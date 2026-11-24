"""The transcriber's second listen for ums (transcribe_worker.second_pass):
suspicious spots (voice between words, a word far too long) are found and
fillers heard there are added to the words, the long word shortened."""
import importlib.util
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "transcribe_worker", os.path.join(ROOT, "plastron", "features", "voice", "transcribe_worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
FILLERS = {"um", "uh", "er"}


def steps():
    yield 0.5
    rate = 16000
    t = np.arange(int(8 * rate)) / rate
    audio = np.zeros_like(t, dtype=np.float32)

    def voice(a, b, amp=0.3):
        audio[int(a * rate):int(b * rate)] = amp * np.sin(2 * np.pi * 180 * t[int(a * rate):int(b * rate)])
    words = [["So", 0.2, 1.8],          # a "so" 1.6 s long: "so... um" swallowed in
             ["this", 2.0, 2.4], ["is", 2.5, 2.7],
             ["good", 4.0, 4.4], ["stuff", 4.5, 5.0]]
    for _w, a, b in words:
        voice(a, b)
    voice(3.0, 3.5)                      # an um between "is" and "good" with no word
    cands = worker.filler_candidates(words, audio, rate)
    kinds = sorted((c[2], c[3]) for c in cands)
    h.check("spots to listen to again: the voice between words and the over-long word",
            ("gap", 2) in kinds and ("long", 0) in kinds and len(cands) == 2, cands)

    def listen(snippet):
        dur = len(snippet) / rate
        if dur > 1.5:                        # the long "So": "So, um"
            return [("So,", 0.05, 0.6), ("um", 0.9, 1.5)]
        return [("Um.", 0.4, 0.8)]
    out = worker.second_pass(words, audio, rate, listen, FILLERS)
    names = [w[0] for w in out]
    h.check("fillers heard there are added in order", names == ["So", "um", "this", "is", "Um.", "good", "stuff"],
            out)
    so = out[0]
    um = out[1]
    h.check("...the long word gives up the part its um took", so[2] <= um[1] + 1e-6 and so[2] < 1.8, (so, um))
    h.check("...the gap's um sits in the gap", 2.7 <= out[4][1] < out[4][2] <= 4.0, out[4])
    out2 = worker.merge_fillers(out, [((2.6, 4.1, "gap", 2), [("um", 3.0, 3.4)])], FILLERS)
    h.check("an um already there isn't added twice", len(out2) == len(out), out2)
    h.check("nothing heard: the words stay as they were",
            worker.second_pass(words, audio, rate, lambda s: [("this", 0, 0.2)], FILLERS) == [list(w) for w in words])


h.run(steps())
