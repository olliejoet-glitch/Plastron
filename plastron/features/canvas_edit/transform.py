"""Moving and transforming pixels.

Ctrl+T (transform): a box around the selection (or, with nothing selected,
around the active layer's painting).
  drag inside: move · drag a corner: scale (Shift: keep proportions) ·
  drag an edge's middle: stretch · drag outside the box: rotate (Shift: 15°
  steps) · Ctrl+drag a corner: distort / perspective (corner pin) ·
  W: warp (drag the grid points; W again: back to the box) ·
  Enter or double-click: apply · Esc: cancel.
V (move): drag to move the selection (or the whole layer); stays on until
another tool key or Esc.

While transforming, the pixels float above the layer (drawn by the GPU, the
layer itself untouched); they're resampled into the layer only on apply, in
one undoable step. The selection moves with them.
"""

import math

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from ...config import tools as cfg
from ...core.theme import _color
from ..storyboard import tools as storyboard_tools
from . import pixels, selection, shapes

HANDLE_PX = 9


class Floating:
    """Pixels lifted off a layer: where they came from and where they're going."""

    def __init__(self, context):
        self.mat = pixels.material()
        layer = pixels.paint_layer(self.mat)
        if layer is None:
            raise ValueError("Pick a paint layer to move or transform")
        self.layer_uid = layer.uid
        self.orig = layer.paint_image
        a = pixels.array(self.orig)
        self.w, self.h = a.shape[1], a.shape[0]
        sel = selection.mask(context)
        self.had_selection = sel is not None
        m = sel if sel is not None else (a[..., 3] > 0).astype(np.float32)
        box = shapes.bbox(m * (a[..., 3] > 0) if sel is not None else m)
        if box is None:
            box = shapes.bbox(m) if sel is not None else None
        if box is None:
            raise ValueError("Nothing to move here")
        x0, y0, x1, y1 = box
        self.box = box
        self.src = a[y0:y1, x0:x1].copy()
        self.src[..., 3] *= m[y0:y1, x0:x1]
        self.src_mask = m[y0:y1, x0:x1].copy()
        self.base = a.copy()
        self.base[..., 3] *= 1.0 - m
        self.corners = shapes.rect_corners(x0, y0, x1, y1)
        self.warp = None
        # Show the hole while the pixels float.
        self.working = bpy.data.images.new(".Plastron Transform", self.w, self.h, alpha=True)
        pixels.write(self.working, self.base)
        self._set_layer_image(self.working)
        self.float_image = bpy.data.images.new(".Plastron Floating", x1 - x0, y1 - y0, alpha=True)
        pixels.write(self.float_image, self.src)

    def _set_layer_image(self, img):
        from ...layers import compiler, paint_target
        layer = self.mat.plastron_stack.by_uid(self.layer_uid)
        layer.paint_image = img
        compiler.push_layer(self.mat, layer)
        paint_target.sync(self.mat)

    # geometry
    def points(self):
        return self.corners if self.warp is None else np.vstack([self.corners, self.warp.reshape(-1, 2)])

    def set_points(self, pts):
        self.corners = pts[:4].copy()
        if self.warp is not None:
            self.warp = pts[4:].reshape(self.warp.shape).copy()

    def grid(self, n=None):
        n = n or cfg.TRANSFORM_MESH
        if self.warp is not None:
            return shapes.grid_from_warp(self.warp, n)
        return shapes.grid_from_corners(self.corners, n)

    def moved(self):
        return not np.allclose(self.grid(2), shapes.grid_from_corners(shapes.rect_corners(*self.box), 2))

    # finishing
    def apply(self, context):
        grid = self.grid()
        out = shapes.render(self.src, grid, self.w, self.h)
        result = shapes.over(self.base, out)
        self._set_layer_image(self.orig)          # undo goes back to the untouched original
        pixels.replace_image(self.mat, self.layer_uid, result)
        if self.had_selection:
            m = np.zeros(self.src_mask.shape + (4,), np.float32)
            m[..., :3] = 1.0
            m[..., 3] = self.src_mask
            selection.set_mask(context, shapes.render(m, grid, self.w, self.h)[..., 3])
        self._cleanup()

    def cancel(self):
        self._set_layer_image(self.orig)
        self._cleanup()

    def _cleanup(self):
        for img in (self.working, self.float_image):
            if img is not None and img.name in bpy.data.images:
                bpy.data.images.remove(img)
        self.working = self.float_image = None


