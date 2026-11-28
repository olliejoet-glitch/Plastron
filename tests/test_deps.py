"""Packages for transcription (core/deps.py, voice/transcribe.py): a missing
dotted package ("nvidia.cublas" with no nvidia at all) reads as missing
instead of stopping the queue (Ollie: "stuck on transcription waiting");
if the graphics-card libraries can't be installed, the queue carries on
(on the processor) instead of waiting for ever."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

deps = h.module("core.deps")
tr = h.module("features.voice.transcribe")


def steps():
    yield 0.5
    ok = True
    try:
        got = deps.available("plastron_no_such_package.sub")
    except Exception as err:            # (what used to happen)
        ok, got = False, repr(err)
    h.check("a dotted package whose parent isn't installed reads as missing (no error)", ok and got is False, got)
    h.check("...missing() lists it", deps.missing({"plastron_no_such_package.sub": "x"}) == ["x"])

    # Windows, base packages there, the graphics-card ones won't install.
    class FakeSys:
        platform = "win32"
    real = (tr.sys, deps.ensure, deps.missing, deps.installing)
    calls = []
    try:
        tr.sys = FakeSys
        deps.ensure = lambda pk, label: calls.append(label) or (pk is tr.cfg.PACKAGES)
        deps.missing = lambda pk: list(pk.values())
        deps.installing = lambda: False
        tr._gpu["tried"] = False
        first, second = tr._ready(), tr._ready()
    finally:
        tr.sys, deps.ensure, deps.missing, deps.installing = real
    h.check("the graphics-card libraries are tried once, then transcription goes ahead without them",
            first is False and second is True and sum("graphics" in c for c in calls) == 1, (first, second, calls))


h.run(steps())
