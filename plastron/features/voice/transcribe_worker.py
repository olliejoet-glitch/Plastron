"""Transcribes one recording. Runs in its own Python process (started by
transcribe.py), so Blender never waits on it.

    python transcribe_worker.py <in.wav> <out.json> <model> <prompt> [--fake]

Writes {"words": [[word, start s, end s], ...]} or {"error": "..."}.
--fake (tests): spreads PLASTRON_FAKE_WORDS evenly over the recording.
"""

import json
import os
import sys
import wave


def fake(path):
    with wave.open(path) as w:
        duration = w.getnframes() / w.getframerate()
    text = os.environ.get("PLASTRON_FAKE_WORDS", "one two three four five six seven eight")
    names = text.split()
    step = duration / max(1, len(names))
    return [[n, round(i * step + 0.02, 3), round((i + 0.8) * step, 3)] for i, n in enumerate(names)]


def whisper(path, model_name, prompt):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(path, word_timestamps=True, initial_prompt=prompt or None,
                                       vad_filter=False, condition_on_previous_text=False)
    out = []
    for segment in segments:
        for w in segment.words or []:
            text = w.word.strip()
            if text:
                out.append([text, round(w.start, 3), round(w.end, 3)])
    return out


def main(argv):
    wav, out_path, model_name, prompt = argv[1:5]
    try:
        result = {"words": fake(wav) if "--fake" in argv else whisper(wav, model_name, prompt)}
    except Exception as err:          # reported in Plastron, never a crash
        result = {"error": f"{type(err).__name__}: {err}"}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main(sys.argv)
