"""Audio mode's sound tools: breath remover, creature voices, music fitting."""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.audio")
analysis = h.module("features.audio.analysis")
breaths = h.module("features.audio.breaths")
creature = h.module("features.audio.creature")
fit = h.module("features.audio.fit")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
events = h.module("timeline.events")
panels = h.module("features.storyboard.panels")

RATE = 48000


def write_wav(path, x, rate=RATE):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def tone(seconds, peak, freq):
    t = np.arange(int(seconds * RATE)) / RATE
    return (peak * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def track_named(sc, name):
    return next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == name)


def vol_at(sc, strip, frame):
    sc.frame_set(frame)
    return strip.volume


def select_only(sc, strip):
    for s in clips.all_clips(sc):
        s.select = s == strip
    sc.sequence_editor.active_strip = strip


def steps():
    yield 1.0
    sc = bpy.context.scene
    bpy.context.window_manager.plastron_mode = 'Audio'
    yield 1.0
    fps = sc.render.fps / sc.render.fps_base
    folder = os.path.join(bpy.app.tempdir, "soundtools")
    os.makedirs(folder, exist_ok=True)

    # --- Breaths: voice (tones) with a quiet, noisy breath between.
    rng = np.random.RandomState(3)
    x = (rng.randn(int(4 * RATE)) * 0.0005).astype(np.float32)               # room tone
    x[24000:72000] += tone(1.0, 0.3, 220)
    x[84000:100800] += (rng.randn(16800) * 0.01).astype(np.float32)          # a breath (1.75-2.1 s)
    x[110400:158400] += tone(1.0, 0.3, 260)
    voice_path = write_wav(os.path.join(folder, "breathy.wav"), x)
    found = breaths.find(analysis.read(voice_path, cfg.ANALYSIS_RATE), cfg.ANALYSIS_RATE)
    h.check("the breath is found (and only it)", len(found) == 1 and 1.65 < found[0][0] < 1.85
            and 1.95 < found[0][1] < 2.2, found)
    voice = clips.editor(sc).strips.new_sound("breathy", voice_path, tracks.channel_of(sc, track_named(sc, "Voice")), 1)
    events.clips_changed(sc)
    select_only(sc, voice)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.breaths_remove()
    yield 0.2
    f = lambda t, s=voice: clips.start(s) + round(t * fps)       # noqa: E731
    g = 10 ** (cfg.BREATH_DB / 20)
    h.check("Remove Breaths: the breath dips, the words don't",
            abs(vol_at(sc, voice, f(1.9)) - g) < 0.02 and abs(vol_at(sc, voice, f(1.0)) - 1) < 0.02
            and abs(vol_at(sc, voice, f(2.8)) - 1) < 0.02,
            (vol_at(sc, voice, f(1.0)), vol_at(sc, voice, f(1.9)), vol_at(sc, voice, f(2.8))))
    clips.apply(sc, {voice: (clips.start(voice) + 30, clips.end(voice) + 30)})
    events.clips_changed(sc)
    yield 0.3
    h.check("...and the dip moves with the clip", abs(vol_at(sc, voice, f(1.9)) - g) < 0.02
            and abs(vol_at(sc, voice, f(1.0)) - 1) < 0.02, vol_at(sc, voice, f(1.9)))
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.breaths_keep()
    yield 0.2
    h.check("Keep Breaths: back to flat", abs(vol_at(sc, voice, f(1.9)) - 1) < 0.02, vol_at(sc, voice, f(1.9)))

    # --- Creature voice: the voice baked with pitched layers (same length).
    hum = clips.editor(sc).strips.new_sound("hum", write_wav(os.path.join(folder, "hum.wav"), tone(2, 0.3, 440)),
                                            tracks.channel_of(sc, track_named(sc, "Voice")), 200)
    events.clips_changed(sc)
    select_only(sc, hum)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.creature_bake(preset="Ogre")
    yield 0.3
    ogre = next((s for s in clips.all_clips(sc) if s.get("plastron_creature") == "Ogre"), None)
    ct = next((t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == cfg.CREATURE_TRACK), None)
    h.check("Creature (Ogre): a baked clip on the Creature track, the same span, linked; the voice muted",
            ogre is not None and ct is not None and ogre.channel == tracks.channel_of(sc, ct)
            and (clips.start(ogre), clips.end(ogre)) == (clips.start(hum), clips.end(hum))
            and clips.linked(hum) == [ogre] and hum.mute and ogre.sound.packed_file is not None,
            ogre and (clips.start(ogre), clips.end(ogre), clips.start(hum), clips.end(hum)))
    y = analysis.clip_samples(sc, ogre, RATE)
    spec = np.abs(np.fft.rfft(y[:RATE]))
    freqs = np.fft.rfftfreq(RATE, 1 / RATE)
    at = lambda hz: spec[np.argmin(np.abs(freqs - hz))]          # noqa: E731
    h.check("...an octave down is in it (220 Hz), the voice too (440 Hz), same length",
            at(220) > 0.3 * at(440) and at(440) > 0 and abs(len(y) - 2 * RATE) < RATE * 0.05,
            (at(220), at(440), len(y)))

    # --- Music fitting: a 120 BPM click track, video ending between beats.
    sc.frame_current = 1
    xs = (np.random.RandomState(1).randn(int(12 * RATE)) * 0.005).astype(np.float32)
    for k in range(24):
        i = int((0.25 + k * 0.5) * RATE)
        xs[i:i + 600] += (np.random.RandomState(k).randn(600) * 0.5).astype(np.float32)
    song = clips.editor(sc).strips.new_sound("song", write_wav(os.path.join(folder, "song.wav"), xs),
                                             tracks.channel_of(sc, track_named(sc, "Music")), 1)
    first = panels.all_panels(sc)[0]
    clips.apply(sc, {first: (clips.start(first), 1 + round(7.36 * fps))})      # the video: 7.36 s
    events.clips_changed(sc)
    yield 0.2
    end = fit.video_end(sc)
    marks = h.module("features.audio.beats").beat_frames(sc, song)
    select_only(sc, song)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.music_fit()
    yield 0.3
    speed = song.get("plastron_speed", 1.0)
    after = h.module("features.audio.beats").beat_frames(sc, song)
    h.check("Fit to Video: the music ends with the video, fading out",
            clips.end(song) == end and song.plastron.fade_out > 0, (clips.end(song), end, song.plastron.fade_out))
    h.check("...stretched a little so a beat lands on the end",
            abs(speed - 1) <= cfg.FIT_MAX_STRETCH and any(abs((b - 1) / speed + 1 - end) <= 1 for b in marks),
            (speed, end, marks[-4:]))
    del after
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.4
    h.screenshot("sound_tools")


h.run(steps())
