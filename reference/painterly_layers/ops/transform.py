"""Ctrl+T: Photoshop-style Free Transform / Distort / Warp of the active paint layer, as a decal
that lives ON the surface.

The lifted content becomes a flat canvas lying on the surface (project/decal.py). Every edit
happens in that canvas's plane coordinates, so navigating the viewport never changes it, and the
preview is drawn on the mesh. Moving slides the canvas over the surface: the grabbed point
follows the surface under the cursor and the canvas tilts with the surface.

  drag inside = slide over the surface · corner = scale (proportional; Shift = free)
  edge = stretch · outside = rotate (Shift = 15° steps) · Ctrl+drag corner = distort
  W = warp (4x4 Bezier grid: drag points, or drag inside the grid)
  Enter / Ctrl+T apply · B apply + brush · L apply + lasso · Esc cancel · navigate freely
"""
import math

import bpy
import gpu
import numpy as np
from bpy_extras.view3d_utils import (location_3d_to_region_2d, region_2d_to_origin_3d,
                                     region_2d_to_vector_3d)
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .. import project as pj
from ..project import decal as dc
from ..ui import hud
from .layers import get_stack
from .modal_util import chain, is_navigation
from .select import image_array, resize_nearest, selection_array, swap_layer_image, write_image
from .view import in_painterly

N = 30          # lattice resolution (divisible by 3 for the warp guide lines)
HIT = 12.0      # handle pick radius, pixels
MAX_CANVAS = 2048
SLIDE_LOG = []  # surface normals used while sliding (tests measure smoothness)


