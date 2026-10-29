"""Shows the panel(s) under the playhead on the canvas.

- "Canvas" is the sheet you paint on (a flat mesh facing the camera, in
  Texture Paint mode). It always stays the active object; it's simply handed
  the layer-stack material of the panel you're drawing on, and painting is
  aimed at that panel's active layer. Swapping materials is cheap and keeps
  paint mode, so you can scrub and draw straight away.
- Each other video track has a display-only sheet showing its clip under the
  playhead, stacked by track order, so backgrounds show under panels.
- Onion skin (if on): two more sheets just behind the canvas show the panels
  before and after the one you're drawing on, faintly (object alpha, which
  every panel material multiplies in).

Performance: the frame-change hook is O(1) while the playhead stays inside
the same stretch of panels (between two clip edges); it only does work when
crossing a clip edge or after an edit.
"""

import bpy

from ...config import project_defaults as defaults
from ...core import handlers
from ...layers import paint_target
from ...timeline import clips, events, tracks

CANVAS = "Canvas"
DISPLAY_PREFIX = "Canvas Track "
ONION = ("Canvas Onion Before", "Canvas Onion After")
SHEET = "Canvas Sheet"
EMPTY = "Plastron Empty Panel"
DEPTH_STEP = 0.01     # higher tracks sit slightly nearer the camera

_state = {"dirty": True, "lo": 0, "hi": -1, "scene": None, "work": 0}


def sheet_size():
    """Width, height of the painted sheet in canvas units (camera frame + bleed)."""
    pw, ph = defaults.PAINT_RESOLUTION
    width = defaults.CANVAS_WIDTH * pw / defaults.PAINT_FRAME[0]
    return width, width * ph / pw


def sheet_mesh():
    me = bpy.data.meshes.get(SHEET)
    if me is None:
        w, h = (s / 2 for s in sheet_size())
        me = bpy.data.meshes.new(SHEET)
        me.from_pydata([(-w, 0, -h), (w, 0, -h), (w, 0, h), (-w, 0, h)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UV")
        for i, co in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
            uv.data[i].uv = co
        me.materials.append(None)
    return me


def empty_material():
    """Shown where a track has no panel: fully transparent."""
    mat = bpy.data.materials.get(EMPTY)
    if mat is None:
        mat = bpy.data.materials.new(EMPTY)
        mat.use_nodes = True
        mat.surface_render_method = 'BLENDED'
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], out.inputs["Surface"])
    return mat


def _sheet_object(scene, name, selectable):
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type != 'MESH':      # a stage-2 (grease pencil) project
        obj.name = name + " (old)"
        obj.hide_viewport = True
        obj = None
    if obj is None:
        obj = bpy.data.objects.new(name, sheet_mesh())
        obj.hide_select = not selectable
        scene.collection.objects.link(obj)
    slot = obj.material_slots[0]
    if slot.link != 'OBJECT':
        slot.link = 'OBJECT'
    return obj


def canvas_object(scene):
    return _sheet_object(scene, CANVAS, True)


def _display_object(scene, track):
    return _sheet_object(scene, DISPLAY_PREFIX + track.uid, False)


def _set(obj, material=None, y=None, hidden=None, alpha=None):
    """Change only what differs (every change costs a scene update)."""
    if alpha is not None and abs(obj.color[3] - alpha) > 1e-4:
        obj.color[3] = alpha
    slot = obj.material_slots[0]
    if material is not None and slot.material != material:
        slot.material = material
    if y is not None and abs(obj.location.y - y) > 1e-6:
        obj.location.y = y
    if hidden is not None and obj.hide_viewport != hidden:
        obj.hide_viewport = hidden


def _material_at(scene, track, frame):
    from .panels import is_panel
    clip = clips.at(scene, tracks.channel_of(scene, track), frame)
    if clip and is_panel(clip) and clip.plastron_panel.material:
        return clip.plastron_panel.material
    return None


def _onion(scene, track, frame, y):
    """Show the panels either side of track's clip at frame (or hide them)."""
    from . import onion
    from .panels import is_panel
    channel = tracks.channel_of(scene, track) if track else None
    current = clips.at(scene, channel, frame) if track else None
    show = onion.enabled() and current is not None and is_panel(current)
    near = (clips.previous_before(scene, channel, clips.start(current)) if show else None,
            clips.next_after(scene, channel, clips.end(current)) if show else None)
    for name, clip in zip(ONION, near):
        mat = clip.plastron_panel.material if clip is not None and is_panel(clip) else None
        obj = _sheet_object(scene, name, False)
        _set(obj, material=mat or empty_material(), y=y + DEPTH_STEP / 2, hidden=mat is None,
             alpha=onion.opacity())


def _drawable(scene, track, frame, sed):
    ch = sed.channels[tracks.channel_of(scene, track)]
    return not ch.mute and not ch.lock and _material_at(scene, track, frame) is not None


def _drawing_track(scene, videos, frame, sed):
    """The track you draw on: the active track if it has a panel under the
    playhead, else the topmost visible, unlocked video track that does. So
    scrubbing onto any panel is enough to draw on it; the active track
    (where new panels go) isn't changed."""
    active = tracks.active(scene)
    if active and active.kind == 'VIDEO' and _drawable(scene, active, frame, sed):
        return active
    for track in reversed(videos):
        if _drawable(scene, track, frame, sed):
            return track
    if active and active.kind == 'VIDEO':
        return active
    return videos[-1] if videos else None


def sync(scene):
    """Recompute what the canvas shows at the current frame."""
    _state["work"] += 1
    frame = scene.frame_current
    empty = empty_material()
    videos = tracks.video_tracks(scene)
    sed = clips.editor(scene)
    active = _drawing_track(scene, videos, frame, sed)

    for depth, track in enumerate(videos):
        y = -depth * DEPTH_STEP
        muted = sed.channels[tracks.channel_of(scene, track)].mute
        material = None if muted else _material_at(scene, track, frame)
        if active and track.uid == active.uid:
            _set(canvas_object(scene), material=material or empty, y=y)
            _set(_display_object(scene, track), material=empty, hidden=True)
        else:
            _set(_display_object(scene, track), material=material or empty, y=y,
                 hidden=material is None)
    canvas_y = -[t.uid for t in videos].index(active.uid) * DEPTH_STEP if active else 0.0
    _onion(scene, active, frame, canvas_y)
    paint_target.sync(scene=scene)

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


def panel_on_canvas(scene):
    """The panel clip being drawn on, or None."""
    from .panels import all_panels
    mat = paint_target.active_material()
    return next((s for s in all_panels(scene) if s.plastron_panel.material == mat), None) \
        if mat is not None else None


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
