"""The um checker (features/voice/ums.py): footage sound transcribed, ums
found and lit, separated into their own clips (video too), deleted with
ripple (the clips after close up, picture and sound stay in sync)."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ums = h.module("features.voice.ums")
transcribe = h.module("features.voice.transcribe")
takes = h.module("features.voice.takes")


def steps():
    yield 1.0
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base
    folder = os.path.join(bpy.app.tempdir, "ums")
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "talk.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=7",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=7",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", movie], check=True)
    made = media.place(sc, movie, frame=100)
    video = next(s for s in made if s.type == 'MOVIE')
    sound = next(s for s in made if s.type == 'SOUND')
    media.place(sc, movie, frame=clips.end(video))
    yield 0.3
    for s in clips.top_clips(sc):
        s.select = s == sound
    os.environ["PLASTRON_FAKE_WORDS"] = "so um this is uh really good"
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.ums(action='TRANSCRIBE')
    for _ in range(200):
        yield 0.1
        if not transcribe.busy():
            break
    yield 0.3
    sc = bpy.context.scene
    sound = sc.sequence_editor.strips_all[sound.name]
    h.check("footage sound gets a transcript (Transcribe in the Ums pop-up)",
            takes.is_voice(sound) and len(takes.words(takes.active_take(sound))) == 7,
            takes.words(takes.active_take(sound)) if takes.is_voice(sound) else None)
    found = ums.find(sc)
    h.check("Find: the two ums in it (in both clips of that footage: 4)",
            [takes.words(takes.active_take(u[0]))[u[3]][0] for u in found] == ["um", "uh", "um", "uh"], found)
    h.check("...each with half the gap either side", all(f1 - f0 >= 0.5 * 7 / 7 * fps * 0.8 for _s, f0, f1, _i in found),
            [(f0, f1) for _s, f0, f1, _i in found])
    um_frames = sum(f1 - f0 for _s, f0, f1, _i in found)
    vch = video.channel

    def span():
        on = clips.on_channel(bpy.context.scene, vch)
        return max(map(clips.end, on)) - min(map(clips.start, on))
    total = span()
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.ums(action='FIND')
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.5
    h.screenshot("ums_found")

    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.ums(action='SEPARATE')
    yield 0.3
    sc = bpy.context.scene
    marked = ums.marked(sc)
    h.check("Separate: each um is its own clip, the picture with it (8 clips), selected",
            len(marked) == 8 and sorted(s.type for s in marked) == ['MOVIE'] * 4 + ['SOUND'] * 4
            and all(s.select for s in marked) and not any(s.select for s in clips.top_clips(sc) if s not in marked),
            [(s.name, s.type) for s in marked])
    h.screenshot("ums_separated")
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.ums(action='DELETE')
    yield 0.4
    sc = bpy.context.scene
    after = span()
    h.check("Delete: the ums go and the clips after close up (ripple)", not ums.marked(sc) and after == total - um_frames,
            (total, um_frames, after))
    pics = sorted((clips.start(s), clips.end(s)) for s in clips.on_channel(sc, vch))
    snds = sorted((clips.start(s), clips.end(s)) for s in clips.on_channel(sc, sound.channel))
    h.check("...picture and sound still line up", pics == snds and len(pics) == 6, (pics, snds))
    h.check("...and no ums are left to find", ums.find(sc) == [], ums.find(sc))


h.run(steps())
