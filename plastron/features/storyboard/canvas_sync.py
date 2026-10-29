"""Shows the panel(s) under the playhead on the canvas.

- "Canvas" is the one object you draw on. It always stays the active object
  in drawing mode; it's simply handed the drawing of the active panel (the
  active track's clip under the playhead). Swapping drawings is cheap and
  keeps drawing mode, so you can scrub and draw straight away.
- Each other video track has a display-only object showing its clip under
  the playhead, stacked by track order, so backgrounds show under panels.

Performance: the frame-change hook is O(1) while the playhead stays inside
the same stretch of panels (between two clip edges); it only does work when
crossing a clip edge or after an edit.
"""

import bpy

from ...core import handlers
from ...timeline import clips, events, tracks

CANVAS = "Canvas"
DISPLAY_PREFIX = "Canvas Track "
EMPTY = "Plastron Empty Drawing"
DEPTH_STEP = 0.01     # higher tracks sit slightly nearer the camera

_state = {"dirty": True, "lo": 0, "hi": -1, "scene": None, "work": 0}


def empty_drawing():
    gp = bpy.data.grease_pencils.get(EMPTY)
    return gp or bpy.data.grease_pencils.new(EMPTY)


def canvas_object(scene):
    obj = bpy.data.objects.get(CANVAS)
    if obj is None:
        obj = bpy.data.objects.new(CANVAS, empty_drawing())
        scene.collection.objects.link(obj)
    return obj


def _display_object(scene, track):
    name = DISPLAY_PREFIX + track.uid
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, empty_drawing())
        obj.hide_select = True
        scene.collection.objects.link(obj)
    return obj


def _set(obj, data=None, y=None, hidden=None):
    """Change only what differs (every change costs a scene update)."""
    if data is not None and obj.data != data:
        obj.data = data
    if y is not None and abs(obj.location.y - y) > 1e-6:
        obj.location.y = y
    if hidden is not None and obj.hide_viewport != hidden:
        obj.hide_viewport = hidden


def _drawing_at(scene, track, frame):
    from .panels import is_panel
    clip = clips.at(scene, tracks.channel_of(scene, track), frame)
    if clip and is_panel(clip) and clip.plastron_panel.drawing:
        return clip.plastron_panel.drawing
    return None


def sync(scene):
    """Recompute what the canvas shows at the current frame."""
    _state["work"] += 1
    frame = scene.frame_current
    empty = empty_drawing()
    videos = tracks.video_tracks(scene)
    active = tracks.active(scene)
    if active is None or active.kind != 'VIDEO':
        active = videos[-1] if videos else None
    sed = clips.editor(scene)

    for depth, track in enumerate(videos):
        y = -depth * DEPTH_STEP
        muted = sed.channels[tracks.channel_of(scene, track)].mute
        drawing = None if muted else _drawing_at(scene, track, frame)
        if active and track.uid == active.uid:
            _set(canvas_object(scene), data=drawing or empty, y=y)
            _set(_display_object(scene, track), data=empty)
        else:
            _set(_display_object(scene, track), data=drawing or empty, y=y, hidden=drawing is None)

    # Remember the stretch of frames where this stays true.
    edges = sorted({e for s in clips.top_clips(scene)
                    for e in (clips.start(s), clips.end(s))})
    lo = max((e for e in edges if e <= frame), default=-10**9)
    hi = min((e for e in edges if e > frame), default=10**9)
    _state.update(dirty=False, lo=lo, hi=hi, scene=scene.name)


def on_frame(scene, *_args):
    # Per-frame hook: O(1) unless the playhead crossed a clip edge.
    if _state["dirty"] or scene.name != _state["scene"] or \
            not (_state["lo"] <= scene.frame_current < _state["hi"]):
        sync(scene)


def invalidate(scene, **_info):
    _state["dirty"] = True
    if scene is not None and hasattr(scene, "plastron_timeline"):
        sync(scene)


def _on_load(scene):
    if scene is None:
        return
    canvas = canvas_object(scene)
    view_layer = bpy.context.view_layer
    if view_layer and view_layer.objects.active != canvas:
        view_layer.objects.active = canvas
    invalidate(scene)


def register():
    for event in ("clips_changed", "tracks_changed", "active_track_changed"):
        events.listen(event, invalidate)
    handlers.on_load(_on_load)
    handlers.add("frame_change_post", on_frame)


def unregister():
    pass
