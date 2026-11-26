"""Each clip owns its animation, in its OWN time (Ollie: keyframed moves
"keep jumping around and disappearing when I ripple edit stuff"; the first
version kept them in the timeline's one action under each clip's NAME, in
timeline frames, shifted by hand whenever a clip moved: trims, renames and
reused names moved or lost them).

Clip time 0 (origin): for footage / sound / scenes, the content's start
(content_start: Blender keeps it where the media is through moves, trims,
splits). Still pictures (panels, titles...) have no hidden content: Blender
puts their content_start at their left edge, so trims / splits would move
it. They keep their own anchor (plastron_anim_at) with the edges last seen
(plastron_anim_seen): after each edit (track), a clip whose two edges moved
by the same amount carries it along; a trim / split (one edge) leaves it.
It's stored on the clip, so undo, split halves and copies keep it right.

A clip (strip) carries:
    plastron_card_offset / _rotation / _scale   where its card stands in 3D
    plastron_cam_set + plastron_cam_location / _rotation / _lens   the 3D Camera
as its resting values, and plastron_anim: its own Action whose keys are in
CLIP time (frames from the clip's content start, content_start). Nothing on
the timeline points at a clip's keys, so moving, trimming (either edge),
rippling, renaming or re-timing a clip can't shift or lose them: they go
wherever its content goes. A split / copied clip gets its own copy.

Plastron plays them itself (fcurve.evaluate at the clip's time). The
keyframe view shows the CURRENT clip's keys: a copy in the timeline's action
at timeline frames (mirror); edits made there are copied back (check_mirror).
"""

import re

import bpy

from ...config import scene3d as cfg

CARD_PROPS = ("plastron_card_offset", "plastron_card_rotation", "plastron_card_scale")
CAM_PROPS = ("plastron_cam_location", "plastron_cam_rotation", "plastron_cam_lens")
ANIM_PROPS = CARD_PROPS + CAM_PROPS
GROUPS = {p: "Card" for p in CARD_PROPS} | {p: "Camera" for p in CAM_PROPS}
DONE = "plastron_clip_anim"            # scene flag: older per-track / camera keys moved onto clips
LOCAL = "plastron_clip_local"          # scene flag: timeline-frame clip keys moved into clip time
_PATH = re.compile(r'^sequence_editor\.strips_all\["((?:[^"\\]|\\.)*)"\]\.(\w+)$')


def strip_path(strip):
    return 'sequence_editor.strips_all["{}"]'.format(strip.name.replace("\\", "\\\\").replace('"', '\\"'))


def all_fcurves(action):
    if action is None:
        return []
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []                                   # layered actions (Blender 4.4+)
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


def scene_fcurves(scene):
    ad = scene.animation_data
    return all_fcurves(ad.action if ad else None)


# --- a clip's own keys (clip time) ---------------------------------------------------------

CONTENT_TYPES = {'MOVIE', 'SOUND', 'SCENE', 'MOVIECLIP', 'MASK'}


def has_content(clip):
    """Does Blender keep where the clip's media starts (content_start) itself?"""
    return clip.type in CONTENT_TYPES or (clip.type == 'IMAGE' and len(clip.elements) > 1)


def origin(clip):
    """Timeline frame of the clip's time 0."""
    if has_content(clip) or not clip.plastron_anim_anchored:
        return clip.content_start
    return clip.plastron_anim_at


def _anchor(clip):
    if not has_content(clip) and not clip.plastron_anim_anchored:
        clip.plastron_anim_at = clip.content_start
        clip.plastron_anim_seen = (clip.left_handle, clip.right_handle)
        clip.plastron_anim_anchored = True


def track(scene):
    """After edits: still pictures' anchors follow whole-clip moves (both edges
    moved by the same amount); trims / splits (one edge) leave them."""
    sed = scene.sequence_editor if scene else None
    for clip in (sed.strips_all if sed else []):
        if not clip.plastron_anim_anchored or has_content(clip):
            continue
        l, r = clip.left_handle, clip.right_handle
        sl, sr = clip.plastron_anim_seen
        if (l, r) == (sl, sr):
            continue
        if l - sl == r - sr:
            clip.plastron_anim_at += l - sl
        clip.plastron_anim_seen = (l, r)