def draw_floating(context, fl, handles, warp_handles):
    if fl is None or fl.float_image is None:
        return
    n = cfg.TRANSFORM_MESH
    grid = fl.grid(n)
    screen = [[pixels.region_point(context, *grid[i, j]) for j in range(n + 1)] for i in range(n + 1)]
    pos, uv = [], []
    for i in range(n):
        for j in range(n):
            quad = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
            for a, b, c in ((0, 1, 2), (0, 2, 3)):
                for k in (a, b, c):
                    r, col = quad[k]
                    pos.append(screen[r][col])
                    uv.append((col / n, r / n))
    shader = gpu.shader.from_builtin('IMAGE')
    gpu.state.blend_set('ALPHA')
    shader.uniform_sampler("image", gpu.texture.from_image(fl.float_image))
    batch_for_shader(shader, 'TRIS', {"pos": pos, "texCoord": uv}).draw(shader)
    line = gpu.shader.from_builtin('UNIFORM_COLOR')
    colour = _color(cfg.TRANSFORM_COLOR)
    line.uniform_float("color", colour)
    box = [pixels.region_point(context, *p) for p in fl.corners]
    if fl.warp is not None and warp_handles:
        g = fl.grid(12)
        lines = []
        for i in range(13):
            for j in range(12):
                lines += [pixels.region_point(context, *g[i, j]), pixels.region_point(context, *g[i, j + 1])]
                lines += [pixels.region_point(context, *g[j, i]), pixels.region_point(context, *g[j + 1, i])]
        batch_for_shader(line, 'LINES', {"pos": lines}).draw(line)
        pts = [pixels.region_point(context, *p) for p in fl.warp.reshape(-1, 2)]
    else:
        batch_for_shader(line, 'LINE_LOOP', {"pos": box}).draw(line)
        pts = box + [((box[k][0] + box[(k + 1) % 4][0]) / 2, (box[k][1] + box[(k + 1) % 4][1]) / 2)
                     for k in range(4)] if handles else []
    s = HANDLE_PX / 2
    for x, y in pts:
        sq = [(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)]
        line.uniform_float("color", (1, 1, 1, 1))
        batch_for_shader(line, 'TRI_FAN', {"pos": sq}).draw(line)
        line.uniform_float("color", colour)
        batch_for_shader(line, 'LINE_LOOP', {"pos": sq}).draw(line)
    gpu.state.blend_set('NONE')


def _inside(pt, quad):
    sign = None
    for k in range(4):
        a, b = quad[k], quad[(k + 1) % 4]
        cross = (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])
        if abs(cross) < 1e-9:
            continue
        if sign is None:
            sign = cross > 0
        elif (cross > 0) != sign:
            return False
    return True


def _rotate(pts, centre, angle):
    c, s = math.cos(angle), math.sin(angle)
    d = pts - centre
    return centre + np.c_[d[:, 0] * c - d[:, 1] * s, d[:, 0] * s + d[:, 1] * c]


def _scale(pts, anchor, ex, ey, sx, sy):
    basis = np.array([ex, ey]).T
    local = np.linalg.solve(basis, (pts - anchor).T)
    local[0] *= sx
    local[1] *= sy
    return anchor + (basis @ local).T


