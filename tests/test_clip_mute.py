"""Muting / unmuting clips (timeline/mute.py): H over the timeline toggles
the selected clips and their linked clips; speed playback never leaves the
project's sound off (saved or reopened)."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
speed = h.module("features.review.speed")


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "mute")
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "talk.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", movie], check=True)
    made = media.place(sc, movie, frame=100)
    names = [s.name for s in made]
    sound = next(s for s in made if s.type == 'SOUND')
    sound.mute = True                                  # (muted somehow)
    for s in clips.top_clips(sc):
        s.select = s.name == sound.name
    area = h.area('SEQUENCE_EDITOR')
    reg = h.region(area)
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    h.redraw()
    yield 0.2
    h.screenshot("clip_muted")
    h.key('H')
    yield 0.3
    sc = bpy.context.scene
    got = [sc.sequence_editor.strips_all[n].mute for n in names]
    h.check("H unmutes a muted clip (and its linked video)", got == [False, False], got)
    h.key('H')
    yield 0.3
    sc = bpy.context.scene
    got = [sc.sequence_editor.strips_all[n].mute for n in names]
    h.check("H again mutes them", got == [True, True], got)

    # A project saved mid speed playback: sound off, rate sped up.
    sc.use_audio = False
    sc.render.fps_base = 1.0 / 1.5
    speed._on_load(sc)
    h.check("reopening puts the project's sound and rate back", sc.use_audio and sc.render.fps_base == 1.0,
            (sc.use_audio, sc.render.fps_base))
    speed._state.update(active=True, handle=None, fps_base=1.0, use_audio=True, sync='AUDIO_SYNC', speed=1.5)
    sc.use_audio = False
    speed._before_save()
    h.check("saving during speed playback puts the sound back first", sc.use_audio and not speed._state["active"])


h.run(steps())
