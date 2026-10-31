"""Pixel selection (L lasso, M rectangle), Photoshop-style.

The selection is a grey image (white = selected) used as Texture Paint's
stencil mask, so painting stays inside it. Each change makes a new image, kept
in scene.plastron_selection: Blender never undoes tool settings (where the
stencil lives), but it does undo the scene, so after every undo the stencil
is set again from it, and Ctrl+Z steps back through selections. The canvas tints what's outside the
selection and outlines its edge.

Drag to select; Shift+drag adds, Alt+drag takes away. The tool stays on
(navigate as usual) until another tool key or Esc.
Ctrl+D deselect, Ctrl+A select all, Ctrl+Shift+I invert, Delete erases the
selected pixels of the active layer.
"""

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from ...config import tools as cfg
from ...core import handlers
from ...core.theme import _color
from ..storyboard import tools as storyboard_tools
from . import pixels, shapes

SEL_KEY = "plastron_selection"
_display = {"source": None, "image": None}
_handles = []


# --- the selection ------------------------------------------------------------------------

def image(context=None):
    scene = (context or bpy.context).scene
    img = scene.plastron_selection if scene is not None else None
    return img if img is not None and img.get(SEL_KEY) else None


def apply_stencil(scene):
    """Point Texture Paint's stencil at the scene's selection (or switch it off)."""
    if scene is None:
        return
    ip = scene.tool_settings.image_paint
    img = scene.plastron_selection
    on = img is not None
    if on and ip.stencil_image != img:
        ip.stencil_image = img
    if on and not ip.invert_stencil:
        ip.invert_stencil = True     # Blender's stencil protects white; ours is white = selected
    if ip.use_stencil_layer != on:
        ip.use_stencil_layer = on


def mask(context=None):
    """float32 (height, width) selection, or None when nothing is selected."""
    img = image(context)
    if img is None:
        return None
    m = pixels.array(img)[..., 0]
    w, h = pixels.size()
    return m if m.shape == (h, w) else None


def set_mask(context, m):
    """Replace the selection (undoable). An empty mask deselects."""
    if m is None or not (m > 0.5).any():
        clear(context)
        return None
    h, w = m.shape
    img = bpy.data.images.new("Plastron Selection", w, h, alpha=False, is_data=True)
    rgba = np.repeat(np.clip(m, 0, 1)[..., None], 4, 2)
    rgba[..., 3] = 1.0
    pixels.write(img, rgba)
    img[SEL_KEY] = True
    context.scene.plastron_selection = img
    apply_stencil(context.scene)
    _redraw(context)
    return img


def clear(context):
    if context.scene.plastron_selection is not None:
        context.scene.plastron_selection = None
    apply_stencil(context.scene)
    _redraw(context)


def _after_undo(*_args):
    apply_stencil(bpy.context.scene)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _redraw(context):
    for area in context.window.screen.areas if context.window else ():
        if area.type == 'VIEW_3D':
            area.tag_redraw()


# --- showing it ---------------------------------------------------------------------------

def _display_image(sel):
    """Tint outside the selection, bright edge: an image made once per selection."""
    if _display["source"] == sel.name and _display["image"] is not None:
        return _display["image"]
    m = pixels.array(sel)[..., 0]
    edge = shapes.outline(m)
    thick = edge.copy()                      # 2-3 px so it shows when zoomed out
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        thick |= np.roll(np.roll(edge, dy, 0), dx, 1)
    tint = list(_color(cfg.SELECTION_COLOR))
    rgba = np.zeros(m.shape + (4,), np.float32)
    rgba[..., :3] = tint[:3]
    rgba[..., 3] = (1.0 - m) * cfg.SELECTION_TINT_ALPHA
    rgba[thick] = (1.0, 1.0, 1.0, 0.9)
    img = _display["image"]
    h, w = m.shape
    if img is None or tuple(img.size) != (w, h) or img.name not in bpy.data.images:
        img = bpy.data.images.new(".Plastron Selection View", w, h, alpha=True)
    pixels.write(img, rgba)
    _display.update(source=sel.name, image=img)
    return img


