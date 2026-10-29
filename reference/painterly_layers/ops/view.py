"""Base-colour view, colour picker and brush helpers (ARCHITECTURE §10).

Base view = scene attribute pl_base_view read by the material's View Switch (a uniform: instant,
no recompile) + view transform temporarily set to Standard so screen pixels equal stack values.
"""
import bpy
from bpy.props import BoolProperty, IntProperty

from .attach import BASE_VIEW

PREV_VT = "pl_prev_view_transform"


def in_painterly(context):
    ws = context.workspace
    return ws is not None and bool(ws.get("pl_painterly"))


def _redraw(context):
    context.scene.update_tag()
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def base_view_active(scene):
    return scene.get(BASE_VIEW, 0.0) > 0.5


def set_base_view(context, on):
    sc = context.scene
    vs = sc.view_settings
    if on and not base_view_active(sc):
        sc[PREV_VT] = vs.view_transform
        vs.view_transform = 'Standard'
    elif not on and base_view_active(sc):
        vs.view_transform = sc.get(PREV_VT, vs.view_transform)
    sc[BASE_VIEW] = 1.0 if on else 0.0
    _redraw(context)


def _brush(context):
    ip = context.tool_settings.image_paint
    return ip.brush if ip else None


class _ToggleBaseView:
    # (shared by two operators: never subclass a REGISTERED operator class, that breaks the
    # parent's Python class lookup and its hotkey/button silently stop working)
    bl_label = "Flat Colour View"
    bl_description = "Show the unlit base colour of the layer stack (C). Click again to return"

    def execute(self, context):
        on = not base_view_active(context.scene)
        if on:
            from .formview import form_view_active, set_form_view
            if form_view_active(context.scene):
                set_form_view(context, False)
        set_base_view(context, on)
        return {'FINISHED'}


class PL_OT_toggle_base_view(_ToggleBaseView, bpy.types.Operator):
    bl_idname = "pl.toggle_base_view"


class PL_OT_toggle_base_view_key(_ToggleBaseView, bpy.types.Operator):
    """C in Object Mode: only inside the CaraPainter workspace (else Blender's circle select)."""
    bl_idname = "pl.toggle_base_view_key"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return in_painterly(context)


