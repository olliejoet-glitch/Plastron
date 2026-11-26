"""Each clip owns its animation (Ollie: "the animation isn't actually stored
per clip, it's stored on a single plane on the entire timeline").

A clip (strip) carries its card's placement and its shot's camera as its own
properties, keyed in the scene's action under the clip's own path:
    plastron_card_offset / _rotation / _scale   where its card stands in 3D
    plastron_cam_set + plastron_cam_location / _rotation / _lens   the 3D Camera
So a clip's keys move, split, duplicate and delete with the clip (Blender's
own clip moves do that; Plastron's moves from Python shift them too:
timeline/clips), never reach another clip, and the keyframe view shows the
current clip's channels only (they're named "... (<clip name>)").

The card on a track's sheet takes the placement of that track's clip under
the playhead; the 3D Camera takes the camera of the clip being drawn on (its
shot), or rests square-on if that clip has none.
"""

import re

import bpy

from ...config import scene3d as cfg

CARD_PROPS = ("plastron_card_offset", "plastron_card_rotation", "plastron_card_scale")
CAM_PROPS = ("plastron_cam_location", "plastron_cam_rotation", "plastron_cam_lens")
DONE = "plastron_clip_anim"            # scene flag: older per-track / camera keys moved onto clips


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


def animated(scene, clip, props):
    """Has the clip keys on any of props?"""
    if clip is None:
        return False
    base = strip_path(clip) + "."
    want = {base + p for p in props}
    return any(fc.data_path in want and len(fc.keyframe_points) for fc in scene_fcurves(scene))


def card_place(clip):
    """(offset, rotation, scale) of a clip's card (rest without a clip)."""
    if clip is None:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0
    return tuple(clip.plastron_card_offset), tuple(clip.plastron_card_rotation), clip.plastron_card_scale


def key(scene, clip, props, frame, group):
    for prop in props:
        clip.keyframe_insert(prop, frame=frame, group=f"{clip.name} | {group}")


def set_card(scene, clip, offset, rotation, scale, frame):
    """A card moved by hand: the clip keeps it, keyed at the playhead."""
    changed = False
    if any(abs(a - b) > 1e-6 for a, b in zip(clip.plastron_card_offset, offset)):
        clip.plastron_card_offset = offset
        changed = True
    if any(abs(a - b) > 1e-6 for a, b in zip(clip.plastron_card_rotation, rotation)):
        clip.plastron_card_rotation = rotation
        changed = True
    if abs(clip.plastron_card_scale - scale) > 1e-6 and scale > 1e-4:
        clip.plastron_card_scale = scale
        changed = True
    if changed:
        key(scene, clip, CARD_PROPS, frame, "Card")
    return changed


def set_camera(scene, clip, location, rotation, lens, frame):
    clip.plastron_cam_set = True
    clip.plastron_cam_location = location
    clip.plastron_cam_rotation = rotation
    clip.plastron_cam_lens = lens
    key(scene, clip, CAM_PROPS, frame, "Camera")


def reset(scene, clip, card=True, camera=True):
    """Put a clip's card square-on in its place and / or its shot's camera at
    rest: its keys go (Ollie: a panel didn't show; its card had been moved
    out of the camera's view). True if anything changed."""
    if clip is None:
        return False
    props = (CARD_PROPS if card else ()) + ((CAM_PROPS + ("plastron_cam_set",)) if camera else ())
    base = strip_path(clip) + "."
    want = {base + p for p in props}
    ad = scene.animation_data
    gone = [fc for fc in scene_fcurves(scene) if fc.data_path in want]
    for fc in gone:
        _remove_fcurve(ad.action, fc)
    before = card_place(clip) + (clip.plastron_cam_set,)
    if card:
        clip.plastron_card_offset = (0.0, 0.0, 0.0)
        clip.plastron_card_rotation = (0.0, 0.0, 0.0)
        clip.plastron_card_scale = 1.0
    if camera:
        clip.plastron_cam_set = False
    return bool(gone) or before != card_place(clip) + (clip.plastron_cam_set,)


def shift_keys(scene, strip, delta):
    """Move every key of strip by delta frames (its keys follow its start)."""
    if not delta:
        return
    base = strip_path(strip) + "."
    for fc in scene_fcurves(scene):
        if fc.data_path.startswith(base):
            for k in fc.keyframe_points:
                k.co[0] += delta
                k.handle_left[0] += delta
                k.handle_right[0] += delta
            fc.update()


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
                    key(scene, clip, CARD_PROPS, f, "Card")
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


def register():
    S = bpy.types.Strip
    S.plastron_card_offset = bpy.props.FloatVectorProperty(name="Card Offset", size=3, subtype='TRANSLATION')
    S.plastron_card_rotation = bpy.props.FloatVectorProperty(name="Card Rotation", size=3, subtype='EULER')
    S.plastron_card_scale = bpy.props.FloatProperty(name="Card Scale", default=1.0, min=0.001)
    S.plastron_cam_set = bpy.props.BoolProperty(name="Has Camera")
    S.plastron_cam_location = bpy.props.FloatVectorProperty(name="Camera Location", size=3, subtype='TRANSLATION')
    S.plastron_cam_rotation = bpy.props.FloatVectorProperty(name="Camera Rotation", size=3, subtype='EULER')
    S.plastron_cam_lens = bpy.props.FloatProperty(name="Camera Lens", default=cfg.CAMERA_LENS, min=1.0)


def unregister():
    S = bpy.types.Strip
    for name in CARD_PROPS + CAM_PROPS + ("plastron_cam_set",):
        if hasattr(S, name):
            delattr(S, name)
