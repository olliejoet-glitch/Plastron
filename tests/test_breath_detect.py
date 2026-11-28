"""Breath detector (features/audio/breaths.py): Find shows the breaths on
the timeline (kept on the recording); Separate cuts them out as selected
clips; Delete removes them with ripple. Plus Export Audio (selected clips
only / whole mix) and Export Video's resolution choice."""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

breaths = h.module("features.audio.breaths")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
events = h.module("timeline.events")
audio_export = h.module("features.export.audio")
video = h.module("features.export.video")

RATE = 48000


def write_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def tone(seconds, peak, freq):
    t = np.arange(int(seconds * RATE)) / RATE
    return (peak * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def wav_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def band_noise(seconds, rms, lo_hz, hi_hz, rng):
    """Noise with its energy between lo_hz and hi_hz, at rms."""
    n = int(seconds * RATE)
    spec = np.fft.rfft(rng.randn(n))
    f = np.fft.rfftfreq(n, 1.0 / RATE)
    spec[(f < lo_hz) | (f > hi_hz)] = 0
    y = np.fft.irfft(spec, n)
    return (y / np.sqrt(np.mean(y ** 2)) * rms).astype(np.float32)


def steps():
    yield 1.0
    # Ollie: "it's marking sibilant noises, and missing the quieter breaths".
    analysis = h.module("features.audio.analysis")
    cfg = h.module("config.audio")
    rng = np.random.RandomState(7)
    x = (rng.randn(int(7 * RATE)) * 0.0005).astype(np.float32)               # room tone (-66 dB)
    x[24000:72000] += tone(1.0, 0.3, 220)                                     # words 0.5-1.5 s
    x[74400:84000] += band_noise(0.2, 0.02, 4500, 7500, rng)                  # an "s" (1.55-1.75 s)
    x[110400:158400] += tone(1.0, 0.3, 260)                                   # words 2.3-3.3 s
    x[172800:192000] += band_noise(0.4, 0.0007, 300, 3000, rng)               # a quiet breath (3.6-4.0 s)
    x[211200:259200] += tone(1.0, 0.3, 240)                                   # words 4.4-5.4 s
    p = write_wav(os.path.join(bpy.app.tempdir, "sibilant.wav"), x)
    got = breaths.find(analysis.read(p, cfg.ANALYSIS_RATE), cfg.ANALYSIS_RATE)
    h.check("the quiet breath is found, the sibilant isn't",
            len(got) == 1 and 3.5 < got[0][0] < 3.75 and 3.85 < got[0][1] < 4.1, got)
    sc = bpy.context.scene
    bpy.context.window_manager.plastron_mode = 'Audio'
    yield 1.0
    fps = sc.render.fps / sc.render.fps_base
    folder = os.path.join(bpy.app.tempdir, "breathdetect")
    os.makedirs(folder, exist_ok=True)
    rng = np.random.RandomState(3)
    x = (rng.randn(int(6 * RATE)) * 0.0005).astype(np.float32)              # room tone
    x[24000:72000] += tone(1.0, 0.3, 220)                                   # words
    x[84000:100800] += (rng.randn(16800) * 0.01).astype(np.float32)          # breath 1 (1.75-2.1 s)
    x[110400:158400] += tone(1.0, 0.3, 260)                                  # words
    x[170400:187200] += (rng.randn(16800) * 0.01).astype(np.float32)         # breath 2 (3.55-3.9 s)
    x[196800:244800] += tone(1.0, 0.3, 240)                                  # words
    path = write_wav(os.path.join(folder, "breathy.wav"), x)
    voice_track = next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == "Voice")
    voice_track.ripple = True
    voice = clips.editor(sc).strips.new_sound("breathy", path, tracks.channel_of(sc, voice_track), 1)
    events.clips_changed(sc)
    for s in clips.top_clips(sc):
        s.select = s == voice
    yield 0.3
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.breaths_find()
    yield 0.3
    sc = bpy.context.scene
    got = breaths.found(sc)
    secs = [((f0 - 1) / fps, (f1 - 1) / fps) for _s, f0, f1 in got]
    h.check("Find Breaths finds both breaths (and nothing else)",
            len(got) == 2 and 1.6 < secs[0][0] < 1.9 and 3.4 < secs[1][0] < 3.7, secs)
    h.check("...kept on the recording, nothing cut or dipped yet",
            breaths.FOUND in voice.sound and len(clips.on_channel(sc, voice.channel)) == 1 and breaths.KEY not in voice)
    h.redraw()
    yield 0.3
    h.screenshot("breaths_found")

    # Split the clip: each piece still shows its own breath.
    ripple = h.module("timeline.ripple")
    ripple.split(sc, [voice], 1 + round(2.8 * fps))
    yield 0.3
    sc = bpy.context.scene
    got = breaths.found(sc)
    h.check("cut in two, each piece still shows its breath", len(got) == 2 and got[0][0] != got[1][0],
            [(s.name, f0) for s, f0, _f1 in got])

    # Separate: each breath its own clip, selected.
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.breaths_cut(delete=False)
    yield 0.3
    sc = bpy.context.scene
    cut = breaths.marked(sc)
    h.check("Separate cuts each breath out into its own clip, all selected",
            len(cut) == 2 and all(s.select for s in cut)
            and all(0.25 * fps < clips.length(s) < 0.6 * fps for s in cut),
            [(s.name, clips.length(s)) for s in cut])
    end_before = max(clips.end(s) for s in clips.on_channel(sc, voice_track and tracks.channel_of(sc, voice_track)))
    total = sum(clips.length(s) for s in cut)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.breaths_cut(delete=True)
    yield 0.3
    sc = bpy.context.scene
    ch = tracks.channel_of(sc, voice_track)
    end_after = max(clips.end(s) for s in clips.on_channel(sc, ch))
    h.check("Delete removes them and the track closes up (ripple)",
            not breaths.marked(sc) and end_after == end_before - total, (end_before, end_after, total))

    # Export Audio: only the selected clip, over its own stretch; else the whole mix.
    piece = clips.on_channel(sc, ch)[0]
    for s in clips.top_clips(sc):
        s.select = s == piece
    out = os.path.join(folder, "selected.wav")
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.export_audio(filepath=out, fmt='WAV', selected_only=True)
    yield 0.3
    h.check("Export Audio (selected only) writes just that clip's stretch",
            os.path.exists(out) and abs(wav_seconds(out) - clips.length(piece) / fps) < 0.1,
            (os.path.exists(out) and wav_seconds(out), clips.length(piece) / fps))
    whole = os.path.join(folder, "whole.flac")
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.export_audio(filepath=whole, fmt='FLAC', selected_only=False)
    yield 0.3
    h.check("...or the whole mix (FLAC)", os.path.exists(whole) and os.path.getsize(whole) > 1000)
    h.check("...and the project's range / mutes are as they were",
            not any(s.mute for s in clips.top_clips(sc)))

    # Export Video: another resolution than the preset's.
    preset = video.preset_named("YouTube 4K")
    small = video.sized(preset, "720p")
    h.check("Export Video at another resolution (720p from the 4K preset; the codec kept)",
            (small["width"], small["height"]) == (1280, 720) and small["codec"] == preset["codec"]
            and video.sized(preset, "PRESET") == preset, (small["width"], small["height"]))
    mp4 = os.path.join(folder, "small.mp4")
    sc.frame_end = sc.frame_start + 12
    sc.plastron_timeline.range_auto = False
    video.export(bpy.context, mp4, video.sized(video.preset_named("Animatic (quick)") or preset, "360p"))
    import subprocess
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", mp4], capture_output=True, text=True)
    h.check("...the file comes out at that size (640×360)", probe.stdout.strip() == "640,360", probe.stdout)


h.run(steps())