def _quad(context, x0, y0, x1, y1):
    return [pixels.region_point(context, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


def draw():
    context = bpy.context
    if context.mode != 'PAINT_TEXTURE' or pixels.material() is None:
        return
    sel = image(context)
    if sel is None:
        return
    w, h = pixels.size()
    tex = gpu.texture.from_image(_display_image(sel))
    shader = gpu.shader.from_builtin('IMAGE')
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": _quad(context, 0, 0, w, h),
                                                 "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)]})
    gpu.state.blend_set('ALPHA')
    shader.uniform_sampler("image", tex)
    batch.draw(shader)
    gpu.state.blend_set('NONE')


# --- the lasso / rectangle tool --------------------------------------------------------------

NAVIGATION = {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'}


def is_navigation(event):
    if event.type in NAVIGATION:
        return True
    return event.type == 'LEFTMOUSE' and ((event.alt and event.shift) or (event.ctrl and event.alt))


class PLASTRON_OT_select_tool(bpy.types.Operator):
    """Select pixels: drag a lasso (L) or a rectangle (M). Shift adds, Alt takes away"""
    bl_idname = "plastron.select_tool"
    bl_label = "Select"
    bl_options = {'REGISTER'}           # each selection pushes its own undo step

    shape: bpy.props.EnumProperty(items=[('LASSO', "Lasso", ""), ('RECT', "Rectangle", "")])

    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_TEXTURE' and pixels.material() is not None and \
            context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        self.pts, self.drawing, self.mode = [], False, 'SET'
        self.region = context.region
        self._h = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        context.window.cursor_modal_set('CROSSHAIR')
        storyboard_tools.override_label[0] = "Lasso select" if self.shape == 'LASSO' else "Rectangle select"
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _draw(self):
        if len(self.pts) < 2 or bpy.context.region != self.region:
            return
        if self.shape == 'RECT':
            (x0, y0), (x1, y1) = self.pts[0], self.pts[-1]
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        else:
            pts = self.pts + [self.pts[0]]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        for off, col in ((1, (0, 0, 0, 0.8)), (0, (1, 1, 1, 1))):
            shader.uniform_float("color", col)
            batch_for_shader(shader, 'LINE_STRIP', {"pos": [(x + off, y - off) for x, y in pts]}).draw(shader)

    def _finish(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._h, 'WINDOW')
        context.window.cursor_modal_restore()
        storyboard_tools.override_label[0] = None
        context.area.tag_redraw()

    def modal(self, context, event):
        t, v = event.type, event.value
        if not self.drawing and is_navigation(event):
            return {'PASS_THROUGH'}
        if t == 'MOUSEMOVE':
            if self.drawing:
                p = (event.mouse_region_x, event.mouse_region_y)
                if self.shape == 'RECT':
                    self.pts = [self.pts[0], p]
                elif (p[0] - self.pts[-1][0]) ** 2 + (p[1] - self.pts[-1][1]) ** 2 > 4:
                    self.pts.append(p)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'PRESS':
            self.drawing = True
            self.mode = 'SUB' if event.alt else ('ADD' if event.shift else 'SET')
            p = (event.mouse_region_x, event.mouse_region_y)
            self.pts = [p, p] if self.shape == 'RECT' else [p]
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'RELEASE' and self.drawing:
            self.drawing = False
            self.apply(context)
            self.pts = []
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if t == 'RIGHTMOUSE' and v == 'PRESS' and self.drawing:
            self.drawing, self.pts = False, []            # abandon this one, keep the tool
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if t in {'LEFTMOUSE', 'RIGHTMOUSE'}:
            return {'RUNNING_MODAL'}                    # never paint while selecting
        if v == 'PRESS' and t == 'ESC':
            self._finish(context)
            return {'FINISHED'}
        if v == 'PRESS' and not event.ctrl and t == ('L' if self.shape == 'LASSO' else 'M'):
            return {'RUNNING_MODAL'}                    # already this tool
        if v == 'PRESS' and t in cfg.LEAVE_SELECTION_KEYS and not self.drawing:
            self._finish(context)                       # another tool: let its key through
            return {'FINISHED', 'PASS_THROUGH'}
        return {'RUNNING_MODAL'} if self.drawing else {'PASS_THROUGH'}

    def apply(self, context):
        w, h = pixels.size()
        if self.shape == 'RECT':
            (ax, ay), (bx, by) = (pixels.canvas_point(context, *p) for p in (self.pts[0], self.pts[-1]))
            if abs(ax - bx) < 1 and abs(ay - by) < 1:     # a click: deselect (like Photoshop)
                if self.mode == 'SET':
                    clear(context)
                    pixels.undo_push("Deselect")
                return
            new = shapes.rect_mask(ax, ay, bx, by, w, h)
        else:
            if len(self.pts) < 3:
                if self.mode == 'SET':
                    clear(context)
                    pixels.undo_push("Deselect")
                return
            new = shapes.polygon_mask([pixels.canvas_point(context, *p) for p in self.pts], w, h)
        set_mask(context, shapes.combine(mask(context), new, self.mode))
        pixels.undo_push("Select")


# --- selection actions ---------------------------------------------------------------------

class _CanvasOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_TEXTURE' and pixels.material() is not None


class PLASTRON_OT_select_none(_CanvasOp, bpy.types.Operator):
    """Deselect (Ctrl+D)"""
    bl_idname = "plastron.select_none"
    bl_label = "Deselect"

    def execute(self, context):
        clear(context)
        return {'FINISHED'}


class PLASTRON_OT_select_all(_CanvasOp, bpy.types.Operator):
    """Select the whole canvas (Ctrl+A)"""
    bl_idname = "plastron.select_all"
    bl_label = "Select All"

    def execute(self, context):
        w, h = pixels.size()
        set_mask(context, np.ones((h, w), np.float32))
        return {'FINISHED'}


class PLASTRON_OT_select_invert(_CanvasOp, bpy.types.Operator):
    """Select everything that isn't selected (Ctrl+Shift+I)"""
    bl_idname = "plastron.select_invert"
    bl_label = "Invert Selection"

    def execute(self, context):
        m = mask(context)
        w, h = pixels.size()
        set_mask(context, np.ones((h, w), np.float32) if m is None else 1.0 - m)
        return {'FINISHED'}


class PLASTRON_OT_select_erase(_CanvasOp, bpy.types.Operator):
    """Erase the selected pixels of the active layer (Delete)"""
    bl_idname = "plastron.select_erase"
    bl_label = "Erase Selected"

    def execute(self, context):
        mat = pixels.material()
        layer = pixels.paint_layer(mat)
        m = mask(context)
        if layer is None or m is None:
            self.report({'INFO'}, "Select something on a paint layer first")
            return {'CANCELLED'}
        a = pixels.array(layer.paint_image).copy()
        a[..., 3] *= 1.0 - m
        pixels.replace_image(mat, layer.uid, a)
        return {'FINISHED'}


classes = (PLASTRON_OT_select_tool, PLASTRON_OT_select_none, PLASTRON_OT_select_all,
           PLASTRON_OT_select_invert, PLASTRON_OT_select_erase)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.plastron_selection = bpy.props.PointerProperty(type=bpy.types.Image)
    handlers.add("undo_post", _after_undo)
    handlers.add("redo_post", _after_undo)
    handlers.on_load(apply_stencil)
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    for handle in _handles:
        bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
    _handles.clear()
    del bpy.types.Scene.plastron_selection
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
