"""The microphone: records into memory, writes a WAV file.

Uses the sounddevice package (installed by core/deps.py). With
PLASTRON_FAKE_MIC set (tests) it "records" a quiet tone instead.
"""

import os
import threading
import time
import wave

import numpy as np

from ...config import voice as cfg


class _SoundDevice:
    def __init__(self):
        import sounddevice
        self.chunks, self.lock = [], threading.Lock()
        self.stream = sounddevice.InputStream(samplerate=cfg.SAMPLE_RATE, channels=cfg.CHANNELS,
                                              dtype='int16', callback=self._callback)
        self.stream.start()

    def _callback(self, indata, _frames, _time, _status):
        with self.lock:
            self.chunks.append(indata.copy())

    def stop(self):
        self.stream.stop()
        self.stream.close()
        with self.lock:
            return np.concatenate(self.chunks) if self.chunks else np.zeros((0, cfg.CHANNELS), np.int16)


class _FakeMic:
    """Tests: a tone as long as the recording ran."""

    def __init__(self):
        self.started = time.monotonic()

    def stop(self):
        n = int((time.monotonic() - self.started) * cfg.SAMPLE_RATE)
        t = np.arange(n) / cfg.SAMPLE_RATE
        tone = (np.sin(2 * np.pi * 220 * t) * 3000 * (0.6 + 0.4 * np.sin(2 * np.pi * 2 * t)))
        return np.repeat(tone.astype(np.int16)[:, None], cfg.CHANNELS, axis=1)


def fake():
    return bool(os.environ.get("PLASTRON_FAKE_MIC"))


def ready():
    """Can we record? (False while sounddevice isn't installed yet.)"""
    if fake():
        return True
    from ...core import deps
    return deps.available("sounddevice")


def start():
    return _FakeMic() if fake() else _SoundDevice()


def write_wav(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(samples.shape[1] if samples.ndim > 1 else 1)
        w.setsampwidth(2)
        w.setframerate(cfg.SAMPLE_RATE)
        w.writeframes(np.ascontiguousarray(samples, np.int16).tobytes())
    return samples.shape[0] / cfg.SAMPLE_RATE