class _TransformBase:
    def _start_drag(self, context, event):
        """What a press at the mouse grabs: (kind, index)."""
        fl = self.fl
        mx, my = event.mouse_region_x, event.mouse_region_y
        near = lambda p: (p[0] - mx) ** 2 + (p[1] - my) ** 2 <= (HANDLE_PX + 3) ** 2
        if fl.warp is not None and self.warp_mode:
            for k, p in enumerate(fl.warp.reshape(-1, 2)):
                if near(pixels.region_point(context, *p)):
                    return 'WARP', k
        box = [pixels.region_point(context, *p) for p in fl.corners]
        if not self.move_only:
            for k, p in enumerate(box):
                if near(p):
                    return ('DISTORT' if event.ctrl else 'CORNER'), k
            for k in range(4):
                mid = ((box[k][0] + box[(k + 1) % 4][0]) / 2, (box[k][1] + box[(k + 1) % 4][1]) / 2)
                if near(mid):
                    return 'EDGE', k
        if self.move_only or _inside((mx, my), box):
            return 'MOVE', 0
        return 'ROTATE', 0

    def _drag(self, context, event):
        fl = self.fl
        p = np.array(pixels.canvas_point(context, event.mouse_region_x, event.mouse_region_y))
        start = self.start_pts
        corners = start[:4]
        kind, k = self.grab
        if kind == 'MOVE':
            new = start + (p - self.start_mouse)
        elif kind == 'ROTATE':
            c = corners.mean(0)
            a = math.atan2(*(p - c)[::-1]) - math.atan2(*(self.start_mouse - c)[::-1])
            if event.shift:
                a = round(a / math.radians(15)) * math.radians(15)
            new = _rotate(start, c, a)
        elif kind == 'CORNER':
            anchor = corners[(k + 2) % 4]
            ex = corners[1] - corners[0]
            ey = corners[3] - corners[0]
            basis = np.array([ex, ey]).T
            d0 = np.linalg.solve(basis, corners[k] - anchor)
            d1 = np.linalg.solve(basis, p - anchor)
            sx = d1[0] / d0[0] if abs(d0[0]) > 1e-9 else 1.0
            sy = d1[1] / d0[1] if abs(d0[1]) > 1e-9 else 1.0
            if event.shift:
                sx = sy = float(np.dot(d1, d0) / max(np.dot(d0, d0), 1e-9))
            new = _scale(start, anchor, ex, ey, sx, sy)
        elif kind == 'EDGE':
            ex = corners[1] - corners[0]
            ey = corners[3] - corners[0]
            mid = (corners[k] + corners[(k + 1) % 4]) / 2
            opp = (corners[(k + 2) % 4] + corners[(k + 3) % 4]) / 2
            basis = np.array([ex, ey]).T
            d0 = np.linalg.solve(basis, mid - opp)
            d1 = np.linalg.solve(basis, p - opp)
            if k in (0, 2):
                new = _scale(start, opp, ex, ey, 1.0, d1[1] / d0[1] if abs(d0[1]) > 1e-9 else 1.0)
            else:
                new = _scale(start, opp, ex, ey, d1[0] / d0[0] if abs(d0[0]) > 1e-9 else 1.0, 1.0)
        elif kind == 'DISTORT':
            new = start.copy()
            new[k] = p
            if fl.warp is not None:            # keep a warp's inner points riding along
                old = shapes.homography(corners, new[:4])
                new[4:] = shapes.apply_h(old, start[4:])
        else:  # WARP
            new = start.copy()
            new[4 + k] = p
        fl.set_points(new)
        context.area.tag_redraw()