def _bag(clip, create=False):
    act = getattr(clip, "plastron_anim", None)
    if create:
        _anchor(clip)
    if act is None:
        if not create:
            return None
        act = bpy.data.actions.new(f"Clip {clip.name}")
        clip.plastron_anim = act
    if not act.slots:
        if not create:
            return None
        act.slots.new(id_type='SCENE', name="Clip")
    if not act.layers:
        if not create:
            return None
        act.layers.new("Layer")
    layer = act.layers[0]
    if not layer.strips:
        if not create:
            return None
        layer.strips.new(type='KEYFRAME')
    st = layer.strips[0]
    bag = st.channelbag(act.slots[0])
    if bag is None and create:
        bag = st.channelbags.new(act.slots[0])
    return bag


def curves(clip):
    """{(prop, index): fcurve} of the clip's own keys."""
    bag = _bag(clip) if clip is not None else None
    return {(fc.data_path, fc.array_index): fc for fc in bag.fcurves} if bag is not None else {}


def _curve(clip, prop, index):
    bag = _bag(clip, create=True)
    fc = bag.fcurves.find(prop, index=index)
    if fc is None:
        fc = bag.fcurves.new(prop, index=index)
        group = bag.groups.get(GROUPS.get(prop, "Keys")) or bag.groups.new(GROUPS.get(prop, "Keys"))
        fc.group = group
    return fc


def animated(scene, clip, props):
    """Has the clip keys on any of props?"""
    return any(p in props and len(fc.keyframe_points) for (p, _i), fc in curves(clip).items())


def value(clip, prop, frame, fcs=None):
    """The clip's prop at timeline frame: its keys if it has any, else its resting value."""
    rest = getattr(clip, prop)
    fcs = curves(clip) if fcs is None else fcs
    t = frame - origin(clip)
    if hasattr(rest, "__len__"):
        out = list(rest)
        for i in range(len(out)):
            fc = fcs.get((prop, i))
            if fc is not None and len(fc.keyframe_points):
                out[i] = fc.evaluate(t)
        return tuple(out)
    fc = fcs.get((prop, 0))
    return fc.evaluate(t) if fc is not None and len(fc.keyframe_points) else rest


def card_place(clip, frame=None):
    """(offset, rotation, scale) of a clip's card at frame (rest without a clip)."""
    if clip is None:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0
    if frame is None:
        return tuple(clip.plastron_card_offset), tuple(clip.plastron_card_rotation), clip.plastron_card_scale
    fcs = curves(clip)
    return tuple(value(clip, p, frame, fcs) for p in CARD_PROPS)


def camera_pose(clip, frame):
    """(location, rotation, lens) of a clip's own camera at frame, or None."""
    if clip is None or not clip.plastron_cam_set:
        return None
    fcs = curves(clip)
    return tuple(value(clip, p, frame, fcs) for p in CAM_PROPS)


def key(scene, clip, props, frame, values=None):
    """Key props at timeline frame in the clip's own time (values: what to key;
    default: the clip's resting values)."""
    _anchor(clip)
    t = frame - origin(clip)
    for n, prop in enumerate(props):
        v = values[n] if values is not None else getattr(clip, prop)
        for i, x in enumerate(v if hasattr(v, "__len__") else (v,)):
            fc = _curve(clip, prop, i)
            fc.keyframe_points.insert(t, x)
            fc.update()


def set_card(scene, clip, offset, rotation, scale, frame):
    """A card moved by hand: the clip keeps it, keyed at the playhead."""
    if scale <= 1e-4:
        return False
    now = card_place(clip, frame)
    new = (tuple(offset), tuple(rotation), scale)
    if all(abs(a - b) <= 1e-6 for a, b in zip(now[0] + now[1] + (now[2],), new[0] + new[1] + (new[2],))):
        return False
    clip.plastron_card_offset, clip.plastron_card_rotation, clip.plastron_card_scale = new
    key(scene, clip, CARD_PROPS, frame, new)
    mirror(scene, force=True)
    return True


def set_camera(scene, clip, location, rotation, lens, frame):
    clip.plastron_cam_set = True
    clip.plastron_cam_location, clip.plastron_cam_rotation, clip.plastron_cam_lens = location, rotation, lens
    key(scene, clip, CAM_PROPS, frame, (tuple(location), tuple(rotation), lens))
    mirror(scene, force=True)


