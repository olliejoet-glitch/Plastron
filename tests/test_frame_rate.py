"""Frame rate check (features/edit/frame_rate.py): phone footage at another
frame rate plays at real speed (in sync with its sound); a variable frame
rate is read from the file and reported; Play at Real Speed fixes older
clips."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
fr = h.module("features.edit.frame_rate")


def make(folder, name, vf=None, rate=30):
    path = os.path.join(folder, name)
    args = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate={rate}:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=300:duration=6"]
    if vf:
        args += ["-vf", vf, "-fps_mode", "vfr"]
    subprocess.run(args + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path], check=True)
    return path


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "rates")
    os.makedirs(folder, exist_ok=True)
    cfr = make(folder, "cfr30.mp4")
    vfr = make(folder, "phone.mp4", vf="setpts='(N/29.4+0.006*mod(N\\,3))/TB'")

    a = fr.video_timing(fr.read_tracks(cfr))
    h.check("a constant 30 fps file reads as constant 30 fps",
            a and not a["variable"] and abs(a["fps"] - 30) < 0.05 and abs(a["sound_seconds"] - 6) < 0.1, a)
    b = fr.video_timing(fr.read_tracks(vfr))
    h.check("a phone-style variable frame rate is spotted (and its average read)",
            b and b["variable"] and abs(b["fps"] - 29.4) < 0.4 and b["min_fps"] < b["max_fps"], b)
    h.check("a file that isn't MP4 / MOV just can't be read (no error)",
            fr.read_tracks(os.path.join(folder, "nothing.mkv")) is None)

    made = media.place(sc, vfr, frame=100)
    video = next(s for s in made if s.type == 'MOVIE')
    sound = next(s for s in made if s.type == 'SOUND')
    h.check("30 fps footage in the 24 fps project plays at real speed", abs(fr.plays_at(sc, video) - 1) < 0.01,
            fr.plays_at(sc, video))
    h.check("...so its picture and sound are the same length (in sync)",
            abs(clips.length(video) - clips.length(sound)) <= 1, (clips.length(video), clips.length(sound)))

    # A clip placed before (played every frame as a project frame: 80 % speed).
    sed = sc.sequence_editor
    old = sed.strips.new_movie("old", cfr, 12, 400)
    h.check("(an older clip plays slow)", abs(fr.plays_at(sc, old) - 0.8) < 0.01, fr.plays_at(sc, old))
    for s in sed.strips_all:
        s.select = s == old
    sed.active_strip = old
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.clip_real_speed()
    h.check("Play at Real Speed fixes it (6 s long again)",
            abs(fr.plays_at(sc, old) - 1) < 0.01 and abs(clips.length(old) - 6 * 24) <= 1,
            (fr.plays_at(sc, old), clips.length(old)))

    sed.active_strip = video
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.clip_frame_rate('INVOKE_DEFAULT')
    yield 0.5
    h.screenshot("frame_rate_check")
    h.key('ESC')
    yield 0.2


h.run(steps())
