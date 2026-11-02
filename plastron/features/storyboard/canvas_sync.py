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
PAINT_SHEET = "Canvas Paint Sheet"     # the canvas's own (its UVs follow a moved layer)
EMPTY = "Plastron Empty Panel"
DEPTH_STEP = 0.01     # higher tracks sit slightly nearer the camera

_state = {"dirty": True, "lo": 0, "hi": -1, "scene": None, "work": 0, "canvas_track": ""}

# Hooks (features/scene3d): SHEET_PLACE: func(track) -> (offset xyz, rotation
# xyz, scale), where a track's sheet is placed in 3D (moved / turned / scaled
# in the 3D scene view; None: every sheet in the picture plane).
# SHEET_ABSORB: func(scene, obj, track): the sheet was moved by hand since
# the canvas last placed it: keep that on the track before re-placing it.
SHEET_PLACE = [None]
SHEET_ABSORB = [None]
_placed = {}     # sheet name -> (location, rotation, scale) as the canvas last set it


def _transform(obj):
    return tuple(obj.location), tuple(obj.rotation_euler), tuple(obj.scale)


def _absorb(scene, obj, track):
    """A sheet moved by hand (3D scene view) since we placed it: keep it."""
    last = _placed.get(obj.name)
    func = SHEET_ABSORB[0]
    if func is None or last is None or track is None:
        return
    now = _transform(obj)
    if any(abs(a - b) > 1e-6 for u, v in zip(now, last) for a, b in zip(u, v)):
        func(scene, obj, track)


def place(track):
    func = SHEET_PLACE[0]
    if func is None or track is None:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0
    return func(track)


def order_y(scene, track):
    """A track's sheet's depth before any 3D placement (higher tracks nearer)."""
    uids = [t.uid for t in tracks.video_tracks(scene)]
    return -uids.index(track.uid) * DEPTH_STEP if track.uid in uids else 0.0


def sheet_track(scene, obj):
    """The track a sheet object stands for right now (or None)."""
    if obj.name == CANVAS:
        uid = _state["canvas_track"]
    elif obj.name.startswith(DISPLAY_PREFIX):
        uid = obj.name[len(DISPLAY_PREFIX):]
    else:
        return None
    return next((t for t in tracks.video_tracks(scene) if t.uid == uid), None)


def frame_px(stack):
    """The camera frame's size in a painting's pixels (it sits in the middle)."""
    if stack.frame_w and stack.frame_h:
        return stack.frame_w, stack.frame_h
    return (stack.width * defaults.PAINT_FRAME[0] / defaults.PAINT_RESOLUTION[0],
            stack.height * defaults.PAINT_FRAME[1] / defaults.PAINT_RESOLUTION[1])


def sheet_size(stack=None):
    """Width, height in canvas units of a painting's sheet (camera frame +
    bleed; paintings grow to fit their camera moves). No stack: the
    standard size, which the shared sheet mesh has."""
    if stack is None or not stack.enabled:
        pw, ph = defaults.PAINT_RESOLUTION
        width = defaults.CANVAS_WIDTH * pw / defaults.PAINT_FRAME[0]
        return width, width * ph / pw
    per_px = defaults.CANVAS_WIDTH / frame_px(stack)[0]
    return stack.width * per_px, stack.height * per_px


def _scale_for(material):
    """Object scale that makes the standard sheet the material's painting size."""
    st = material.plastron_stack if material is not None else None
    if st is None or not st.enabled:
        return 1.0, 1.0
    (w, h), (sw, sh) = sheet_size(st), sheet_size()
    return w / sw, h / sh


def sheet_mesh(name=SHEET):
    me = bpy.data.meshes.get(name)
    if me is None:
        w, h = (s / 2 for s in sheet_size())
        me = bpy.data.meshes.new(name)
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


def _sheet_object(scene, name, selectable, mesh=SHEET):
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type != 'MESH':      # a stage-2 (grease pencil) project
        obj.name = name + " (old)"
        obj.hide_viewport = True
        obj = None
    if obj is None:
        obj = bpy.data.objects.new(name, sheet_mesh(mesh))
        obj.hide_select = not selectable
        scene.collection.objects.link(obj)
    elif obj.data.name != mesh:                     # projects from before stage 6
        obj.data = sheet_mesh(mesh)
    if obj.hide_select == selectable:               # (display sheets became selectable)
        obj.hide_select = not selectable
    slot = obj.material_slots[0]
    if slot.link != 'OBJECT':
        slot.link = 'OBJECT'
    return obj


def canvas_object(scene):
    return _sheet_object(scene, CANVAS, True, PAINT_SHEET)


