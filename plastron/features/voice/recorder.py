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


class _Chunks:
    """Collects the microphone's blocks of samples as they arrive (on the
    audio thread) and counts any it had to drop."""

    def __init__(self):
        self.chunks, self.lock = [], threading.Lock()
        self.dropped = 0

    def _add(self, block, status=None):
        with self.lock:
            self.chunks.append(block)
            if status:
                self.dropped += 1

    def _all(self):
        with self.lock:
            return np.concatenate(self.chunks) if self.chunks else np.zeros((0, cfg.CHANNELS), np.int16)


class _SoundDevice(_Chunks):
    def __init__(self, device=None):
        super().__init__()
        import sounddevice
        self.stream = sounddevice.InputStream(samplerate=cfg.SAMPLE_RATE, channels=cfg.CHANNELS,
                                              dtype='int16', device=device, callback=self._callback)
        self.stream.start()

    def _callback(self, indata, _frames, _time, status):
        self._add(indata.copy(), bool(status.input_overflow) if status else False)

    def stop(self):
        self.stream.stop()
        self.stream.close()
        return self._all()


class _FakeMic(_Chunks):
    """Tests: a tone, delivered like a real microphone: blocks of samples
    arriving on a thread in real time."""

    BLOCK = 1024

    def __init__(self, device=None):
        super().__init__()
        self.device = device
        self.started = time.monotonic()
        self.sent = 0
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _block(self, n):
        t = (self.sent + np.arange(n)) / cfg.SAMPLE_RATE
        tone = np.sin(2 * np.pi * 220 * t) * 3000 * (0.6 + 0.4 * np.sin(2 * np.pi * 2 * t))
        self.sent += n
        return np.repeat(tone.astype(np.int16)[:, None], cfg.CHANNELS, axis=1)

    def _run(self):
        while self.running:
            due = int((time.monotonic() - self.started) * cfg.SAMPLE_RATE)
            while self.sent + self.BLOCK <= due:
                self._add(self._block(self.BLOCK))
            time.sleep(self.BLOCK / cfg.SAMPLE_RATE / 2)

    def stop(self):
        self.running = False
        self.thread.join()
        due = int((time.monotonic() - self.started) * cfg.SAMPLE_RATE)
        if due > self.sent:
            self._add(self._block(due - self.sent))
        return self._all()


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
