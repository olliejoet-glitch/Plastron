"""Level Voice (features/audio/level.py): quiet stretches inside a recording
(leaning back from the mic) come up to the voice's usual level; loud ones
stay; long pauses get no boost; kept on the recording, so cuts keep it."""
import os
import sys
import wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

level = h.module("features.audio.level")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")

RATE = 48000


def voice(seconds, db, rng):
    """Speech-like sound: noisy syllables at db, with short gaps."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    syll = (np.sin(2 * np.pi * 4.0 * t) > -0.3).astype(np.float32)        # ~4 syllables / s
    tone = 0.6 * np.sin(2 * np.pi * 180 * t) + 0.4 * rng.standard_normal(n)
    return (10 ** (db / 20) * 0.3 * syll * tone).astype(np.float32)


def write(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def gain_at(scene, strip, seconds):
    """The level curve's gain at a time in the recording."""
    pts = level.points(scene, strip)
    fps = scene.render.fps / scene.render.fps_base
    frames = [f for f, _g in pts]
    return float(np.interp(strip.content_start + seconds * fps, frames, [g for _f, g in pts]))


def steps():
    yield 1.0
    sc = bpy.context.scene
    rng = np.random.default_rng(1)
    noise = lambda s: (1e-3 * rng.standard_normal(int(s * RATE))).astype(np.float32)   # noqa: E731
    # 0-6 s normal, 6-12 s leaning back (-14 dB), 12-18 s normal, 18-21 s silence, 21-27 s normal.
    x = np.concatenate([voice(6, 0, rng), voice(6, -14, rng), voice(6, 0, rng), noise(3), voice(6, 0, rng)])
    x[: len(x)] += (1e-3 * rng.standard_normal(len(x))).astype(np.float32)
    path = os.path.join(bpy.app.tempdir, "lean_back.wav")
    write(path, x)
    track = next(t for t in tracks.all_tracks(sc) if t.kind == 'AUDIO')
    strip = clips.editor(sc).strips.new_sound("Lean back", path, tracks.channel_of(sc, track), 1)
    yield 0.3
    sc = bpy.context.scene
    strip = sc.sequence_editor.strips_all["Lean back"]
    for s in clips.top_clips(sc):
        s.select = s == strip
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.level_voice()
    yield 0.4
    sc = bpy.context.scene
    strip = sc.sequence_editor.strips_all["Lean back"]
    quiet, loud, pause = gain_at(sc, strip, 9.0), gain_at(sc, strip, 3.0), gain_at(sc, strip, 19.5)
    db = lambda g: 20 * np.log10(max(g, 1e-6))          # noqa: E731
    h.check("the quiet stretch (leaning back) comes up most of the way (14 dB down -> +10 dB or more)",
            db(quiet) >= 10.0, round(db(quiet), 1))
    h.check("...the normal stretches stay about where they are", abs(db(loud)) < 2.0, round(db(loud), 1))
    h.check("...a long pause gets no boost (room noise isn't pumped up)", db(pause) <= 0.5, round(db(pause), 1))
    h.check("...kept once, on the recording", level.KEY in strip.sound and len(strip.sound[level.KEY]) > 4)
    fc = next((f for f in sc.animation_data.action.layers[0].strips[0].channelbags[0].fcurves
               if f.data_path == f'sequence_editor.strips_all["{strip.name}"].volume'), None) \
        if sc.animation_data and sc.animation_data.action else None
    fps = sc.render.fps / sc.render.fps_base
    h.check("the clip's volume follows it on the timeline (louder in the quiet stretch)",
            fc is not None and fc.evaluate(1 + 9 * fps) > 2.5 * fc.evaluate(1 + 3 * fps),
            fc and (fc.evaluate(1 + 9 * fps), fc.evaluate(1 + 3 * fps)))

    # Cut it up: each piece keeps its part (the curve is the recording's).
    right = ripple.split(sc, [strip], int(1 + 8 * fps))
    yield 0.4
    sc = bpy.context.scene
    r = right[0] if right else None
    h.check("a piece cut from it keeps its part of the curve",
            r is not None and abs(gain_at(sc, r, 9.0) - quiet) < 0.05, r and gain_at(sc, r, 9.0))
    with h.override('SEQUENCE_EDITOR'):
        for s in clips.top_clips(sc):
            s.select = s.type == 'SOUND'
        bpy.ops.plastron.level_clear()
    yield 0.3
    sc = bpy.context.scene
    h.check("Clear Level puts it back", not any(level.KEY in s.sound for s in clips.top_clips(sc)
                                                if s.type == 'SOUND' and s.sound))


h.run(steps())