class PLASTRON_OT_transform(_TransformBase, bpy.types.Operator):
    """Transform the selection or layer: scale, rotate, move, distort, warp (Ctrl+T)"""
    bl_idname = "plastron.transform"
    bl_label = "Transform"
    bl_options = {'REGISTER'}

    move_only = False

    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_TEXTURE' and pixels.paint_layer() is not None and \
            context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        try:
            self.fl = Floating(context)
        except ValueError as err:
            self.report({'INFO'}, str(err))
            return {'CANCELLED'}
        self.grab = None
        self.warp_mode = False
        self.region = context.region
        self._h = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        storyboard_tools.override_label[0] = "Transform: Enter applies, Esc cancels, W warp"
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _draw(self):
        if bpy.context.region == self.region:
            draw_floating(bpy.context, self.fl, True, self.warp_mode)

    def _end(self, context, apply):
        bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
        storyboard_tools.override_label[0] = None
        if apply and self.fl.moved():
            self.fl.apply(context)
            pixels.undo_push("Transform")
        else:
            self.fl.cancel()
        context.area.tag_redraw()

    def modal(self, context, event):
        t, v = event.type, event.value
        if self.grab is None and selection.is_navigation(event):
            return {'PASS_THROUGH'}
        if t == 'MOUSEMOVE':
            if self.grab is not None:
                self._drag(context, event)
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'DOUBLE_CLICK':
            self._end(context, True)
            return {'FINISHED'}
        if t == 'LEFTMOUSE' and v == 'PRESS':
            self.grab = self._start_drag(context, event)
            self.start_pts = self.fl.points().copy()
            self.start_mouse = np.array(pixels.canvas_point(context, event.mouse_region_x,
                                                            event.mouse_region_y))
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'RELEASE':
            self.grab = None
            return {'RUNNING_MODAL'}
        if v == 'PRESS' and t in {'RET', 'NUMPAD_ENTER'}:
            self._end(context, True)
            return {'FINISHED'}
        if v == 'PRESS' and t == 'T' and event.ctrl:
            self._end(context, True)
            return {'FINISHED'}
        if v == 'PRESS' and t in {'ESC', 'RIGHTMOUSE'}:
            self._end(context, False)
            return {'CANCELLED'}
        if v == 'PRESS' and t == 'W':
            if self.fl.warp is None:
                self.fl.warp = shapes.warp_from_corners(self.fl.corners)
            self.warp_mode = not self.warp_mode
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}


class PLASTRON_OT_move_tool(_TransformBase, bpy.types.Operator):
    """Move tool (V): drag to move the selection, or the whole layer"""
    bl_idname = "plastron.move_tool"
    bl_label = "Move"
    bl_options = {'REGISTER'}

    move_only = True

    @classmethod
    def poll(cls, context):
        return PLASTRON_OT_transform.poll(context)

    def invoke(self, context, event):
        self.fl, self.grab, self.warp_mode = None, None, False
        self.region = context.region
        self._h = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        storyboard_tools.override_label[0] = "Move"
        context.window.cursor_modal_set('SCROLL_XY')
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _draw(self):
        if bpy.context.region == self.region:
            draw_floating(bpy.context, self.fl, False, False)

    def _finish(self, context):
        if self.fl is not None:
            self.fl.cancel()
        bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
        context.window.cursor_modal_restore()
        storyboard_tools.override_label[0] = None
        context.area.tag_redraw()

    def modal(self, context, event):
        t, v = event.type, event.value
        if self.fl is None and selection.is_navigation(event):
            return {'PASS_THROUGH'}
        if t == 'MOUSEMOVE':
            if self.fl is not None:
                self._drag(context, event)
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'PRESS':
            try:
                self.fl = Floating(context)
            except ValueError as err:
                self.report({'INFO'}, str(err))
                return {'RUNNING_MODAL'}
            self.grab = ('MOVE', 0)
            self.start_pts = self.fl.points().copy()
            self.start_mouse = np.array(pixels.canvas_point(context, event.mouse_region_x,
                                                            event.mouse_region_y))
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'RELEASE' and self.fl is not None:
            if self.fl.moved():
                self.fl.apply(context)
                pixels.undo_push("Move")
            else:
                self.fl.cancel()
            self.fl = None
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if t in {'LEFTMOUSE', 'RIGHTMOUSE'}:
            return {'RUNNING_MODAL'}
        if v == 'PRESS' and t == 'ESC':
            self._finish(context)
            return {'FINISHED'}
        if v == 'PRESS' and t == 'V' and not event.ctrl:
            return {'RUNNING_MODAL'}
        if v == 'PRESS' and self.fl is None and (t in cfg.LEAVE_SELECTION_KEYS or (t == 'T' and event.ctrl)):
            self._finish(context)
            return {'FINISHED', 'PASS_THROUGH'}
        return {'PASS_THROUGH'} if self.fl is None else {'RUNNING_MODAL'}


classes = (PLASTRON_OT_transform, PLASTRON_OT_move_tool)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
