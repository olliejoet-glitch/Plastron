"""Lasso selection (L) and selection actions (Ctrl+D deselect, invert, delete, fill).

The selection is a greyscale texture used as Blender's Texture Paint *stencil mask*, so painting
is confined to it and the viewport tints it. Every change creates a new image (and layer edits
swap in a new layer image) so Ctrl+Z works: Blender can't undo pixels written from Python, but
it does undo which image a property points at.
"""
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from .. import project as pj
from .layers import get_stack, sync_paint_target
from ..ui import hud
from .modal_util import chain, is_navigation
from .view import in_painterly

SEL_KEY = "pl_selection"


# ----------------------------------------------------------------------------- image helpers

def image_array(img):
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def write_image(img, arr):
    img.pixels.foreach_set(np.ascontiguousarray(arr, np.float32).reshape(-1))
    img.update()


def resize_nearest(a, res):
    if a.shape[0] == res and a.shape[1] == res:
        return a
    ys = (np.arange(res) * a.shape[0] / res).astype(int)
    xs = (np.arange(res) * a.shape[1] / res).astype(int)
    return a[ys][:, xs]


def swap_layer_image(context, mat, layer_uid, arr):
    """Put arr (straight RGBA, stored values) into a NEW image on the layer (undoable)."""
    stack = mat.pl_stack
    layer = stack.by_uid(layer_uid)
    old = layer.paint_image
    h, w = arr.shape[:2]
    new = bpy.data.images.new(old.name if old else "Paint", w, h, alpha=True)
    if old is not None:
        new.colorspace_settings.name = old.colorspace_settings.name
    write_image(new, arr)
    new["pl_owned"] = True  # packed on save
    layer.paint_image = new
    sync_paint_target(context, mat)
    return new


def selection_image(context):
    ip = context.scene.tool_settings.image_paint
    img = ip.stencil_image
    if ip.use_stencil_layer and img is not None and img.get(SEL_KEY):
        return img
    return None


def selection_array(context, res=None):
    img = selection_image(context)
    if img is None:
        return None
    a = image_array(img)[..., 0]
    return resize_nearest(a, res) if res else a


def set_selection(context, mask):
    res = mask.shape[0]
    img = bpy.data.images.new("PL Selection", res, res, alpha=False, is_data=True)
    write_image(img, np.repeat(np.clip(mask, 0, 1)[..., None], 4, 2))
    img[SEL_KEY] = True
    ip = context.scene.tool_settings.image_paint
    ip.stencil_image = img
    ip.use_stencil_layer = True
    ip.invert_stencil = True  # Blender's stencil protects white; we store white = selected
    ip.stencil_color = (0.15, 0.45, 1.0)
    return img


def clear_selection(context):
    context.scene.tool_settings.image_paint.use_stencil_layer = False


def view_projector(context, stack):
    region, rv3d = context.region, context.region_data
    P, uv = pj.mesh_arrays(context.object, context.evaluated_depsgraph_get(), stack.uv_map)
    return pj.Projector(P, uv, rv3d.view_matrix.copy(), rv3d.window_matrix.copy(),
                        (region.width, region.height))


def _paint_layer(stack):
    l = stack.active
    return l if l is not None and l.layer_type == "PAINT" and l.paint_image is not None else None


# ----------------------------------------------------------------------------- lasso