def shift_paint_uv(scene, du, dv, a=1.0):
    """Map the canvas sheet's UVs to uv * a - (du, dv) (fractions of the
    painting), so strokes land in a layer shown moved / scaled
    (features/motion: layer motion, parallax)."""
    uv = canvas_object(scene).data.uv_layers[0].data
    want = [(x * a - du, y * a - dv) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    if any(abs(uv[i].uv[0] - x) > 1e-7 or abs(uv[i].uv[1] - y) > 1e-7 for i, (x, y) in enumerate(want)):
        for i, co in enumerate(want):
            uv[i].uv = co
        canvas_object(scene).data.update()


def _display_object(scene, track):
    # Selectable: they're moved / turned / scaled in the 3D scene view.
    return _sheet_object(scene, DISPLAY_PREFIX + track.uid, True)


def _set(obj, material=None, y=None, hidden=None, alpha=None, placed=None):
    """Change only what differs (every change costs a scene update).
    placed: (offset, rotation, scale) from the 3D scene (y is added to the offset)."""
    if alpha is not None and abs(obj.color[3] - alpha) > 1e-4:
        obj.color[3] = alpha
    slot = obj.material_slots[0]
    if material is not None and slot.material != material:
        slot.material = material
    offset, rotation, k = placed or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0)
    if material is not None:
        sx, sz = _scale_for(material)
        sx, sz = sx * k, sz * k
        if abs(obj.scale.x - sx) > 1e-6 or abs(obj.scale.z - sz) > 1e-6 or abs(obj.scale.y - k) > 1e-6:
            obj.scale = (sx, k, sz)
    if y is not None:
        loc = (offset[0], y + offset[1], offset[2])
        if any(abs(a - b) > 1e-6 for a, b in zip(obj.location, loc)):
            obj.location = loc
        if any(abs(a - b) > 1e-6 for a, b in zip(obj.rotation_euler, rotation)):
            obj.rotation_euler = rotation
        _placed[obj.name] = _transform(obj)
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
        (ox, _oy, oz), rot, k = place(track)
        _set(obj, material=mat or empty_material(), y=y + DEPTH_STEP / 2, hidden=mat is None,
             placed=((ox, 0.0, oz), rot, k),
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

    previous_canvas = _state["canvas_track"]
    _state["canvas_track"] = active.uid if active else ""
    for track in videos:                           # cards moved by hand: keep that first
        if active and track.uid == active.uid and previous_canvas == track.uid:
            _absorb(scene, canvas_object(scene), track)
        elif not (active and track.uid == active.uid):
            _absorb(scene, _display_object(scene, track), track)
    for depth, track in enumerate(videos):
        y = -depth * DEPTH_STEP
        placed = place(track)
        muted = sed.channels[tracks.channel_of(scene, track)].mute
        material = None if muted else _material_at(scene, track, frame)
        if active and track.uid == active.uid:
            _set(canvas_object(scene), material=material or empty, y=y, placed=placed)
            _set(_display_object(scene, track), material=empty, hidden=True)
        else:
            _set(_display_object(scene, track), material=material or empty, y=y,
                 hidden=material is None, placed=placed)
    canvas_y = (-[t.uid for t in videos].index(active.uid) * DEPTH_STEP + place(active)[0][1]) \
        if active else 0.0
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


# Painting speed: the canvas is one flat sheet facing the view, so Texture
# Paint's occlusion test (a depth render at every stroke start), seam bleed and
# angle falloff only cost time. Panels are unlit, so the viewport needs no
# shadows / ray tracing either.
FAST_SETTINGS = {
    "tool_settings.image_paint.use_occlude": False,
    "tool_settings.image_paint.use_backface_culling": False,
    "tool_settings.image_paint.use_normal_falloff": False,
    "tool_settings.image_paint.seam_bleed": 0,
    "eevee.use_shadows": False,
    "eevee.use_raytracing": False,
    "eevee.use_fast_gi": False,
    "eevee.use_volumetric_shadows": False,
    # Ollie: strokes looked thin and faint while drawing, then filled in. The
    # viewport blended each new frame with older ones (reprojection) and kept
    # refining over 16 samples; a flat painted sheet needs neither, so a stroke
    # shows at its final weight straight away.
    "eevee.taa_samples": 1,
    "eevee.use_taa_reprojection": False,
}


def fast_settings(scene):
    for path, value in FAST_SETTINGS.items():
        *parents, attr = path.split(".")
        owner = scene
        for name in parents:
            owner = getattr(owner, name)
        if getattr(owner, attr) != value:
            setattr(owner, attr, value)


def _on_load(scene):
    if scene is None:
        return
    fast_settings(scene)
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
