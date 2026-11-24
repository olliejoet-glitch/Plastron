"""Transcribes one recording. Runs in its own Python process (started by
transcribe.py), so Blender never waits on it.

    python transcribe_worker.py <in.wav> <out.json> <model> <prompt> [--fake]

Writes {"words": [[word, start s, end s], ...]} or {"error": "..."} to
out.json, and what it's doing ("getting the speech model", "45%") to
out.json.status as it goes, for Plastron's header.
--fake (tests): spreads PLASTRON_FAKE_WORDS evenly over the recording.
"""

import json
import os
import sys
import time
import traceback
import wave

# ctranslate2 and onnxruntime can each bring their own OpenMP; on Windows
# loading both aborts the process unless this is set.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def status(out_path, text):
    try:
        with open(out_path + ".status", "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def fake(path, out_path):
    status(out_path, "Transcribing...")
    with wave.open(path) as w:
        duration = w.getnframes() / w.getframerate()
    text = os.environ.get("PLASTRON_FAKE_WORDS", "one two three four five six seven eight")
    names = text.split()
    step = duration / max(1, len(names))
    return [[n, round(i * step + 0.02, 3), round((i + 0.8) * step, 3)] for i, n in enumerate(names)]


def load_audio(path, rate=16000):
    """Our WAV recordings -> mono float32 at 16 kHz, what Whisper wants.
    (Done here, not by faster-whisper, whose PyAV-based loader breaks with
    newer PyAV versions.)"""
    import numpy as np
    with wave.open(path) as w:
        channels, width, src = w.getnchannels(), w.getsampwidth(), w.getframerate()
        data = w.readframes(w.getnframes())
    kind = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    audio = np.frombuffer(data, kind).astype(np.float32)
    if width == 1:
        audio -= 128.0
    audio /= float(2 ** (8 * width - 1))
    audio = audio.reshape(-1, channels).mean(axis=1)
    if src == rate:
        return audio
    if src % rate == 0:
        # Low-pass (windowed sinc, cut at the new Nyquist) then keep every n-th sample.
        n = src // rate
        taps = np.arange(-32, 33)
        kernel = np.sinc(taps / n) * np.hamming(len(taps))
        kernel /= kernel.sum()
        return np.convolve(audio, kernel, mode="same")[::n].astype(np.float32)
    t = np.arange(int(len(audio) * rate / src)) * (src / rate)
    return np.interp(t, np.arange(len(audio)), audio).astype(np.float32)


def _model_cached(model_name):
    hub = os.path.join(os.environ.get("HF_HOME", ""), "hub")
    return os.path.isdir(hub) and any(model_name in d for d in os.listdir(hub))


def whisper(path, model_name, prompt, out_path):
    status(out_path, "Starting the transcriber...")
    from faster_whisper import WhisperModel
    if not _model_cached(model_name):
        status(out_path, "Getting the speech model (first time only, a few hundred MB)...")
    else:
        status(out_path, "Loading the speech model...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    status(out_path, "Transcribing 0%")
    kw = dict(word_timestamps=True, initial_prompt=prompt or None, vad_filter=False,
              condition_on_previous_text=False)
    # The prompt (full of "um"s) only reaches Whisper's first 30 s window; after
    # that it tidied the ums away (Ollie: "missing 90% of them"). Hotwords go
    # into every window.
    import inspect
    if prompt and "hotwords" in inspect.signature(model.transcribe).parameters:
        kw["hotwords"] = prompt
    segments, info = model.transcribe(load_audio(path), **kw)
    out = []
    for segment in segments:
        if info.duration:
            status(out_path, f"Transcribing {min(99, int(100 * segment.end / info.duration))}%")
        for w in segment.words or []:
            text = w.word.strip()
            if text:
                out.append([text, round(w.start, 3), round(w.end, 3)])
    fillers = fillers_wanted()
    if fillers:
        audio = load_audio(path)

        def listen(snippet):
            segs, _info = model.transcribe(snippet, word_timestamps=True, initial_prompt=FILLER_PROMPT,
                                           vad_filter=False, condition_on_previous_text=False,
                                           language="en", without_timestamps=False)
            return [(w.word.strip(), w.start, w.end) for seg in segs for w in (seg.words or [])]
        out = second_pass(out, audio, 16000, listen, fillers, out_path)
    return out


# --- Second pass: ums Whisper tidied away -----------------------------------------------------
# Whisper leaves many fillers out of a long transcript (and stretches the word
# next to one over it). Every suspicious spot is listened to again on its own,
# with Whisper told to expect fillers: voice in a gap between words, and words
# far longer than their letters need. Fillers it hears there are added.

FILLER_PROMPT = "Um, uh, umm, er, hmm. Uh, um, so, uh, yeah."


def _clean(word):
    return word.strip(" ,.!?;:-\u2026\"'").lower()


def _envelope(audio, rate, hop=0.02):
    import numpy as np
    n = int(hop * rate)
    m = len(audio) // n
    if m == 0:
        return np.zeros(0)
    rms = np.sqrt(np.mean(audio[:m * n].reshape(m, n) ** 2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def filler_candidates(words, audio, rate, hop=0.02):
    """Pure: [(start s, end s, kind, word index)] to listen to again:
    'gap' (voice between two words) and 'long' (a word much longer than its
    letters need: an um swallowed into it)."""
    import numpy as np
    env = _envelope(audio, rate, hop)
    if not len(env):
        return []
    loud = float(np.percentile(env, 95))
    voiced = env >= loud - 25
    total = len(env) * hop
    out = []
    bounds = [(None, 0.0)] + [(i, w[2]) for i, w in enumerate(words)]
    starts = [w[1] for w in words] + [total]
    for (i, g0), g1 in zip(bounds, starts):
        if g1 - g0 < 0.15:
            continue
        a, b = int(g0 / hop), int(g1 / hop)
        if voiced[a:b].sum() * hop >= 0.12:
            out.append((max(0.0, g0 - 0.05), min(total, g1 + 0.05), "gap", i))
    for i, (word, s, e) in enumerate(words):
        letters = sum(ch.isalpha() for ch in word)
        if e - s > max(0.9, 0.35 + 0.08 * letters):
            out.append((max(0.0, s - 0.05), min(total, e + 0.05), "long", i))
    return out


def merge_fillers(words, heard, fillers):
    """Pure: words with the fillers heard in candidates added.
    heard: [((start, end, kind, index), [(word, s, e) in the transcript's time])].
    A long word gives up the part its filler took."""
    words = [list(w) for w in words]
    added = []
    for (a, b, kind, index), got in heard:
        found = [(w, s, e) for w, s, e in got if _clean(w) in fillers]
        if not found:
            continue
        for w, s, e in found:
            s, e = max(a, s), min(b, e)
            if e - s < 0.05:
                continue
            if kind == "long" and index is not None:
                word = words[index]
                if s - word[1] >= e - word[2] or abs(s - word[1]) > abs(e - word[2]):
                    word[2] = min(word[2], max(word[1] + 0.05, s))      # (the filler came after)
                else:
                    word[1] = max(word[1], min(word[2] - 0.05, e))      # (before)
            added.append([w.strip(), round(s, 3), round(e, 3)])
    existing = [(s, e) for w, s, e in words if _clean(w) in fillers]
    for f in sorted(added, key=lambda x: x[1]):
        if not any(s < f[2] and f[1] < e for s, e in existing):
            words.append(f)
            existing.append((f[1], f[2]))
    words.sort(key=lambda w: w[1])
    return words


def second_pass(words, audio, rate, listen, fillers, out_path=None):
    """listen(snippet) -> [(word, s, e)] in the snippet's time."""
    cands = filler_candidates(words, audio, rate)
    heard = []
    for k, c in enumerate(cands):
        if out_path and k % 10 == 0:
            status(out_path, f"Listening for ums {k}/{len(cands)}")
        a, b = c[0], c[1]
        snippet = audio[int(a * rate):int(b * rate)]
        if len(snippet) < int(0.1 * rate):
            continue
        try:
            got = [(w, a + s, a + e) for w, s, e in listen(snippet)]
        except Exception as err:          # (one snippet failing never stops the transcript)
            print("Plastron: um pass skipped a spot:", err)
            continue
        heard.append((c, got))
    return merge_fillers(words, heard, fillers)


def fillers_wanted():
    try:
        return set(json.loads(os.environ.get("PLASTRON_FILLERS", "[]")))
    except ValueError:
        return set()


def main(argv):
    wav, out_path, model_name, prompt = argv[1:5]
    started = time.time()
    try:
        words = fake(wav, out_path) if "--fake" in argv else whisper(wav, model_name, prompt, out_path)
        result = {"words": words}
        print(f"Transcribed {os.path.basename(wav)}: {len(words)} words in {time.time() - started:.1f} s")
    except Exception as err:          # reported in Plastron, never a crash
        traceback.print_exc()
        result = {"error": f"{type(err).__name__}: {err}"}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main(sys.argv)
