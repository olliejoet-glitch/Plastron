"""Link / unlink clips by hand (timeline/link.py): Ctrl+Alt+L on the
selected clips; linked clips cut, delete and ripple together."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "link")
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "phone.mp4")
    wav = os.path.join(folder, "mic.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", movie], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=4", wav],
                   check=True)
    video = media.place(sc, movie, frame=200)[0]
    sound = media.place(sc, wav, frame=200)[0]
    yield 0.3
    h.check("(a picture-only video and a separate sound, not linked)",
            video.type == 'MOVIE' and sound.type == 'SOUND' and not clips.linked(video), (video.type, sound.type))
    for s in clips.top_clips(sc):
        s.select = s in (video, sound)
    area = h.area('SEQUENCE_EDITOR')
    reg = h.region(area)
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    h.key('L', ctrl=True, alt=True)
    yield 0.3
    sc = bpy.context.scene
    video, sound = (sc.sequence_editor.strips_all[n] for n in (video.name, sound.name))
    h.check("Ctrl+Alt+L links the selected clips", clips.linked(video) == [sound], clips.linked(video))
    right = ripple.split(sc, [video], 240)
    yield 0.2
    h.check("cutting the video cuts its linked sound too", len(right) == 2, [s.name for s in right])
    ripple.delete(sc, [s for s in right if s.type == 'MOVIE'])
    yield 0.2
    h.check("deleting the video's right half deletes the sound's too",
            all(n.name not in sc.sequence_editor.strips_all for n in right))
    for s in clips.top_clips(sc):
        s.select = s in (video, sound)
    h.key('L', ctrl=True, alt=True)
    yield 0.3
    sc = bpy.context.scene
    video, sound = (sc.sequence_editor.strips_all[n] for n in (video.name, sound.name))
    h.check("Ctrl+Alt+L again unlinks them (Blender's connection too)",
            not clips.linked(video) and not clips.linked(sound) and not len(video.connections),
            (clips.linked(video), len(video.connections)))
    names = (video.name, sound.name)          # (a deleted clip's Python object can't be read after)
    ripple.delete(sc, [video])
    yield 0.2
    h.check("...and the sound now stays when the video goes",
            names[1] in sc.sequence_editor.strips_all and names[0] not in sc.sequence_editor.strips_all,
            ([s.name for s in sc.sequence_editor.strips_all], names))


h.run(steps())
