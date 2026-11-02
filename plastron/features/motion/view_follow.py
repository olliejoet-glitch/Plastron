"""Camera view: the canvas looks through the camera. The frame stays where
it is on screen and the drawing pans, zooms and turns behind it, as the
playhead moves (also during playback) and while a move is being set.

Only the canvas view (a UI setting, not scene data) changes, so nothing in
the project is re-evaluated. Each view remembers which camera state it has
taken on, and is moved by the difference, so your own panning / zooming /
rotating of the canvas is kept. Fitting the canvas (Ctrl+0) starts afresh.

The Camera View toggle (options bar, remembered) switches to the stage view:
the drawing stays still and the frame moves over it.
"""

import math

import bpy
from mathutils import Quaternion, Vector

from ...core import user_settings
from ...core.views import is_canvas
from . import camera

SETTING = "camera_view"
REST = camera.REST
_applied = {}          # region_3d pointer -> camera state the view has taken on


def enabled():
    return bool(user_settings.get(SETTING, True))


# --- the camera's mapping (canvas plane: x across, z up) -----------------------------------

def base():
    """(centre, width) of the scene camera's frame, or None."""
    from ..storyboard.canvas_view import camera_frame
    corners = camera_frame(bpy.context.scene)
    if not corners:
        return None
    return sum(corners, Vector()) / 4, (corners[0] - corners[3]).length


def forward(p, state, centre, width):
    """Where the camera in state puts point p of the normal frame (world)."""
    x, y, zoom, rot = state
    rx, rz = (p.x - centre.x) / zoom, (p.z - centre.z) / zoom
    c, s = math.cos(rot), math.sin(rot)
    return Vector((centre.x + x / 100 * width + rx * c - rz * s, p.y,
                   centre.z + y / 100 * width + rx * s + rz * c))


def backward(p, state, centre, width):
    x, y, zoom, rot = state
    qx, qz = p.x - centre.x - x / 100 * width, p.z - centre.z - y / 100 * width
    c, s = math.cos(-rot), math.sin(-rot)
    return Vector((centre.x + (qx * c - qz * s) * zoom, p.y, centre.z + (qx * s + qz * c) * zoom))


def linear(v, state):
    """The camera's turn and scale only (for a drag's direction)."""
    _x, _y, zoom, rot = state
    c, s = math.cos(rot), math.sin(rot)
    return Vector(((v.x * c - v.z * s) / zoom, 0.0, (v.x * s + v.z * c) / zoom))


# --- moving views -------------------------------------------------------------------------

def applied(r3d):
    return _applied.get(r3d.as_pointer(), REST)


def _close(a, b):
    return all(abs(p - q) < 1e-7 for p, q in zip(a, b))


def apply_view(r3d, state, frame=None):
    """Make a canvas view look through the camera in state."""
    old = applied(r3d)
    if _close(old, state):
        return False
    frame = frame or base()
    if frame is None:
        return False
    centre, width = frame
    home = backward(r3d.view_location, old, centre, width)
    r3d.view_location = forward(home, state, centre, width)
    r3d.view_distance = r3d.view_distance * old[2] / state[2]
    # The frame turned anticlockwise (seen from the front) = about -Y.
    r3d.view_rotation = Quaternion((0.0, -1.0, 0.0), state[3] - old[3]) @ r3d.view_rotation
    _applied[r3d.as_pointer()] = tuple(state)
    return True


def views():
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D' and is_canvas(area.spaces.active):
                yield area, area.spaces.active.region_3d


def wanted(scene):
    """The camera state the canvas should look through now."""
    if not enabled():
        return REST
    strip = camera.shot(scene)
    if strip is None or not camera.moves(strip):
        return REST
    fps = scene.render.fps / scene.render.fps_base
    return camera.state_at(strip, scene.frame_current, fps)


def follow(scene=None):
    """Every canvas view to the camera at the playhead (cheap: a few numbers)."""
    scene = scene or bpy.context.scene
    if scene is None or not hasattr(scene, "plastron_timeline"):
        return
    state = wanted(scene)
    frame = None
    for area, r3d in views():
        if _close(applied(r3d), state):
            continue
        frame = frame or base()
        if apply_view(r3d, state, frame):
            area.tag_redraw()


def after_fit(r3d):
    """canvas_view hook: a fitted view shows the normal frame; then follow."""
    _applied[r3d.as_pointer()] = REST
    state = wanted(bpy.context.scene)
    if not _close(state, REST):
        apply_view(r3d, state)


def _get(_self):
    return enabled()


def _set(_self, value):
    user_settings.set(SETTING, bool(value))
    follow()


def register():
    from ..storyboard import canvas_view
    canvas_view.AFTER_FIT.append(after_fit)
    bpy.types.WindowManager.plastron_camera_view = bpy.props.BoolProperty(
        name="Camera View",
        description="Look through the camera: the frame stays still and the drawing moves behind it "
                    "(off: the frame moves over the drawing)",
        get=_get, set=_set)


def unregister():
    from ..storyboard import canvas_view
    if after_fit in canvas_view.AFTER_FIT:
        canvas_view.AFTER_FIT.remove(after_fit)
    del bpy.types.WindowManager.plastron_camera_view
    _applied.clear()
