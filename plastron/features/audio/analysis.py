"""Reading clips' sound as numbers (numpy) and measuring it: loudness
(LUFS, ITU BS.1770: K-weighting + gating), loudness envelope, beats.
Pure numpy; sounds are read with Blender's audaspace (aud)."""

import os

import aud
import bpy
import numpy as np

from ...config import audio as cfg
from ...timeline import clips

_cache = {}          # (path, rate) -> samples (mono float32)
_CACHE_MAX = 6


def sound_path(sound):
    """A file aud can read for a Blender sound (packed sounds: written once to temp)."""
    if sound.packed_file is not None:
        ext = os.path.splitext(sound.filepath)[1] or ".wav"        # (the reader goes by the file's kind)
        path = os.path.join(bpy.app.tempdir, f"plastron_sound_{abs(hash(sound.name))}_{sound.packed_file.size}{ext}")
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(sound.packed_file.data)
        return path
    return bpy.path.abspath(sound.filepath)


def read(path, rate):
    key = (path, rate)
    if key not in _cache:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        snd = aud.Sound(path).rechannel(1).resample(rate, False)
        _cache[key] = np.ascontiguousarray(snd.data()[:, 0], dtype=np.float32)
    return _cache[key]


def clip_samples(scene, strip, rate):
    """The part of a sound clip that plays (mono, at rate)."""
    if strip.type != 'SOUND' or strip.sound is None:
        return np.zeros(0, np.float32)
    data = read(sound_path(strip.sound), rate)
    fps = scene.render.fps / scene.render.fps_base
    a = int(max(0.0, (clips.start(strip) - strip.content_start) / fps) * rate)
    b = a + int(clips.length(strip) / fps * rate)
    return data[a:b]


# --- Loudness -------------------------------------------------------------------------------

def _k_weighting(n, rate):
    """|H(f)| of BS.1770's K-weighting (its two biquads at 48 kHz) for an rfft of n."""
    f = np.fft.rfftfreq(n, 1.0 / rate)
    z = np.exp(-2j * np.pi * f / 48000.0)

    def biquad(b, a):
        return (b[0] + b[1] * z + b[2] * z * z) / (1.0 + a[0] * z + a[1] * z * z)

    shelf = biquad((1.53512485958697, -2.69169618940638, 1.19839281085285), (-1.69065929318241, 0.73248077421585))
    high = biquad((1.0, -2.0, 1.0), (-1.99004745483398, 0.99007225036621))
    return np.abs(shelf * high)


def loudness(x, rate):
    """Integrated loudness (LUFS) of mono samples; None if silent."""
    if len(x) < int(0.4 * rate):
        return None
    spec = np.fft.rfft(x.astype(np.float64))
    y = np.fft.irfft(spec * _k_weighting(len(x), rate), len(x))
    block, step = int(0.4 * rate), int(0.1 * rate)
    sq = np.concatenate(([0.0], np.cumsum(y * y)))
    starts = np.arange(0, len(y) - block + 1, step)
    z = (sq[starts + block] - sq[starts]) / block
    lk = -0.691 + 10 * np.log10(np.maximum(z, 1e-12))
    z = z[lk > -70.0]                                        # absolute gate
    if len(z) == 0:
        return None
    rel = -0.691 + 10 * np.log10(z.mean()) - 10.0             # relative gate
    z = z[-0.691 + 10 * np.log10(z) > rel]
    return float(-0.691 + 10 * np.log10(z.mean())) if len(z) else None


def envelope_db(x, rate, hop):
    """Loudness over time: RMS in dB per hop seconds."""
    n = max(1, int(hop * rate))
    m = len(x) // n
    if m == 0:
        return np.zeros(0)
    rms = np.sqrt(np.mean(x[:m * n].reshape(m, n) ** 2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


_envelopes = {}      # (path, hop) -> dB per hop over the whole file


def file_envelope(path, hop):
    key = (path, hop)
    if key not in _envelopes:
        _envelopes[key] = envelope_db(read(path, cfg.ANALYSIS_RATE), cfg.ANALYSIS_RATE, hop)
    return _envelopes[key]


def clip_envelope(scene, strip, hop):
    """(dB per hop, the clip's start in seconds) for the part of a sound clip that plays."""
    if strip.type != 'SOUND' or strip.sound is None:
        return np.zeros(0), 0.0
    env = file_envelope(sound_path(strip.sound), hop)
    fps = scene.render.fps / scene.render.fps_base
    a = int(max(0.0, (clips.start(strip) - strip.content_start) / fps) / hop)
    n = int(clips.length(strip) / fps / hop)
    return env[a:a + n], clips.start(strip) / fps


# --- Beats ------------------------------------------------------------------------------------

def beats(x, rate):
    """Beat times (seconds) in mono samples: onset strength (spectral flux),
    tempo by autocorrelation, then the grid that lands on the most onsets."""
    n_fft, hop = 1024, 256
    if len(x) < n_fft * 4:
        return []
    frames = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    mag = np.abs(np.fft.rfft(x[idx] * np.hanning(n_fft), axis=1))
    logm = np.log1p(100 * mag)
    flux = np.maximum(0.0, np.diff(logm, axis=0)).sum(axis=1)
    flux = flux - np.convolve(flux, np.ones(16) / 16, mode="same")       # local mean removed
    flux = np.maximum(flux, 0)
    fr = rate / hop                                                   # onset frames per second
    lo, hi = cfg.BEAT_BPM
    lags = np.arange(max(1, int(fr * 60 / hi)), int(fr * 60 / lo) + 1)
    ac = np.array([np.dot(flux[:-l], flux[l:]) for l in lags])
    bpm = 60 * fr / lags
    ac = ac * np.exp(-0.5 * (np.log2(bpm / 120.0) / 0.9) ** 2)         # (prefer common tempi)
    period = lags[int(np.argmax(ac))]
    # Refine the period (sub-frame) and find the phase that hits the most onsets.
    best = None
    for p in np.linspace(period - 0.5, period + 0.5, 11):
        for phase in range(int(np.ceil(p))):
            pos = np.arange(phase, len(flux), p).astype(int)
            score = flux[pos].sum()
            if best is None or score > best[0]:
                best = (score, p, phase)
    _s, p, phase = best
    # (flux i = frame i -> i + 1: a hit shows as it enters the window, about n_fft after its start)
    return [(phase + k * p) / fr + n_fft / rate for k in range(int((len(flux) - phase) / p) + 1)]
