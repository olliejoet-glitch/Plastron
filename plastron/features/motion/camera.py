"""Camera moves: each panel's camera frame has a start and an end position
(pan, zoom, a slight rotation), eased by a dot graph, plus an optional shake.

Nothing is animated in Blender: the scene camera never moves. Where the
frame is at a frame is worked out when it's needed (the canvas overlay as it
draws, the panel's image, later the animatic export), so playback costs
nothing extra.

    strip.plastron_motion.start / .end   x, y (% of the frame width), zoom, rotation
    strip.plastron_motion.curve          easing (dot graph id)
    strip.plastron_motion.shake / .shake_speed
"""

import math
import zlib

import bpy

from ...config import motion as cfg
from ...timeline import clips
from ...widgets import dot_graph


def _changed(self, context):
    """A position changed: redraw the canvas; the panel's image shows the start."""
    from . import thumbnails
    thumbnails.camera_changed(self)
    bump()
    from . import view_follow
    view_follow.follow()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class PLASTRON_PG_camera_state(bpy.types.PropertyGroup):
    x: bpy.props.FloatProperty(name="X", description="Left / right, in % of the frame width",
                               subtype='PERCENTAGE', soft_min=-100, soft_max=100, precision=1,
                               update=_changed)
    y: bpy.props.FloatProperty(name="Y", description="Up / down, in % of the frame width",
                               subtype='PERCENTAGE', soft_min=-100, soft_max=100, precision=1,
                               update=_changed)
    zoom: bpy.props.FloatProperty(name="Zoom", description="1 = the normal frame, 2 = twice as close",
                                  default=1.0, min=cfg.ZOOM_RANGE[0], max=cfg.ZOOM_RANGE[1],
                                  precision=2, step=5, update=_changed)
    rotation: bpy.props.FloatProperty(name="Rotation", subtype='ANGLE',
                                      min=-math.radians(cfg.ROTATION_LIMIT),
                                      max=math.radians(cfg.ROTATION_LIMIT), update=_changed)


class PLASTRON_PG_motion(bpy.types.PropertyGroup):
    start: bpy.props.PointerProperty(type=PLASTRON_PG_camera_state)
    end: bpy.props.PointerProperty(type=PLASTRON_PG_camera_state)
    curve: bpy.props.StringProperty()
    shake: bpy.props.FloatProperty(name="Shake", description="How much the camera shakes, % of the frame width",
                                   subtype='PERCENTAGE', min=0.0, max=cfg.SHAKE_AMOUNT_MAX, precision=2,
                                   step=5, update=_changed)
    shake_speed: bpy.props.FloatProperty(name="Speed", description="Wobbles per second",
                                         default=6.0, min=cfg.SHAKE_SPEED_RANGE[0],
                                         max=cfg.SHAKE_SPEED_RANGE[1], update=_changed)


REST = (0.0, 0.0, 1.0, 0.0)


def as_tuple(state):
    return (state.x, state.y, state.zoom, state.rotation)


def set_state(state, values):
    for attr, v in zip(("x", "y", "zoom", "rotation"), values):
        if abs(getattr(state, attr) - v) > 1e-9:
            setattr(state, attr, v)


def moves(strip):
    """Does this panel's camera do anything?"""
    m = strip.plastron_motion
    same = lambda a, b: all(abs(p - q) < 1e-6 for p, q in zip(a, b))
    return m.shake > 1e-6 or not (same(as_tuple(m.start), REST) and same(as_tuple(m.end), REST))


def clip_time(strip, frame):
    """0 at the panel's first frame, 1 at its last."""
    s, e = clips.start(strip), clips.end(strip)
    return min(1.0, max(0.0, (frame - s) / max(1, e - 1 - s)))