def reset(scene, clip, card=True, camera=True):
    """Put a clip's card square-on in its place and / or its shot's camera at
    rest: its keys go (Ollie: a panel didn't show; its card had been moved
    out of the camera's view). True if anything changed."""
    if clip is None:
        return False
    props = (CARD_PROPS if card else ()) + (CAM_PROPS if camera else ())
    bag = _bag(clip)
    gone = [fc for fc in (bag.fcurves if bag is not None else []) if fc.data_path in props]
    for fc in gone:
        bag.fcurves.remove(fc)
    before = card_place(clip) + (clip.plastron_cam_set,)
    if card:
        clip.plastron_card_offset = (0.0, 0.0, 0.0)
        clip.plastron_card_rotation = (0.0, 0.0, 0.0)
        clip.plastron_card_scale = 1.0
    if camera:
        clip.plastron_cam_set = False
    mirror(scene, force=True)
    return bool(gone) or before != card_place(clip) + (clip.plastron_cam_set,)


def own_copy(clip):
    """A split / copied clip shares its original's keys: give it its own."""
    act = getattr(clip, "plastron_anim", None)
    if act is not None:
        clip.plastron_anim = act.copy()
        clip.plastron_anim.name = f"Clip {clip.name}"


def slid(clip, d):
    """A ripple trim of the start cut d frames off: a still picture's clip
    time slides like footage's content does (the cut-off start is gone)."""
    if clip.plastron_anim_anchored and not has_content(clip):
        clip.plastron_anim_at += d


def scale_times(scene, k):
    """The frame rate changed by k (clip times are frames: keep their seconds)."""
    sed = scene.sequence_editor
    for clip in (sed.strips_all if sed else []):
        if clip.plastron_anim_anchored:
            clip.plastron_anim_at *= k
            clip.plastron_anim_seen = (clip.left_handle, clip.right_handle)
        for fc in curves(clip).values():
            for kp in fc.keyframe_points:
                kp.co[0] *= k
                kp.handle_left[0] *= k
                kp.handle_right[0] *= k
            fc.update()


# --- the keyframe view: a copy of the current clip's keys at timeline frames ----------------

_mirror = {"scene": None, "clip": None, "origin": None, "snap": None, "busy": False, "ids": None, "op": 0}

# Operators that edit keys in the keyframe view (only their changes are copied back).
KEY_EDITS = ("ACTION_OT_", "ANIM_OT_", "GRAPH_OT_")
KEY_DRAGS = {"TRANSFORM_OT_transform"}


def _last_op():
    wm = bpy.context.window_manager
    ops = wm.operators if wm is not None else []
    return ops[-1] if len(ops) else None


def _keys_edited():
    """Has a keyframe-view edit (by hand) finished since the copy was made / read?"""
    op = _last_op()
    if op is None or op.as_pointer() == _mirror["op"]:
        return False
    return op.bl_idname.startswith(KEY_EDITS) or op.bl_idname in KEY_DRAGS


def _current(scene):
    from ..storyboard import canvas_sync
    name = canvas_sync._state.get("canvas_clip")
    sed = scene.sequence_editor if scene else None
    return sed.strips_all.get(name) if (sed is not None and name) else None


def _shown(scene):
    """{(clip name, prop, index): fcurve} of clip keys in the timeline's action."""
    out = {}
    for fc in scene_fcurves(scene):
        m = _PATH.match(fc.data_path)
        if m and m.group(2) in ANIM_PROPS:
            out[(m.group(1).replace('\\"', '"').replace("\\\\", "\\"), m.group(2), fc.array_index)] = fc
    return out


def _snap(fcs, shift):
    """Comparable keys: {(prop, index): ((t, value, interpolation), ...)} at frame - shift."""
    return {k: tuple((round(kp.co[0] - shift, 4), round(kp.co[1], 6), kp.interpolation)
                     for kp in fc.keyframe_points) for k, fc in fcs.items() if len(fc.keyframe_points)}


def _remove_scene_fcurve(scene, fc):
    ad = scene.animation_data
    _remove_fcurve(ad.action if ad else None, fc)


def _copy_points(src, dst, shift):
    dst.keyframe_points.clear()
    dst.keyframe_points.add(len(src.keyframe_points))
    for a, b in zip(src.keyframe_points, dst.keyframe_points):
        b.co = (a.co[0] + shift, a.co[1])
        b.handle_left_type, b.handle_right_type = a.handle_left_type, a.handle_right_type
        b.handle_left = (a.handle_left[0] + shift, a.handle_left[1])
        b.handle_right = (a.handle_right[0] + shift, a.handle_right[1])
        b.interpolation, b.easing = a.interpolation, a.easing
    dst.update()


