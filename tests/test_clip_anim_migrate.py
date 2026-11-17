"""Older projects: per-track card keys and one long 3D camera animation
move onto the clips (each clip owns its animation, features/scene3d/shots)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

scene3d = h.module("features.scene3d")
shots = h.module("features.scene3d.shots")
panels = h.module("features.storyboard.panels")
tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
canvas_sync = h.module("features.storyboard.canvas_sync")
cfg = h.module("config.scene3d")


def steps():
    yield 1.0
    sc = bpy.context.scene
    first = panels.all_panels(sc)[0]                    # 1 .. 49 on Panels
    second = panels.create(sc, first.channel, clips.end(first), 48)
    top = tracks.track_of_clip(sc, first)
    # The old way: the track's card keyed at 10 and 60, the camera keyed at 10 and 60.
    top.place_offset = (0.0, 1.0, 0.0)
    top.keyframe_insert("place_offset", frame=10)
    top.place_offset = (0.0, 3.0, 0.0)
    top.keyframe_insert("place_offset", frame=60)
    cam = scene3d.camera(sc)
    loc, _rot = scene3d.rest_pose()
    cam.location = (1.0, loc.y, loc.z)
    cam.keyframe_insert("location", frame=10)
    cam.location = (2.0, loc.y, loc.z)
    cam.keyframe_insert("location", frame=60)
    del sc[shots.DONE]
    scene3d._on_load(sc)
    yield 0.5
    h.check("old per-track card keys are gone, the clips have them",
            not any("plastron_timeline.tracks" in fc.data_path for fc in shots.scene_fcurves(sc))
            and shots.animated(sc, first, shots.CARD_PROPS) and shots.animated(sc, second, shots.CARD_PROPS),
            [fc.data_path for fc in shots.scene_fcurves(sc)])
    h.check("old camera keys are gone, each shot has its own",
            cam.animation_data is None and shots.animated(sc, first, shots.CAM_PROPS)
            and shots.animated(sc, second, shots.CAM_PROPS))
    sc.frame_current = 10
    yield 0.4
    at10 = cam.location.x
    sc.frame_current = 60
    yield 0.4
    h.check("...and the camera still goes where it went (1 at frame 10, 2 at frame 60)",
            abs(at10 - 1.0) < 1e-4 and abs(cam.location.x - 2.0) < 1e-4, (at10, cam.location.x))
    h.check("...the cards too (offset 3 at frame 60, on the second clip)",
            abs(second.plastron_card_offset[1] - 3.0) < 1e-4, tuple(second.plastron_card_offset))
    n = len(shots.scene_fcurves(sc))
    scene3d._on_load(sc)
    yield 0.2
    h.check("done once (loading again changes nothing)", len(shots.scene_fcurves(sc)) == n)


h.run(steps())