def _decode(c):
    return [x / 12.92 if x < 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def sample_base_colour(context, x, y):
    """sRGB colour of the UNLIT layer stack at region pixel (x, y), without touching the visible
    viewport: the flat view is drawn into an offscreen buffer for this one sample, then every
    setting is restored before the viewport redraws."""
    import gpu
    sc, space, region, rv3d = context.scene, context.space_data, context.region, context.region_data
    if space is None or space.type != 'VIEW_3D' or rv3d is None or region is None:
        return None
    vs = sc.view_settings
    saved = (sc.get(BASE_VIEW, 0.0), vs.view_transform, vs.look, vs.exposure, vs.gamma,
             space.overlay.show_overlays)
    try:
        sc[BASE_VIEW] = 1.0
        vs.view_transform, vs.look, vs.exposure, vs.gamma = 'Standard', 'None', 0.0, 1.0
        space.overlay.show_overlays = False
        sc.update_tag()
        context.evaluated_depsgraph_get().update()
        off = gpu.types.GPUOffScreen(region.width, region.height)
        try:
            off.draw_view3d(sc, context.view_layer, space, region, rv3d.view_matrix,
                            rv3d.window_matrix, do_color_management=True)
            with off.bind():
                fb = gpu.state.active_framebuffer_get()
                buf = fb.read_color(int(x), int(y), 1, 1, 4, 0, 'FLOAT')
            buf.dimensions = 4
            rgb = [float(v) for v in buf[:3]]
        finally:
            off.free()
    finally:
        sc[BASE_VIEW] = saved[0]
        vs.view_transform, vs.look, vs.exposure, vs.gamma = saved[1:5]
        space.overlay.show_overlays = saved[5]
        sc.update_tag()
    return rgb


def set_brush_colour(context, srgb):
    """Brush colours are scene-linear in Blender 5: decode the picked sRGB value."""
    lin = _decode(srgb)
    ip = context.tool_settings.image_paint
    ups = ip.unified_paint_settings
    if ups.use_unified_color:
        ups.color = lin
    if ip.brush is not None:
        ip.brush.color = lin


class PL_OT_pick_color(bpy.types.Operator):
    """Z: eyedropper for the colour you see (lit). Tap = pick under the cursor; hold, click to
    pick, release to finish. Shift+Z: the unlit paint (base colour) instead."""
    bl_idname = "pl.pick_color"
    bl_label = "Pick Colour"
    bl_options = {'REGISTER'}
    lit: BoolProperty(name="Lit Colour", default=False)

    @classmethod
    def poll(cls, context):
        return in_painterly(context) and context.mode == 'PAINT_TEXTURE'

    def _pick(self, context, x, y):
        try:
            if self.lit:
                bpy.ops.paint.sample_color(location=(int(x), int(y)), merged=True, palette=False)
            else:
                rgb = sample_base_colour(context, x, y)
                if rgb is not None:
                    set_brush_colour(context, rgb)
        except Exception as e:  # never leave the user stuck in a modal picker
            self.report({'WARNING'}, f"Pick failed: {e}")

    def invoke(self, context, event):
        self.key = event.type
        self.xy = (event.mouse_region_x, event.mouse_region_y)
        self.picked = False
        from ..ui import hud
        hud.tool_mode(context, True)
        hud.set_label("Eyedropper" if self.lit else "Eyedropper (unlit paint)")
        context.window.cursor_modal_set('EYEDROPPER')
        context.workspace.status_text_set("Eyedropper: click to pick, release Z to finish"
                                          + ("" if self.lit else " (unlit paint, no lighting)"))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        from ..ui import hud
        hud.tool_mode(context, False)
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)

    def modal(self, context, event):
        from ..ui import hud
        hud.set_mouse(event)
        if event.type == 'MOUSEMOVE':
            self.xy = (event.mouse_region_x, event.mouse_region_y)
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._pick(context, *self.xy)
            self.picked = True
        elif event.type == self.key and event.value == 'RELEASE':
            if not self.picked:  # quick tap: pick where the cursor is
                self._pick(context, *self.xy)
            self._finish(context)
            return {'FINISHED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            self._finish(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class PL_OT_brush_tool(bpy.types.Operator):
    bl_idname = "pl.brush_tool"
    bl_label = "Brush Tool"
    bl_description = "Back to the paint brush, eraser off (B)"

    @classmethod
    def poll(cls, context):
        return in_painterly(context) and context.mode == 'PAINT_TEXTURE'

    def execute(self, context):
        for tool in ("builtin.brush", "builtin_brush.Draw", "builtin_brush.draw"):
            try:
                bpy.ops.wm.tool_set_by_id(name=tool)
                break
            except (RuntimeError, TypeError):
                continue
        b = _brush(context)
        if b is not None and b.blend == 'ERASE_ALPHA':
            b.blend = b.get("pl_prev_blend", 'MIX')
        return {'FINISHED'}


class PL_OT_brush_size(bpy.types.Operator):
    bl_idname = "pl.brush_size"
    bl_label = "Brush Size Step"
    bl_description = "Make the brush smaller / bigger (Q / W)"
    step: IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        return in_painterly(context) and context.mode == 'PAINT_TEXTURE'

    def execute(self, context):
        ups = context.tool_settings.image_paint.unified_paint_settings  # per paint mode in 5.x
        brush = _brush(context)
        factor = 1.15 if self.step > 0 else 1 / 1.15
        if ups.use_unified_size or brush is None:
            ups.size = max(1, min(5000, round(ups.size * factor) + (1 if self.step > 0 else 0)))
        else:
            brush.size = max(1, min(5000, round(brush.size * factor) + (1 if self.step > 0 else 0)))
        return {'FINISHED'}


class PL_OT_eraser_toggle(bpy.types.Operator):
    bl_idname = "pl.eraser_toggle"
    bl_label = "Toggle Eraser"
    bl_description = "Switch the current brush between painting and erasing alpha (E)"

    @classmethod
    def poll(cls, context):
        return in_painterly(context) and context.mode == 'PAINT_TEXTURE' and _brush(context) is not None

    def execute(self, context):
        b = _brush(context)
        if b.blend == 'ERASE_ALPHA':
            b.blend = b.get("pl_prev_blend", 'MIX')
            self.report({'INFO'}, "Brush")
        else:
            b["pl_prev_blend"] = b.blend
            b.blend = 'ERASE_ALPHA'
            self.report({'INFO'}, "Eraser")
        return {'FINISHED'}


classes = (PL_OT_toggle_base_view, PL_OT_toggle_base_view_key, PL_OT_pick_color, PL_OT_brush_tool, PL_OT_brush_size,
           PL_OT_eraser_toggle)