def _inside(p, poly):
    x, y = p
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, np.roll(poly, -1, 0)):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _bern(t):
    return np.array([(1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3])


class PL_OT_transform(bpy.types.Operator):
    bl_idname = "pl.transform"
    bl_label = "Transform Layer"
    bl_description = ("Move (slides over the surface), scale, rotate, distort (Ctrl+drag corner) or "
                      "warp (W) the active paint layer or its selected part (Ctrl+T)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        stack = get_stack(context)[1]
        l = stack.active if stack else None
        return (in_painterly(context) and context.mode == 'PAINT_TEXTURE' and l is not None
                and l.layer_type == "PAINT" and l.paint_image is not None
                and context.area is not None and context.area.type == 'VIEW_3D'
                and context.region.type == 'WINDOW')

    # ------------------------------------------------------------------ setup
    def invoke(self, context, event):
        self.mat, stack = get_stack(context)
        layer = stack.active
        self.layer_uid = layer.uid
        self.img = layer.paint_image
        self.orig = image_array(self.img).copy()
        res = self.orig.shape[0]
        self.obj = context.object
        self.P, self.UV, self.Nrm = pj.mesh_arrays(self.obj, context.evaluated_depsgraph_get(),
                                                   stack.uv_map, normals=True)
        # 1. what's visible and selected now
        pr_v = pj.Projector(self.P, self.UV, context.region_data.view_matrix.copy(),
                            context.region_data.window_matrix.copy(),
                            (context.region.width, context.region.height))
        _, vis_v, _ = pr_v.to_texture(np.zeros((context.region.height, context.region.width), np.float32), res)
        sel = selection_array(context)
        sel = resize_nearest(sel, res) if sel is not None else np.ones((res, res), np.float32)
        lift = vis_v * sel
        w = lift * self.orig[..., 3]
        if w.sum() < 1e-3:
            self.report({'WARNING'}, "Nothing visible to transform on this layer")
            return {'CANCELLED'}
        # 2. a decal frame on the surface under that content, aligned with the screen
        Ptex, Ntex, _ = dc.uv_positions(self.P, self.UV, self.Nrm, res)
        wsum = w.sum()
        anchor = (Ptex * w[..., None]).reshape(-1, 3).sum(0) / wsum
        normal = (Ntex * w[..., None]).reshape(-1, 3).sum(0)
        right = context.region_data.view_rotation @ Vector((1, 0, 0))
        self.frame = dc.Frame(anchor, normal if np.linalg.norm(normal) > 1e-9 else (0, 0, 1), right)
        pts = self.frame.plane(Ptex[w > 0.004])
        x0, y0 = pts.min(0)
        x1, y1 = pts.max(0)
        pad = 0.02 * max(x1 - x0, y1 - y0, 1e-6)
        self.rest = (x0 - pad, y0 - pad, x1 + pad, y1 + pad)
        rw, rh = self.rest[2] - self.rest[0], self.rest[3] - self.rest[1]
        self.depth = max(rw, rh) * 1.5
        ppu = math.sqrt(max((w > 0.004).sum(), 1) / max(rw * rh, 1e-12))  # ~ texels per unit
        self.ppu = min(ppu, MAX_CANVAS / max(rw, rh))
        self.src_size = (max(8, int(rw * self.ppu)), max(8, int(rh * self.ppu)))
        # 3. lift: only what the decal camera can see too, so nothing is lost
        pr_d = dc.decal_projector(self.P, self.UV, self.frame, self.rest, self.src_size, self.depth)
        _, vis_d, _ = pr_d.to_texture(np.zeros(self.src_size[::-1], np.float32), res)
        lift = lift * vis_d
        snap = pr_d.snapshot(self.orig, lift)
        if snap[..., 3].max() < 0.004:
            self.report({'WARNING'}, "Nothing visible to transform on this layer")
            return {'CANCELLED'}
        self.src_tex = pj.texture(snap)
        keep = 1 - lift
        # symmetry: every mirrored side gets the same transform, applied to its own content
        self.mirrors = []
        ip = context.tool_settings.image_paint
        me = self.obj.data
        axes = [getattr(ip, f"use_symmetry_{a}") or getattr(me, f"use_mirror_{a}", False) for a in "xyz"]
        if any(axes):
            sel_canvas = None
            if selection_array(context) is not None:
                s3 = np.repeat(sel[..., None], 3, 2)
                sel_canvas = pr_d.snapshot(np.concatenate([s3, np.ones_like(sel[..., None])], -1))
            for M, odd in dc.mirror_matrices(self.obj, axes):
                fm = dc.mirror_frame(self.frame, M, odd)
                rect_m = dc.mirror_rect(self.rest, odd)
                pr_m = dc.decal_projector(self.P, self.UV, fm, rect_m, self.src_size, self.depth)
                _, vis_m, _ = pr_m.to_texture(np.zeros(self.src_size[::-1], np.float32), res)
                lift_m = vis_m
                if sel_canvas is not None:  # the selection, mirrored onto that side
                    sc = np.flip(sel_canvas, 1) if odd else sel_canvas
                    sm, _, _ = pr_m.to_texture(sc, res)
                    lift_m = lift_m * sm[..., 0]
                snap_m = pr_m.snapshot(self.orig, lift_m)
                if snap_m[..., 3].max() < 0.004:
                    continue
                keep = keep * (1 - lift_m)
                self.mirrors.append({"M": M, "odd": odd,
                                     "src": pj.texture(np.ascontiguousarray(np.flip(snap_m, 1) if odd else snap_m)),
                                     "preview": dc.Preview(self.P)})
        self.cleared = self.orig.copy()
        self.cleared[..., 3] *= keep
        write_image(self.img, self.cleared)  # the lifted pixels leave a hole until applied
        x0, y0, x1, y1 = self.rest
        self.corners = np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], float)
        self.ctrl = None
        self.drag = None
        self.region = context.region
        self.preview = dc.Preview(self.P)
        self._refresh()
        self._h2d = bpy.types.SpaceView3D.draw_handler_add(self._draw_2d, (), 'WINDOW', 'POST_PIXEL')
        self._h3d = bpy.types.SpaceView3D.draw_handler_add(self._draw_3d, (), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        hud.tool_mode(context, True)
        self._status(context)
        self._hover(context, event)
        return {'RUNNING_MODAL'}

    def _status(self, context):
        if self.ctrl is None:
            txt = ("Transform: inside slide · corner scale (Shift free) · edge stretch · outside rotate"
                   " · Ctrl+corner distort · W warp · Enter/Ctrl+T apply · Esc cancel · navigate freely")
        else:
            txt = ("Warp: drag points or inside the grid · W back to transform · Enter/Ctrl+T apply"
                   " · Esc cancel · navigate freely")
        context.workspace.status_text_set(txt)

    # ------------------------------------------------------------------ canvas
    def lattice(self):
        """Lattice in plane coordinates (N+1, N+1, 2)."""
        return pj.quad_lattice(self.corners, N) if self.ctrl is None else pj.bezier_patch(self.ctrl, N)

    def _canvas(self, src=None):
        """Render the transformed content into a plane-space canvas: (W, rect)."""
        lat = self.lattice()
        lo, hi = lat.reshape(-1, 2).min(0), lat.reshape(-1, 2).max(0)
        pad = 0.02 * max(*(hi - lo), 1e-6)
        rect = (lo[0] - pad, lo[1] - pad, hi[0] + pad, hi[1] + pad)
        span = max(rect[2] - rect[0], rect[3] - rect[1])
        ppu = min(self.ppu, MAX_CANVAS / span)
        size = (max(8, int((rect[2] - rect[0]) * ppu)), max(8, int((rect[3] - rect[1]) * ppu)))
        grid = (lat - (rect[0], rect[1])) * (size[0] / (rect[2] - rect[0]), size[1] / (rect[3] - rect[1]))
        W = pj.draw_lattice(src or self.src_tex, grid, (0, 0) + self.src_size, size, target=True,
                            src_size=self.src_size)
        return W, rect

    def _decals(self):
        """[(W, frame, rect)] for the main decal and every mirrored one, in their own frames."""
        W, rect = self._canvas()
        out = [(W, self.frame, rect)]
        for m in self.mirrors:
            Wm, _ = self._canvas(m["src"])
            if m["odd"]:
                Wm = np.ascontiguousarray(np.flip(Wm, 1))
            out.append((Wm, dc.mirror_frame(self.frame, m["M"], m["odd"]), dc.mirror_rect(rect, m["odd"])))
        return out

    def _refresh(self):
        previews = [self.preview] + [m["preview"] for m in self.mirrors]
        for pv, (W, frame, rect) in zip(previews, self._decals()):
            pv.update(self.UV, frame, rect, W, self.depth)

    # ------------------------------------------------------------------ screen helpers
    def _rv3d(self):
        ctx = bpy.context
        return ctx.region_data if ctx.region_data is not None else ctx.space_data.region_3d

    def _to_screen(self, plane_pts):
        pts = self.frame.world(np.asarray(plane_pts, float))
        rv3d = self._rv3d()
        out = []
        for p in pts.reshape(-1, 3):
            s = location_3d_to_region_2d(self.region, rv3d, Vector(p))
            out.append((s.x, s.y) if s is not None else (np.nan, np.nan))
        return np.array(out).reshape(pts.shape[:-1] + (2,))

    def _plane_point(self, context, mx, my):
        """Mouse -> plane coords (intersection of the mouse ray with the decal plane)."""
        rv3d = context.region_data
        o = region_2d_to_origin_3d(self.region, rv3d, (mx, my))
        d = region_2d_to_vector_3d(self.region, rv3d, (mx, my))
        den = d.dot(self.frame.n)
        if abs(den) < 1e-9:
            return None
        s = (self.frame.a - o).dot(self.frame.n) / den
        return self.frame.plane(o + d * s)

    def _surface_hit(self, context, mx, my):
        """Mouse ray -> (hit point, smoothed surface normal) on the painted object, or None."""
        rv3d = context.region_data
        o = region_2d_to_origin_3d(self.region, rv3d, (mx, my))
        d = region_2d_to_vector_3d(self.region, rv3d, (mx, my))
        hit = self._ray(context, o, d)
        if hit is None:
            return None
        loc, nrm = hit
        # Fit a plane through a ring of surface samples around the hit (the decal's footprint):
        # follows the broad form, ignores facets and small bumps. Then ease toward it.
        ref = self._n_smooth if getattr(self, "_n_smooth", None) is not None else nrm
        r = 0.35 * max(self.rest[2] - self.rest[0], self.rest[3] - self.rest[1])
        t = ref.orthogonal().normalized()
        b = ref.cross(t)
        pts = [np.array(loc)]
        for k in range(12):
            ang = 2 * math.pi * k / 12
            off = t * (r * math.cos(ang)) + b * (r * math.sin(ang))
            h = self._ray(context, loc + off + ref * self.depth, -ref)
            if h is not None and (h[0] - loc).length < 3 * r:
                pts.append(np.array(h[0]))
        if len(pts) >= 4:
            q = np.array(pts) - np.mean(pts, 0)
            n_fit = Vector(np.linalg.svd(q)[2][-1])
            if n_fit.dot(nrm) < 0:
                n_fit = -n_fit
        else:
            n_fit = nrm
        new = n_fit if getattr(self, "_n_smooth", None) is None else (self._n_smooth * 0.55 + n_fit * 0.45)
        self._n_smooth = new.normalized()
        SLIDE_LOG.append(tuple(self._n_smooth))
        return loc, self._n_smooth

    def _ray(self, context, origin, direction):
        ob = self.obj
        inv = ob.matrix_world.inverted()
        ok, loc, nrm, _ = ob.ray_cast(inv @ origin, (inv.to_3x3() @ direction).normalized(),
                                      depsgraph=context.evaluated_depsgraph_get())
        if not ok:
            return None
        n = (inv.to_3x3().transposed() @ nrm).normalized()
        return ob.matrix_world @ loc, n

    # ------------------------------------------------------------------ drawing
    def _draw_3d(self):
        if bpy.context.region != self.region:
            return
        try:
            vp = bpy.context.region_data.perspective_matrix
            self.preview.draw(vp)
            for m in self.mirrors:
                m["preview"].draw(vp)
        except Exception as e:
            print("CaraPainter transform preview:", e)

    def _draw_2d(self):
        if bpy.context.region != self.region:  # draw handlers fire in every 3D viewport
            return
        try:
            sh = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.blend_set('ALPHA')
            lat = self._to_screen(self.lattice())
            step = N // 3 if self.ctrl is not None else N
            segs = []
            for k in range(0, N + 1, step):
                for i in range(N):
                    segs += [tuple(lat[k, i]), tuple(lat[k, i + 1]), tuple(lat[i, k]), tuple(lat[i + 1, k])]
            segs = [p for p in segs if not np.isnan(p[0])]
            segs = segs[:len(segs) // 2 * 2]
            sh.uniform_float("color", (1, 1, 1, 0.9))
            batch_for_shader(sh, 'LINES', {"pos": segs}).draw(sh)
            if self.ctrl is not None:
                c = self._to_screen(self.ctrl)
                hl = []
                for (a, b) in (((0, 0), (0, 1)), ((0, 0), (1, 0)), ((0, 3), (0, 2)), ((0, 3), (1, 3)),
                               ((3, 0), (2, 0)), ((3, 0), (3, 1)), ((3, 3), (3, 2)), ((3, 3), (2, 3))):
                    hl += [tuple(c[a]), tuple(c[b])]
                sh.uniform_float("color", (1, 1, 1, 0.5))
                batch_for_shader(sh, 'LINES', {"pos": hl}).draw(sh)
            pts = [tuple(p) for p in self._handles_screen() if not np.isnan(p[0])]
            gpu.state.point_size_set(9)
            sh.uniform_float("color", (0, 0, 0, 1))
            batch_for_shader(sh, 'POINTS', {"pos": pts}).draw(sh)
            gpu.state.point_size_set(6)
            sh.uniform_float("color", (1, 1, 1, 1))
            batch_for_shader(sh, 'POINTS', {"pos": pts}).draw(sh)
            gpu.state.point_size_set(1)
            gpu.state.blend_set('NONE')
        except Exception as e:  # never break the viewport
            print("CaraPainter transform draw:", e)

    def _handles_screen(self):
        if self.ctrl is not None:
            return self._to_screen(self.ctrl.reshape(-1, 2))
        c = self.corners
        return self._to_screen(np.concatenate([c, (c + np.roll(c, -1, 0)) / 2]))

    # ------------------------------------------------------------------ interaction
    CURSORS = {"move": ('HAND', "Move"), "corner": ('SCROLL_XY', "Scale"), "rotate": ('CROSSHAIR', "Rotate"),
               "distort": ('CROSS', "Distort"), "wpoint": ('HAND_POINT', "Warp point"),
               "winside": ('HAND', "Warp")}

    def _hit(self, ms, event):
        """What the pointer (region px) is over. Hit-testing happens on screen, editing in plane."""
        if self.ctrl is not None:
            cs = self._to_screen(self.ctrl)
            d = np.linalg.norm(cs - ms, axis=-1)
            d = np.where(np.isnan(d), 1e9, d)
            i, j = np.unravel_index(np.argmin(d), d.shape)
            if d[i, j] < HIT:
                return ("wpoint", (i, j))
            lat_s = self._to_screen(self.lattice())
            dl = np.linalg.norm(lat_s - ms, axis=-1)
            dl = np.where(np.isnan(dl), 1e9, dl)
            vi, ui = np.unravel_index(np.argmin(dl), dl.shape)
            if dl[vi, ui] < 2 * HIT or _inside(ms, lat_s[[0, 0, -1, -1], [0, -1, -1, 0]]):
                w = np.outer(_bern(vi / N), _bern(ui / N))
                return ("winside", w / (w * w).sum())
            return None
        cs = self._to_screen(self.corners)
        for i in range(4):
            if np.linalg.norm(cs[i] - ms) < HIT:
                return ("distort" if event.ctrl else "corner", i)
        mids = (cs + np.roll(cs, -1, 0)) / 2
        for i in range(4):
            if np.linalg.norm(mids[i] - ms) < HIT:
                return ("edge", i)
        if _inside(ms, cs):
            return ("move", None)
        return ("rotate", None)

    def hover_state(self, ms, event):
        hit = self._hit(ms, event)
        kind = self.drag[0] if self.drag else (hit[0] if hit else None)
        if kind == "edge":
            i = (self.drag or hit)[1]
            cs = self._to_screen(self.corners)
            e = cs[(i + 1) % 4] - cs[i]
            cursor, label = ('MOVE_Y' if abs(e[0]) > abs(e[1]) else 'MOVE_X'), "Stretch"
        elif kind is None:
            cursor, label = 'DEFAULT', ("Warp" if self.ctrl is not None else "Transform")
        else:
            cursor, label = self.CURSORS[kind]
        if self.drag and cursor == 'HAND':
            cursor = 'HAND_CLOSED'
        return cursor, label

    def _hover(self, context, event):
        ms = np.array([event.mouse_region_x, event.mouse_region_y], float)
        cursor, label = self.hover_state(ms, event)
        context.window.cursor_modal_set(cursor)
        hud.set_label(label)

    def _press(self, context, event):
        ms = np.array([event.mouse_region_x, event.mouse_region_y], float)
        hit = self._hit(ms, event)
        self.m0 = self._plane_point(context, *ms)
        self.c0 = self.corners.copy()
        self.k0 = None if self.ctrl is None else self.ctrl.copy()
        self.f0 = self.frame
        self._n_smooth = Vector(self.frame.n)  # sliding eases from the current orientation
        SLIDE_LOG.clear()
        if hit is None or self.m0 is None:
            return None
        return hit

    def _move(self, context, event):
        kind, arg = self.drag
        mx, my = event.mouse_region_x, event.mouse_region_y
        if kind == "move":
            h = self._surface_hit(context, mx, my)
            if h is not None:  # the grabbed point follows the surface under the cursor
                self.frame = self.f0.slid(h[0], h[1], self.m0)
            return
        m = self._plane_point(context, mx, my)
        if m is None:
            return
        d = m - self.m0
        c0 = self.c0
        if kind == "rotate":
            ctr = c0.mean(0)
            a = math.atan2(*(m - ctr)[::-1]) - math.atan2(*(self.m0 - ctr)[::-1])
            if event.shift:
                a = round(a / math.radians(15)) * math.radians(15)
            R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
            self.corners = (c0 - ctr) @ R.T + ctr
        elif kind == "distort":
            self.corners = c0.copy()
            self.corners[arg] = c0[arg] + d
        elif kind in ("corner", "edge"):
            ex = c0[1] - c0[0]
            ey = c0[3] - c0[0]
            B = np.stack([ex / np.linalg.norm(ex), ey / np.linalg.norm(ey)], 1)
            Binv = np.linalg.inv(B)
            if kind == "corner":
                anchor = c0[(arg + 2) % 4]
                q0 = Binv @ (c0[arg] - anchor)
                q1 = Binv @ (m - anchor)
                s = np.where(np.abs(q0) > 1e-9, q1 / np.where(np.abs(q0) > 1e-9, q0, 1), 1.0)
                if not event.shift:  # proportional by default (Photoshop CC); Shift = free
                    k = float(np.dot(q1, q0) / max(np.dot(q0, q0), 1e-12))
                    s = np.array([k, k])
            else:
                mids = (c0 + np.roll(c0, -1, 0)) / 2
                anchor = mids[(arg + 2) % 4]
                q0 = Binv @ (mids[arg] - anchor)
                q1 = Binv @ (m - anchor)
                axis = 1 if arg in (0, 2) else 0
                s = np.ones(2)
                if abs(q0[axis]) > 1e-12:
                    s[axis] = q1[axis] / q0[axis]
            S = B @ np.diag(s) @ Binv
            self.corners = (c0 - anchor) @ S.T + anchor
        elif kind == "wpoint":
            i, j = arg
            self.ctrl = self.k0.copy()
            self.ctrl[i, j] = self.k0[i, j] + d
            if i in (0, 3) and j in (0, 3):  # corners carry their handles, like Photoshop
                for a, b in ((i, 1 if j == 0 else 2), (1 if i == 0 else 2, j)):
                    self.ctrl[a, b] = self.k0[a, b] + d
        elif kind == "winside":
            self.ctrl = self.k0 + arg[..., None] * d

    def _toggle_warp(self, context):
        if self.ctrl is None:
            H = pj.homography([(0, 0), (1, 0), (1, 1), (0, 1)], self.corners)
            t = np.linspace(0, 1, 4)
            U, V = np.meshgrid(t, t)
            p = np.stack([U, V, np.ones_like(U)], -1) @ H.T
            self.ctrl = p[..., :2] / p[..., 2:3]
        else:
            k = self.ctrl
            self.corners = np.array([k[0, 0], k[0, 3], k[3, 3], k[3, 0]])
            self.ctrl = None
        self._status(context)

    def modal(self, context, event):
        context.area.tag_redraw()
        hud.set_mouse(event)
        t, v = event.type, event.value
        if v == 'PRESS' and (t in {'RET', 'NUMPAD_ENTER', 'SPACE'} or (t == 'T' and event.ctrl)):
            return self._commit(context)
        if t in {'B', 'L'} and v == 'PRESS':
            self._commit(context)
            chain(context, "pl.brush_tool" if t == 'B' else "pl.lasso_select")
            return {'FINISHED'}
        if not self.drag and is_navigation(event):
            return {'PASS_THROUGH'}  # the decal is anchored to the surface: navigation is free
        if t == 'MOUSEMOVE':
            if self.drag:
                self._move(context, event)
                self._refresh()
            self._hover(context, event)
        elif t in {'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT'}:
            self._hover(context, event)
        elif t == 'LEFTMOUSE' and v == 'PRESS':
            self.drag = self._press(context, event)
            self._hover(context, event)
        elif t == 'LEFTMOUSE' and v == 'RELEASE':
            self.drag = None
            self._hover(context, event)
        elif t == 'W' and v == 'PRESS':
            self._toggle_warp(context)
            self._refresh()
            self._hover(context, event)
        elif t == 'ESC' and v == 'PRESS':
            write_image(self.img, self.orig)
            self._finish(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _commit(self, context):
        self._apply(context)
        self._finish(context)
        return {'FINISHED'}

    def _finish(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._h2d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._h3d, 'WINDOW')
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        hud.tool_mode(context, False)
        context.area.tag_redraw()

    def _apply(self, context):
        res = self.orig.shape[0]
        out = self.cleared
        for W, frame, rect in self._decals():
            pr = dc.decal_projector(self.P, self.UV, frame, rect, (W.shape[1], W.shape[0]), self.depth)
            proj, vis, inside = pr.to_texture(W, res)
            proj = np.stack([pj.bleed(proj[..., c], inside > 0.5, 3) for c in range(4)], -1)
            a = proj[..., 3:4]
            base = out
            out_a = a + base[..., 3:4] * (1 - a)
            out = np.empty_like(base)
            out[..., :3] = (proj[..., :3] + base[..., :3] * base[..., 3:4] * (1 - a)) / np.maximum(out_a, 1e-6)
            out[..., 3:4] = out_a
        write_image(self.img, self.orig)  # the old image keeps the original pixels for undo
        swap_layer_image(context, self.mat, self.layer_uid, out)


classes = (PL_OT_transform,)
