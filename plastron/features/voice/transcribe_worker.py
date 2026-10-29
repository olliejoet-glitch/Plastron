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
    segments, info = model.transcribe(path, word_timestamps=True, initial_prompt=prompt or None,
                                      vad_filter=False, condition_on_previous_text=False)
    out = []
    for segment in segments:
        if info.duration:
            status(out_path, f"Transcribing {min(99, int(100 * segment.end / info.duration))}%")
        for w in segment.words or []:
            text = w.word.strip()
            if text:
                out.append([text, round(w.start, 3), round(w.end, 3)])
    return out


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