class PL_OT_lasso_select(bpy.types.Operator):
    """L: Lasso tool. Drag around what you want to paint (Shift = add; Alt+D switches the tool
    to subtract and back), as many times as you like; the view can be navigated in between
    (Alt+drag orbits as usual). L again, B or Esc: back to brush"""
    bl_idname = "pl.lasso_select"
    bl_label = "Lasso Tool"
    bl_options = {'REGISTER'}  # one undo step per selection is pushed by hand

    @classmethod
    def poll(cls, context):
        return (in_painterly(context) and context.mode == 'PAINT_TEXTURE'
                and get_stack(context)[1] is not None and context.area is not None
                and context.area.type == 'VIEW_3D' and context.region.type == 'WINDOW')

    def invoke(self, context, event):
        self.pts = []
        self.drawing = False
        self.op = "SET"
        self.subtract = False  # Alt+D toggles (Alt+drag stays viewport navigation)
        self.region = context.region
        self._h = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        context.window.cursor_modal_set('CROSSHAIR')
        hud.tool_mode(context, True)
        self._label(event)
        context.workspace.status_text_set(
            "Lasso: drag around an area · Shift add · Alt+D subtract mode · Ctrl+D deselect · "
            "Ctrl+T transform · L / B / Esc back to brush · navigate as usual")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _mode(self, event):
        return "SUB" if self.subtract else ("ADD" if event.shift else "SET")

    def _label(self, event):
        op = self.op if self.drawing else self._mode(event)
        hud.set_label({"SET": "Lasso", "ADD": "Lasso: add", "SUB": "Lasso: subtract"}[op])

    def _draw(self):
        if len(self.pts) < 2 or bpy.context.region != self.region:  # only the viewport we lasso in
            return
        sh = gpu.shader.from_builtin('UNIFORM_COLOR')
        pts = self.pts + [self.pts[0]]
        for off, col in ((1, (0, 0, 0, 0.8)), (0, (1, 1, 1, 1))):
            b = batch_for_shader(sh, 'LINE_STRIP', {"pos": [(x + off, y - off) for x, y in pts]})
            sh.uniform_float("color", col)
            b.draw(sh)

    def _finish(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        hud.tool_mode(context, False)
        context.area.tag_redraw()

    def modal(self, context, event):
        context.area.tag_redraw()
        hud.set_mouse(event)
        t, v = event.type, event.value
        if t == 'D' and v == 'PRESS' and event.ctrl:
            clear_selection(context)
            bpy.ops.ed.undo_push(message="Deselect")
            return {'RUNNING_MODAL'}
        if t == 'D' and v == 'PRESS' and event.alt:
            self.subtract = not self.subtract
            self._label(event)
            return {'RUNNING_MODAL'}
        if not self.drawing and is_navigation(event):
            return {'PASS_THROUGH'}
        if t == 'MOUSEMOVE':
            if self.drawing:
                p = (event.mouse_region_x, event.mouse_region_y)
                if (p[0] - self.pts[-1][0]) ** 2 + (p[1] - self.pts[-1][1]) ** 2 > 4:
                    self.pts.append(p)
            self._label(event)
        elif t in {'LEFT_SHIFT', 'RIGHT_SHIFT'}:
            self._label(event)
        elif t == 'LEFTMOUSE' and v == 'PRESS':
            self.drawing = True
            self.op = self._mode(event)
            self.pts = [(event.mouse_region_x, event.mouse_region_y)]
        elif t == 'LEFTMOUSE' and v == 'RELEASE' and self.drawing:
            self.drawing = False
            if len(self.pts) >= 3:
                self.apply(context)
                bpy.ops.ed.undo_push(message="Lasso Select")
            self.pts = []
            self._label(event)
        elif t == 'RIGHTMOUSE' and v == 'PRESS' and self.drawing:
            self.drawing = False  # abandon this lasso, keep the tool
            self.pts = []
        elif t == 'T' and v == 'PRESS' and event.ctrl:
            self._finish(context)
            chain(context, "pl.transform")
            return {'FINISHED'}
        elif v == 'PRESS' and (t in {'L', 'ESC'} or t == 'B'):
            self._finish(context)
            if t == 'B':
                chain(context, "pl.brush_tool")
            return {'FINISHED'}
        elif t in {'LEFTMOUSE', 'RIGHTMOUSE'}:
            pass  # never let clicks reach the brush while lassoing
        elif v in {'PRESS', 'RELEASE'} and not self.drawing:
            return {'PASS_THROUGH'}  # other hotkeys (Q/W, Z, C, V…) keep working
        return {'RUNNING_MODAL'}

    def apply(self, context):
        mat, stack = get_stack(context)
        res = stack.resolution
        pr = view_projector(context, stack)
        screen_mask = pj.polygon_mask(self.pts, pr.size)
        val, vis, inside = pr.to_texture(screen_mask, res)
        m = pj.bleed(val[..., 0], inside > 0.5, 4)
        feather = context.scene.pl_sel_feather
        if feather > 0:
            m = pj.blur(m, feather)
        old = selection_array(context, res)
        if old is not None and self.op == "ADD":
            m = np.maximum(old, m)
        elif old is not None and self.op == "SUB":
            m = old * (1 - m)
        elif self.op == "SUB":
            m = np.zeros_like(m)
        set_selection(context, m)


# ----------------------------------------------------------------------------- actions

class _SelOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return in_painterly(context) and context.mode == 'PAINT_TEXTURE' and get_stack(context)[1] is not None


class PL_OT_deselect(_SelOp, bpy.types.Operator):
    bl_idname = "pl.deselect"
    bl_label = "Deselect"
    bl_description = "Remove the selection (Ctrl+D)"

    def execute(self, context):
        clear_selection(context)
        return {'FINISHED'}


class PL_OT_select_invert(_SelOp, bpy.types.Operator):
    bl_idname = "pl.select_invert"
    bl_label = "Invert Selection"
    bl_description = "Select everything that isn't selected"

    def execute(self, context):
        stack = get_stack(context)[1]
        m = selection_array(context, stack.resolution)
        set_selection(context, np.zeros((stack.resolution,) * 2, np.float32) if m is None else 1 - m)
        return {'FINISHED'}


class PL_OT_selection_delete(_SelOp, bpy.types.Operator):
    bl_idname = "pl.selection_delete"
    bl_label = "Delete Selected"
    bl_description = "Erase the active paint layer inside the selection"

    def execute(self, context):
        mat, stack = get_stack(context)
        act = stack.active
        if act is not None and act.paint_target == "MASK" and selection_array(context) is not None:
            return bpy.ops.pl.mask_edit(action="BLACK")  # painting the mask: hide inside the selection
        layer = _paint_layer(stack)
        m = selection_array(context)
        if layer is None or m is None:
            self.report({'WARNING'}, "Needs a paint layer and a selection")
            return {'CANCELLED'}
        a = image_array(layer.paint_image).copy()
        a[..., 3] *= 1 - resize_nearest(m, a.shape[0])
        swap_layer_image(context, mat, layer.uid, a)
        return {'FINISHED'}


class PL_OT_selection_fill(_SelOp, bpy.types.Operator):
    bl_idname = "pl.selection_fill"
    bl_label = "Fill Selected"
    bl_description = "Fill the selection on the active paint layer with the brush colour"

    def execute(self, context):
        mat, stack = get_stack(context)
        layer = _paint_layer(stack)
        m = selection_array(context)
        ip = context.tool_settings.image_paint
        ups = ip.unified_paint_settings
        lin = ups.color if (ups.use_unified_color or ip.brush is None) else ip.brush.color
        enc = np.array([c * 12.92 if c < 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in lin],
                       np.float32)
        act = stack.active
        if act is not None and act.paint_target == "MASK" and m is not None:  # painting the mask
            return bpy.ops.pl.mask_edit(action="VALUE", value=float(np.dot(enc, (0.3, 0.59, 0.11))))
        if layer is None or m is None:
            self.report({'WARNING'}, "Needs a paint layer and a selection")
            return {'CANCELLED'}
        if layer.paint_image.colorspace_settings.name in ('Non-Color', 'Raw') or layer.paint_image.is_float:
            enc = np.array(lin, np.float32)
        a = image_array(layer.paint_image).copy()
        k = resize_nearest(m, a.shape[0])[..., None]
        out_a = k + a[..., 3:4] * (1 - k)
        a[..., :3] = (enc * k + a[..., :3] * a[..., 3:4] * (1 - k)) / np.maximum(out_a, 1e-6)
        a[..., 3:4] = out_a
        swap_layer_image(context, mat, layer.uid, a)
        return {'FINISHED'}


classes = (PL_OT_lasso_select, PL_OT_deselect, PL_OT_select_invert, PL_OT_selection_delete,
           PL_OT_selection_fill)
