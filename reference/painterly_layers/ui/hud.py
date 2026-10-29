"""Tool label next to the cursor (CaraPainter workspace, Texture Paint mode).

Shows the active tool (Brush, Eraser, Fill, …). Modal tools (lasso, transform, eyedropper)
override it with what they are doing right now (Lasso: add, Scale, Rotate, Warp, …).

Blender's cursor-draw callback doesn't receive the mouse position, so a tiny pass-through
listener (only while in the CaraPainter workspace in Texture Paint) records it; our own modal
tools report it while they run (they consume mouse moves).
"""
import blf
import bpy

_state = {"text": None, "xy": None, "listening": False}
_handle = None


def set_mouse(event):
    _state["xy"] = (event.mouse_x, event.mouse_y)


def set_label(text):
    """Override the label (None = back to the active tool)."""
    _state["text"] = text


def tool_mode(context, on):
    """Entering / leaving one of our modal tools: hide Blender's brush circle while it runs."""
    ip = context.tool_settings.image_paint
    if on:
        if "brush_shown" not in _state:
            _state["brush_shown"] = ip.show_brush
        ip.show_brush = False
    else:
        ip.show_brush = _state.pop("brush_shown", True)
        set_label(None)


def tool_label(context):
    ws = context.workspace
    tool = ws.tools.from_space_view3d_mode(context.mode, create=False) if ws else None
    idname = tool.idname if tool else "builtin.brush"
    if idname == "builtin.brush" or idname.startswith("builtin_brush"):
        b = context.tool_settings.image_paint.brush
        return "Eraser" if b is not None and b.blend == 'ERASE_ALPHA' else "Brush"
    return idname.split(".")[-1].replace("_", " ").title()


def current_label(context):
    if _state["text"]:
        return _state["text"]
    label = tool_label(context)
    ob = context.object
    mat = ob.active_material if ob else None
    if mat is not None and mat.pl_stack.enabled:
        act = mat.pl_stack.active
        if act is not None and act.paint_target == "MASK" and act.active_mask is not None:
            label += " · depth correction" if act.active_mask.source == "DEPTH" else " · mask"
    return label


def _brush_radius(context):
    ip = context.tool_settings.image_paint
    ups = ip.unified_paint_settings
    if ups.use_unified_size or ip.brush is None:
        return ups.size
    return ip.brush.size


def _draw(*args):
    try:
        from ..ops.view import in_painterly
        ctx = bpy.context
        if ctx.mode != 'PAINT_TEXTURE' or not in_painterly(ctx) or ctx.region is None or _state["xy"] is None:
            return
        x, y = _state["xy"]  # cursor overlays draw in window coordinates
        scale = ctx.preferences.system.ui_scale
        off = 14 * scale if _state["text"] else max(14 * scale, _brush_radius(ctx) * 0.72)
        font = 0
        blf.size(font, 12 * scale)
        blf.enable(font, blf.SHADOW)
        blf.shadow(font, 3, 0, 0, 0, 0.9)
        blf.shadow_offset(font, 1, -1)
        blf.color(font, 1, 1, 1, 0.95)
        blf.position(font, x + off + 4, y - off - 12 * scale, 0)
        blf.draw(font, current_label(ctx))
        blf.disable(font, blf.SHADOW)
    except Exception as e:  # never break the viewport
        print("CaraPainter HUD:", e)


def _painterly_paint(win):
    ws = win.workspace
    vl = win.view_layer
    ob = vl.objects.active if vl else None
    return bool(ws.get("pl_painterly")) and ob is not None and ob.mode == 'TEXTURE_PAINT'


class PL_OT_cursor_listener(bpy.types.Operator):
    """Records the mouse position for the tool label. Passes every event through."""
    bl_idname = "pl.cursor_listener"
    bl_label = "CaraPainter Cursor Listener"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        _state["listening"] = True
        set_mouse(event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL', 'PASS_THROUGH'}

    def modal(self, context, event):
        if context.window is None or not _painterly_paint(context.window):
            _state["listening"] = False
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            set_mouse(event)
        return {'PASS_THROUGH'}


def _start_listener():
    """Timer: make sure the listener runs while a window is in CaraPainter + Texture Paint."""
    try:
        if not _state["listening"]:
            for win in bpy.context.window_manager.windows:
                if not _painterly_paint(win):
                    continue
                area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None)
                if area is None:
                    continue
                region = next(r for r in area.regions if r.type == 'WINDOW')
                with bpy.context.temp_override(window=win, area=area, region=region):
                    bpy.ops.pl.cursor_listener('INVOKE_DEFAULT')
                break
    except Exception as e:
        print("CaraPainter cursor listener:", e)
    return 0.5


def register():
    global _handle
    bpy.utils.register_class(PL_OT_cursor_listener)
    _handle = bpy.types.WindowManager.draw_cursor_add(_draw, (), 'VIEW_3D', 'WINDOW')
    bpy.app.timers.register(_start_listener, first_interval=1.0, persistent=True)


def unregister():
    global _handle
    if bpy.app.timers.is_registered(_start_listener):
        bpy.app.timers.unregister(_start_listener)
    if _handle is not None:
        bpy.types.WindowManager.draw_cursor_remove(_handle)
        _handle = None
    bpy.utils.unregister_class(PL_OT_cursor_listener)
    _state["listening"] = False