def mirror(scene, force=False):
    """Show the current clip's keys in the keyframe view (only those): its own
    keys copied into the timeline's action at timeline frames."""
    if scene is None or _mirror["busy"] or not hasattr(scene, "plastron_timeline"):
        return
    if not scene.get(LOCAL):
        migrate_local(scene)                   # (never wipe a project's keys before they're the clips')
    clip = _current(scene)
    name = clip.name if clip is not None else None
    if not force and _mirror["scene"] == scene.name and _mirror["clip"] == name \
            and clip is not None and _mirror["origin"] == origin(clip):
        return
    _mirror["busy"] = True
    try:
        for fc in list(_shown(scene).values()):
            _remove_scene_fcurve(scene, fc)
        own = curves(clip)
        for (prop, i), fc in own.items():
            if not len(fc.keyframe_points):
                continue
            array = hasattr(getattr(clip, prop), "__len__")
            clip.keyframe_insert(prop, index=i if array else -1, frame=fc.keyframe_points[0].co[0] + origin(clip),
                                 group=f"{clip.name} | {GROUPS.get(prop, 'Keys')}")
        shown = _shown(scene)
        for (prop, i), fc in own.items():
            dst = shown.get((name, prop, i))
            if dst is not None:
                _copy_points(fc, dst, origin(clip))
        _mirror.update(scene=scene.name, clip=name, origin=origin(clip) if clip is not None else None,
                       ids=_ids(scene, clip), op=_last_op().as_pointer() if _last_op() else 0,
                       snap=_snap({(p, i): fc for (n, p, i), fc in _shown(scene).items() if n == name}, 0.0))
    finally:
        _mirror["busy"] = False


def _ids(scene, clip):
    """Which copy this is: the scene's action and the clip themselves (after
    opening a file or undo they're new: the copy there isn't ours to read)."""
    ad = scene.animation_data
    act = ad.action if ad else None
    return (scene.as_pointer(), act.as_pointer() if act else 0, clip.as_pointer() if clip is not None else 0)


def check_mirror(scene, edited=None):
    """After an edit: keys changed BY HAND in the keyframe view go back into
    the clip's own keys; any other change to the copy (the clip moved, a new
    file, undo, something else rewriting the timeline's keys) just makes the
    copy afresh from the clip's own keys, which always rule.
    edited: the copy was edited by hand (default: a keyframe-view operator ran)."""
    if scene is None or _mirror["busy"] or _mirror["scene"] != scene.name or _mirror["clip"] is None:
        return
    sed = scene.sequence_editor
    clip = sed.strips_all.get(_mirror["clip"]) if sed else None
    if clip is None or clip != _current(scene) or origin(clip) != _mirror["origin"] \
            or _ids(scene, clip) != _mirror["ids"]:
        mirror(scene, force=True)              # (another clip, it moved, or a new file / undo: the clip's own keys rule)
        return
    shown = {(p, i): fc for (n, p, i), fc in _shown(scene).items() if n == clip.name}
    if _snap(shown, 0.0) == _mirror["snap"]:
        return
    if not (_keys_edited() if edited is None else edited):
        mirror(scene, force=True)
        return
    op = _last_op()
    _mirror["op"] = op.as_pointer() if op else 0
    _mirror["busy"] = True
    try:
        bag = _bag(clip)
        for fc in list(bag.fcurves if bag is not None else []):
            if (fc.data_path, fc.array_index) not in shown and fc.data_path in ANIM_PROPS:
                bag.fcurves.remove(fc)
        for (prop, i), src in shown.items():
            dst = _curve(clip, prop, i)
            _copy_points(src, dst, -origin(clip))
        _mirror["snap"] = _snap(shown, 0.0)
    finally:
        _mirror["busy"] = False


def forget_mirror(*_args):
    _mirror.update(scene=None, clip=None, origin=None, snap=None, ids=None)