def _noise(t, seed):
    """Smooth wobble in -1..1 (a few sines at unrelated speeds)."""
    p = [(seed >> (8 * k) & 255) / 255 * math.tau for k in range(3)]
    return (math.sin(math.tau * t + p[0]) + 0.6 * math.sin(math.tau * 2.13 * t + p[1])
            + 0.3 * math.sin(math.tau * 3.71 * t + p[2])) / 1.9


def shake_offset(strip, seconds):
    """(dx, dy, rotation) the shake adds at this time."""
    m = strip.plastron_motion
    if m.shake <= 1e-6:
        return 0.0, 0.0, 0.0
    seed = zlib.crc32((strip.plastron_panel.uid or strip.name).encode())
    t = seconds * m.shake_speed
    return (m.shake * _noise(t, seed), m.shake * _noise(t + 17.3, seed >> 3),
            math.radians(cfg.SHAKE_ROTATION * m.shake) * _noise(t + 41.7, seed >> 5))


def blend(a, b, e):
    """State between a and b at eased amount e (zoom blends evenly in scale)."""
    za, zb = max(a[2], 1e-3), max(b[2], 1e-3)
    return (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e,
            za * (zb / za) ** e, a[3] + (b[3] - a[3]) * e)


def state_at(strip, frame, fps=None, shake=True):
    """(x, y, zoom, rotation) of the panel's camera at a frame."""
    m = strip.plastron_motion
    e = dot_graph.evaluate(m.curve, clip_time(strip, frame))
    x, y, z, r = blend(as_tuple(m.start), as_tuple(m.end), e)
    if shake and m.shake > 1e-6:
        fps = fps or 24.0
        dx, dy, dr = shake_offset(strip, (frame - clips.start(strip)) / fps)
        x, y, r = x + dx, y + dy, r + dr
    return x, y, z, r


def corners(base, state):
    """The scene camera's frame corners (world) moved to a state."""
    x, y, zoom, rot = state
    cx = sum(c.x for c in base) / 4
    cz = sum(c.z for c in base) / 4
    width = (base[0] - base[3]).length
    cos, sin = math.cos(rot), math.sin(rot)
    out = []
    for c in base:
        rx, rz = (c.x - cx) / zoom, (c.z - cz) / zoom
        p = c.copy()
        p.x = cx + x / 100 * width + rx * cos - rz * sin
        p.z = cz + y / 100 * width + rx * sin + rz * cos
        out.append(p)
    return out


def crop(state, frame_crop):
    """A state's frame as a crop of the painting (rotation left out)."""
    x0, y0, fw, fh = frame_crop
    x, y, zoom, _rot = state
    cx, cy = x0 + fw / 2 + x / 100 * fw, y0 + fh / 2 + y / 100 * fw
    w, h = fw / zoom, fh / zoom
    return (cx - w / 2, cy - h / 2, w, h)


_edits = [0]
_shot = {"key": None, "name": ""}


def bump():
    """Motion changed (cached answers below are worked out again)."""
    _edits[0] += 1


def shot(scene):
    """The panel whose camera the canvas shows: the one being drawn on.
    Cached until the canvas changes panel or anything is edited (the frame
    hook asks every frame)."""
    from ..storyboard import canvas_sync
    sed = scene.sequence_editor
    if sed is None:
        return None
    key = (canvas_sync._state["work"], scene.name, _edits[0])
    if key != _shot["key"]:
        strip = canvas_sync.panel_on_canvas(scene)
        _shot.update(key=key, name=strip.name if strip else "")
    return sed.strips_all.get(_shot["name"]) if _shot["name"] else None


def frame_provider(context):
    """canvas_frame hook: the moved frame at the playhead (or None)."""
    from ..storyboard.canvas_view import camera_frame
    scene = context.scene
    strip = shot(scene)
    if strip is None or not moves(strip):
        return None
    base = camera_frame(scene)
    if not base:
        return None
    fps = scene.render.fps / scene.render.fps_base
    return corners(base, state_at(strip, scene.frame_current, fps))


classes = (PLASTRON_PG_camera_state, PLASTRON_PG_motion)
