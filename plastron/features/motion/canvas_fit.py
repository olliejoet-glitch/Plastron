"""The painting grows to fit its camera move (the brief's "oversized canvas";
Ollie couldn't paint where the camera had panned past the painting's edge).

Shortly after a camera move stops changing, every frame position along the
move (both ends, the easing in between, overshoot, shake) is checked; if
any part of a frame falls outside the painting, the painting is made bigger
around the middle (stack.pad_canvas: every layer keeps its place; one undo
step). It never shrinks, and stops at CANVAS_FIT["max"] frame widths.
"""

import math
import time

import bpy

from ...config import motion as cfg
from ...layers import stack as stack_ops
from ...widgets import dot_graph
from ..storyboard import canvas_sync
from . import camera

FIT = cfg.CANVAS_FIT
_pending = {"strips": set(), "last": 0.0}


def needed_size(strip):
    """(width, height) in pixels the painting needs for its camera move, or
    None if it already fits."""
    mat = strip.plastron_panel.material
    if mat is None or not mat.plastron_stack.enabled or not camera.moves(strip):
        return None
    st = mat.plastron_stack
    fw, fh = canvas_sync.frame_px(st)
    m = strip.plastron_motion
    a, b = camera.as_tuple(m.start), camera.as_tuple(m.end)
    half = [(sx * 0.5, sy * 0.5 * fh / fw) for sx in (-1, 1) for sy in (-1, 1)]   # frame widths
    reach_x = reach_y = 0.0
    for i in range(FIT["samples"] + 1):
        x, y, zoom, rot = camera.blend(a, b, dot_graph.evaluate(m.curve, i / FIT["samples"]))
        c, s = math.cos(rot), math.sin(rot)
        for hx, hy in half:
            reach_x = max(reach_x, abs(x / 100 + (hx * c - hy * s) / zoom))
            reach_y = max(reach_y, abs(y / 100 + (hx * s + hy * c) / zoom))
    extra = FIT["margin"] + m.shake / 100 * 1.5
    step = FIT["step_px"]
    want_w = math.ceil(min(FIT["max"], 2 * (reach_x + extra)) * fw / step) * step
    want_h = math.ceil(min(FIT["max"] * fh / fw, 2 * (reach_y + extra)) * fw / step) * step
    if want_w <= st.width and want_h <= st.height:
        return None
    return max(want_w, st.width), max(want_h, st.height)


def fit(strip):
    """Grow strip's painting if its camera move needs it. True if it grew."""
    size = needed_size(strip)
    if size is None:
        return False
    mat = strip.plastron_panel.material
    frame = canvas_sync.frame_px(mat.plastron_stack)
    grown = stack_ops.pad_canvas(mat, size[0], size[1], frame)
    if grown:
        from ..canvas_edit import selection
        scene = strip.id_data
        try:
            selection.clear(bpy.context)          # a selection made at the old size
        except Exception:
            pass
        canvas_sync.invalidate(scene)
    return grown


def request(strip):
    _pending["strips"].add(strip.name)
    _pending["last"] = time.monotonic()
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=FIT["delay"])


def _timer():
    wait = FIT["delay"] - (time.monotonic() - _pending["last"])
    if wait > 0.01:
        return wait                        # the camera's still being moved
    from ..storyboard import stroke_guard
    if stroke_guard.busy():
        return 0.25                        # never swap images under a brush stroke (crashed)
    names, _pending["strips"] = _pending["strips"], set()
    scene = bpy.context.scene
    sed = scene.sequence_editor if scene else None
    grew = False
    for name in names:
        strip = sed.strips_all.get(name) if sed else None
        if strip is not None:
            grew = fit(strip) or grew
    if grew:
        wm = bpy.context.window_manager
        window = wm.windows[0] if wm and wm.windows else None
        if window is not None:
            with bpy.context.temp_override(window=window):
                try:
                    bpy.ops.ed.undo_push(message="Canvas grown to fit the camera")
                except RuntimeError:
                    pass
    return None


def fit_all(scene):
    """Every panel (projects whose camera moves went past their painting)."""
    from ..storyboard.panels import all_panels
    if scene is None or getattr(scene, "sequence_editor", None) is None:
        return
    for strip in all_panels(scene):
        fit(strip)


def unregister():
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