def migrate_local(scene):
    """Projects keyed in timeline frames under clip names (before clip time):
    each clip's keys moved into its own (once)."""
    if scene.get(LOCAL) or not hasattr(scene, "plastron_timeline"):
        return
    scene[LOCAL] = 1
    sed = scene.sequence_editor
    for (name, prop, i), fc in _shown(scene).items():
        clip = sed.strips_all.get(name) if sed else None
        if clip is not None and len(fc.keyframe_points):
            fc_local = _curve(clip, prop, i)           # (anchors the clip first)
            _copy_points(fc, fc_local, -origin(clip))
        _remove_scene_fcurve(scene, fc)


# --- older projects: per-track card keys and one long camera animation -----------------------

_TRACK = re.compile(r"plastron_timeline\.tracks\[(\d+)\]\.(place_offset|place_rotation|place_scale)$")


def migrate(scene, rest_location, rest_rotation, shot_clip_at):
    """Move a project's older animation onto its clips (once): each track's
    card keys onto that track's clips (the keys inside each clip's span, and
    its value at the clip's start), the camera's keys onto the clip that was
    its shot at each key; untouched placements copied as each clip's own."""
    from ...timeline import clips, tracks
    if scene.get(DONE) or not hasattr(scene, "plastron_timeline"):
        return
    scene[DONE] = 1
    fcs = scene_fcurves(scene)
    track_curves = {}
    for fc in fcs:
        m = _TRACK.match(fc.data_path)
        if m:
            track_curves.setdefault(int(m.group(1)), []).append(fc)
    all_tracks = tracks.all_tracks(scene)
    for i, track in enumerate(all_tracks):
        if track.kind != 'VIDEO' or not hasattr(track, "place_offset"):
            continue
        curves = track_curves.get(i, [])
        if curves and all(len({round(k.co[1], 6) for k in fc.keyframe_points}) <= 1 for fc in curves):
            for fc in curves:                  # (keys that never change: a placement, not a move)
                if len(fc.keyframe_points):
                    prop = fc.data_path.rsplit(".", 1)[1]
                    v = getattr(track, prop)
                    if hasattr(v, "__len__"):
                        v = list(v)
                        v[fc.array_index] = fc.keyframe_points[0].co[1]
                    else:
                        v = fc.keyframe_points[0].co[1]
                    setattr(track, prop, v)
            curves = []
        static = (tuple(track.place_offset), tuple(track.place_rotation), track.place_scale)
        moved = any(abs(v) > 1e-6 for v in static[0] + static[1]) or abs(static[2] - 1.0) > 1e-6
        if not curves and not moved:
            continue
        for clip in clips.on_channel(scene, tracks.channel(i)):
            s, e = clips.start(clip), clips.end(clip)
            inside = {round(k.co[0]) for fc in curves for k in fc.keyframe_points if s <= k.co[0] < e}
            frames = sorted({s} | inside)       # (no keys in its span: just its placement, unkeyed)

            def value(prop, n, frame):
                out = list(getattr(track, prop)) if n > 1 else [getattr(track, prop)]
                for fc in curves:
                    if fc.data_path.endswith(prop) and fc.array_index < n:
                        out[fc.array_index] = fc.evaluate(frame)
                return tuple(out) if n > 1 else out[0]
            for f in (frames if inside else [s]):
                clip.plastron_card_offset = value("place_offset", 3, f)
                clip.plastron_card_rotation = value("place_rotation", 3, f)
                clip.plastron_card_scale = value("place_scale", 1, f)
                if inside:
                    key(scene, clip, CARD_PROPS, f)
    for curves in track_curves.values():
        for fc in curves:
            _remove_fcurve(scene.animation_data.action, fc)
    for track in all_tracks:
        if hasattr(track, "place_offset"):
            track.place_offset = (0.0, 0.0, 0.0)
            track.place_rotation = (0.0, 0.0, 0.0)
            track.place_scale = 1.0
    _migrate_camera(scene, rest_location, rest_rotation, shot_clip_at)


