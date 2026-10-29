"""Shared bits for our modal tools: let viewport navigation through, chain into another tool."""
import bpy

NAV_EVENTS = {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE',
              'TRACKPADPAN', 'TRACKPADZOOM', 'MOUSEROTATE', 'MOUSESMARTZOOM', 'HOME'}


def is_navigation(event, allow_alt_lmb=True):
    t = event.type
    if t in NAV_EVENTS or t.startswith('NDOF_'):
        return True
    if t.startswith('NUMPAD_') and t not in ('NUMPAD_ENTER',):
        return True
    # Alt+LMB orbits ("Emulate 3 button mouse" / industry keymaps): never ours
    return allow_alt_lmb and t == 'LEFTMOUSE' and event.alt


def chain(context, op_idname, **props):
    """Start another tool right after the current modal operator returns."""
    win, area, region = context.window, context.area, context.region

    def go():
        try:
            with bpy.context.temp_override(window=win, area=area, region=region):
                getattr(getattr(bpy.ops, op_idname.split(".")[0]), op_idname.split(".")[1])(
                    'INVOKE_DEFAULT', **props)
        except Exception as e:
            print("CaraPainter: could not start", op_idname, e)
        return None

    bpy.app.timers.register(go, first_interval=0.01)
