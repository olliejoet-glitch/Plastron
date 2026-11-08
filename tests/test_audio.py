"""Audio mode: layout, Sound panel, loudness (LUFS) + Normalise, auto-ducking,
beat markers."""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.audio")
analysis = h.module("features.audio.analysis")
loudness = h.module("features.audio.loudness")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
events = h.module("timeline.events")

RATE = 48000


def write_wav(path, x, rate=RATE):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def tone(seconds, peak=0.1, freq=997.0):
    t = np.arange(int(seconds * RATE)) / RATE
    return (peak * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def track_named(sc, name):
    return next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == name)


def add_sound(sc, path, track, start):
    ch = tracks.channel_of(sc, track)
    s = clips.editor(sc).strips.new_sound(os.path.basename(path), path, ch, start)
    return s


def steps():
    yield 1.0
    sc = bpy.context.scene
    wm = bpy.context.window_manager
    wm.plastron_mode = 'Audio'
    yield 1.0
    kinds = sorted((a.type, getattr(a.spaces.active, "view_type", "")) for a in h.window().screen.areas)
    tl = h.area('SEQUENCE_EDITOR')
    h.check("Audio mode: the picture over a big timeline with its Sound sidebar",
            kinds == [('SEQUENCE_EDITOR', 'PREVIEW'), ('SEQUENCE_EDITOR', 'SEQUENCER')]
            and tl.spaces.active.show_region_ui and tl.height > h.area('PREVIEW').height, kinds)

    folder = os.path.join(bpy.app.tempdir, "audio")
    os.makedirs(folder, exist_ok=True)
    quiet = write_wav(os.path.join(folder, "voice.wav"), tone(4, 0.1))           # -23 LUFS
    lufs = analysis.loudness(analysis.read(quiet, RATE), RATE)
    h.check("loudness measured like YouTube (a -20 dBFS sine = -23 LUFS)", abs(lufs + 23.0) < 0.2, lufs)

    voice = add_sound(sc, quiet, track_named(sc, "Voice"), 1)
    music = add_sound(sc, write_wav(os.path.join(folder, "music.wav"), tone(4, 0.1, 440.0)),
                      track_named(sc, "Music"), 1)
    events.clips_changed(sc)
    for s in clips.all_clips(sc):
        s.select = s in (voice, music)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.audio_normalise(which='SELECTED')
    after_v = analysis.loudness(analysis.clip_samples(sc, voice, RATE) * voice.plastron.volume, RATE)
    after_m = analysis.loudness(analysis.clip_samples(sc, music, RATE) * music.plastron.volume, RATE)
    h.check("Normalise: the voice lands on its target", abs(after_v - cfg.TARGETS["voice"]) < 0.3,
            (after_v, voice.plastron.volume))
    h.check("...the music on its (quieter) target", abs(after_m - cfg.TARGETS["music"]) < 0.3,
            (after_m, music.plastron.volume))
    yield 0.2
    h.check("...and the clips play at that volume (the mix writes it)",
            abs(voice.volume - voice.plastron.volume * track_named(sc, "Voice").volume) < 1e-4, voice.volume)

    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.5
    h.screenshot("audio_mode")
    yield from more_steps(sc, folder, voice, music)


def vol_at(sc, strip, frame):
    sc.frame_set(frame)
    return strip.volume


def more_steps(sc, folder, voice, music):
    # --- Auto-ducking: the music dips under the voice.
    fps = sc.render.fps / sc.render.fps_base
    x = np.zeros(int(6 * RATE), np.float32)
    for a, b in ((1.0, 2.0), (3.5, 4.5)):
        x[int(a * RATE):int(b * RATE)] = tone(b - a, 0.3)
    for s in (voice, music):
        clips.editor(sc).strips.remove(s)
    talk = add_sound(sc, write_wav(os.path.join(folder, "talk.wav"), x), track_named(sc, "Voice"), 1)
    bed = add_sound(sc, write_wav(os.path.join(folder, "bed.wav"), tone(6, 0.1, 220.0)), track_named(sc, "Music"), 1)
    events.clips_changed(sc)
    yield 0.2
    music_track = track_named(sc, "Music")
    music_track.duck = True
    yield 0.3
    g = 10 ** (cfg.DUCK_DB / 20)
    f = lambda t: 1 + round(t * fps)        # noqa: E731  (seconds -> frame; clips start at frame 1)
    quiet, talking, gap, after = (vol_at(sc, bed, f(0.5)), vol_at(sc, bed, f(1.5)), vol_at(sc, bed, f(2.9)),
                                  vol_at(sc, bed, f(5.5)))
    h.check("Duck on Music: it dips under the voice while someone talks",
            abs(talking - g) < 0.02 and abs(quiet - 1.0) < 0.02 and abs(after - 1.0) < 0.02,
            (quiet, talking, after))
    h.check("...and comes back up in a pause longer than DUCK_GAP", abs(gap - 1.0) < 0.05, gap)
    h.check("...ramping (attack before the voice starts)", g < vol_at(sc, bed, f(1.0 - cfg.DUCK_ATTACK / 2)) < 1.0,
            vol_at(sc, bed, f(1.0 - cfg.DUCK_ATTACK / 2)))
    track_named(sc, "Music").volume = 0.5
    yield 0.3
    h.check("...on top of the mix volume (track at 50 %)", abs(vol_at(sc, bed, f(1.5)) - 0.5 * g) < 0.02
            and abs(vol_at(sc, bed, f(0.5)) - 0.5) < 0.02, (vol_at(sc, bed, f(1.5)), vol_at(sc, bed, f(0.5))))
    clips.apply(sc, {talk: (clips.start(talk) + 24, clips.end(talk) + 24)})
    events.clips_changed(sc)
    yield 0.3
    h.check("moving the voice moves the dip", abs(vol_at(sc, bed, f(1.5)) - 0.5) < 0.05
            and abs(vol_at(sc, bed, f(2.5)) - 0.5 * g) < 0.02, (vol_at(sc, bed, f(1.5)), vol_at(sc, bed, f(2.5))))
    music_track.duck = False
    yield 0.3
    h.check("Duck off: the music plays flat again", abs(vol_at(sc, bed, f(2.5)) - 0.5) < 0.02, vol_at(sc, bed, f(2.5)))
    yield from beat_steps(sc, folder)


def beat_steps(sc, folder):
    yield 0.1


h.run(steps())