def _migrate_camera(scene, rest_location, rest_rotation, shot_clip_at):
    from ...timeline import clips
    cam = bpy.data.objects.get(cfg.CAMERA_NAME)
    if cam is None:
        return
    curves = [(cam, fc) for fc in all_fcurves(cam.animation_data.action if cam.animation_data else None)
              if fc.data_path in ("location", "rotation_euler")]
    curves += [(cam.data, fc) for fc in all_fcurves(cam.data.animation_data.action if cam.data.animation_data else None)
               if fc.data_path == "lens"]

    def pose_at(frame):
        loc, rot, lens = list(cam.location), list(cam.rotation_euler), cam.data.lens
        for _owner, fc in curves:
            v = fc.evaluate(frame)
            if fc.data_path == "location":
                loc[fc.array_index] = v
            elif fc.data_path == "rotation_euler":
                rot[fc.array_index] = v
            else:
                lens = v
        return tuple(loc), tuple(rot), lens
    if curves:
        per_clip = {}
        for _owner, fc in curves:
            for k in fc.keyframe_points:
                clip = shot_clip_at(scene, round(k.co[0]))
                if clip is not None:
                    per_clip.setdefault(clip.name, (clip, set()))[1].add(round(k.co[0]))
        sed = scene.sequence_editor
        for clip in (sed.strips_all if sed else []):      # (clips without keys of their own: the pose they showed)
            if clip.name not in per_clip and clip.type != 'SOUND':
                clip.plastron_cam_set = True
                clip.plastron_cam_location, clip.plastron_cam_rotation, clip.plastron_cam_lens = \
                    pose_at(clips.start(clip))
        for clip, frames in per_clip.values():
            for f in sorted(frames | {clips.start(clip)}):
                set_camera(scene, clip, *pose_at(f), f)
        for owner in (cam, cam.data):
            if owner.animation_data is not None:
                owner.animation_data_clear()
    else:
        loc, rot, lens = tuple(cam.location), tuple(cam.rotation_euler), cam.data.lens
        off_rest = any(abs(a - b) > 1e-4 for a, b in zip(loc + rot, tuple(rest_location) + tuple(rest_rotation))) \
            or abs(lens - cfg.CAMERA_LENS) > 1e-4
        if off_rest:                          # (placed once for the whole project: every clip keeps it)
            sed = scene.sequence_editor
            for clip in (sed.strips_all if sed else []):
                clip.plastron_cam_set = True
                clip.plastron_cam_location, clip.plastron_cam_rotation, clip.plastron_cam_lens = loc, rot, lens


def _remove_fcurve(action, fc):
    if action is None:
        return
    if hasattr(action, "fcurves"):
        action.fcurves.remove(fc)
        return
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                if fc in list(bag.fcurves):
                    bag.fcurves.remove(fc)
                    return


def _on_split(scene, original, new):
    own_copy(new)


def register():
    S = bpy.types.Strip
    S.plastron_card_offset = bpy.props.FloatVectorProperty(name="Card Offset", size=3, subtype='TRANSLATION')
    S.plastron_card_rotation = bpy.props.FloatVectorProperty(name="Card Rotation", size=3, subtype='EULER')
    S.plastron_card_scale = bpy.props.FloatProperty(name="Card Scale", default=1.0, min=0.001)
    S.plastron_cam_set = bpy.props.BoolProperty(name="Has Camera")
    S.plastron_cam_location = bpy.props.FloatVectorProperty(name="Camera Location", size=3, subtype='TRANSLATION')
    S.plastron_cam_rotation = bpy.props.FloatVectorProperty(name="Camera Rotation", size=3, subtype='EULER')
    S.plastron_cam_lens = bpy.props.FloatProperty(name="Camera Lens", default=cfg.CAMERA_LENS, min=1.0)
    S.plastron_anim = bpy.props.PointerProperty(type=bpy.types.Action, name="Clip Keys")
    S.plastron_anim_anchored = bpy.props.BoolProperty()
    S.plastron_anim_at = bpy.props.FloatProperty()
    S.plastron_anim_seen = bpy.props.IntVectorProperty(size=2)
    from ...timeline import events, rate
    events.listen("clip_split", _on_split)
    events.listen("clip_duplicated", _on_split)
    rate.TIME_SCALERS.append(scale_times)
    from ...timeline import clips
    clips.SLIDE_HOOKS.append(slid)
    from ...core import handlers
    handlers.add("load_pre", forget_mirror)


def unregister():
    S = bpy.types.Strip
    from ...timeline import rate
    if scale_times in rate.TIME_SCALERS:
        rate.TIME_SCALERS.remove(scale_times)
    from ...timeline import clips
    if slid in clips.SLIDE_HOOKS:
        clips.SLIDE_HOOKS.remove(slid)
    for name in CARD_PROPS + CAM_PROPS + ("plastron_cam_set", "plastron_anim", "plastron_anim_anchored",
                                                  "plastron_anim_at", "plastron_anim_seen"):
        if hasattr(S, name):
            delattr(S, name)
