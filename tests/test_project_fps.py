"""Changing the project's frame rate (timeline/rate.py): every clip, its
media, keys, fades, markers and the range keep their time in seconds;
footage keeps playing at real speed, in sync with its sound."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
fr = h.module("features.edit.frame_rate")
shots = h.module("features.scene3d.shots")
panels = h.module("features.storyboard.panels")


def snapshot(sc):
    r = sc.render.fps / sc.render.fps_base
    out = {}
    for s in clips.all_clips(sc):
        out[s.name] = (clips.start(s) / r, clips.end(s) / r, s.content_start / r)
    keys = sorted([round(k.co[0] / r, 2) for fc in shots.scene_fcurves(sc) for k in fc.keyframe_points]
                  + [round((k.co[0] + shots.origin(c)) / r, 2) for c in sc.sequence_editor.strips_all
                     for fc in shots.curves(c).values() for k in fc.keyframe_points])     # (clips' own keys)
    marks = sorted(round(m.frame / r, 2) for m in sc.timeline_markers)
    return out, keys, marks


def close(a, b, r):
    """Same times, within a frame at the coarser rate."""
    tol = 1.01 / r
    if a[0].keys() != b[0].keys():
        return False, "clips differ", sorted(set(a[0]) ^ set(b[0]))
    for name in a[0]:
        if any(abs(x - y) > tol for x, y in zip(a[0][name], b[0][name])):
            return False, name, (a[0][name], b[0][name])
    for x, y in zip(a[1] + a[2], b[1] + b[2]):
        if abs(x - y) > tol:
            return False, "keys / markers", (a[1:], b[1:])
    return True, None, None


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "fps")
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "phone.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", movie], check=True)
    made = media.place(sc, movie, frame=100)
    video = next(s for s in made if s.type == 'MOVIE')
    sound = next(s for s in made if s.type == 'SOUND')
    # Trim its start (the media slides: a cut-off start).
    clips.apply(sc, {video: (124, clips.end(video), video.content_start), sound: (124, clips.end(sound), sound.content_start)})
    panel = panels.all_panels(sc)[0]
    panel.plastron.fade_in = 12
    shots.set_card(sc, panel, (0.5, 0, 0), (0, 0, 0), 1.0, 10)
    shots.set_card(sc, panel, (1.0, 0, 0), (0, 0, 0), 1.0, 40)
    sc.timeline_markers.new("beat", frame=200)
    windows = h.module("features.edit.windows")
    windows.new_window(sc, windows.styles()[0][1], frame=400)
    sc.frame_current = 150
    yield 0.5
    before = snapshot(sc)
    seconds_now = 150 / 24

    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.project_fps(fps=30)
    yield 0.5
    sc = bpy.context.scene
    video, sound, panel = (sc.sequence_editor.strips_all[n] for n in (video.name, sound.name, panel.name))
    ws = next(x for x in bpy.data.scenes if x.get("plastron_window_of") == sc.name)
    h.check("info windows' own timelines change rate with it", ws.render.fps == 30, ws.render.fps)
    h.check("the project is 30 fps", sc.render.fps == 30 and sc.render.fps_base == 1.0, (sc.render.fps, sc.render.fps_base))
    ok, what, detail = close(before, snapshot(sc), 24)
    h.check("every clip, its media, the keys and the markers keep their time in seconds", ok, (what, detail))
    h.check("the footage still plays at real speed", abs(fr.plays_at(sc, video) - 1) < 0.01, fr.plays_at(sc, video))
    h.check("...in step with its sound (same length)", abs(clips.length(video) - clips.length(sound)) <= 1,
            (clips.length(video), clips.length(sound)))
    h.check("fades keep their length (12 frames at 24 = 15 at 30)", panel.plastron.fade_in == 15, panel.plastron.fade_in)
    h.check("the playhead stays at the same moment", abs(sc.frame_current / 30 - seconds_now) < 1 / 24, sc.frame_current)

    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.project_fps(fps=24)
    yield 0.5
    sc = bpy.context.scene
    video = sc.sequence_editor.strips_all[video.name]
    ok, what, detail = close(before, snapshot(sc), 24)
    h.check("back to 24 fps: everything where it started", ok and sc.render.fps == 24, (what, detail))
    h.check("...and the footage at real speed again", abs(fr.plays_at(sc, video) - 1) < 0.01, fr.plays_at(sc, video))
    h.redraw()
    yield 0.3
    h.screenshot("project_fps")


h.run(steps())
