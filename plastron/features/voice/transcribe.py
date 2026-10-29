"""Transcription jobs: one per take, run once after recording, in a separate
process (transcribe_worker.py) so Blender never waits. A timer checks on the
running job (only while there is one).
"""

import json
import os
import subprocess
import sys

import bpy

from ...config import voice as cfg
from ...core import deps
from . import takes

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcribe_worker.py")

_queue = []                    # [(take uid, wav path)]
_job = {"proc": None, "uid": None, "wav": None, "out": None}
_listeners = []                # func() after a transcript arrives
_last_error = [""]


def listen(func):
    _listeners.append(func)


def fake():
    return bool(os.environ.get("PLASTRON_FAKE_TRANSCRIBE"))


def queue(take, wav_path):
    take.status = 'WAITING'
    _queue.append((take.uid, wav_path))
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.1, persistent=True)


def busy():
    return bool(_queue) or _job["proc"] is not None


def status():
    if _job["proc"] is not None:
        return "Transcribing..."
    if _queue:
        return deps.status() or "Transcription waiting..."
    return _last_error[0]


def queue_again(take):
    """Transcribe a take again (e.g. after a failure): its packed sound is
    written out to a file for the worker."""
    if take.sound is None:
        return False
    path = os.path.join(bpy.app.tempdir, "plastron_recordings", take.uid + "_again.wav")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if take.sound.packed_file is not None:
        with open(path, "wb") as f:
            f.write(take.sound.packed_file.data)
    else:
        path = bpy.path.abspath(take.sound.filepath)
    queue(take, path)
    return True


def _set(uid, **values):
    """Set values on every copy of the take (split clips share takes)."""
    for scene in bpy.data.scenes:
        if not hasattr(scene, "plastron_timeline") or scene.sequence_editor is None:
            continue
        for _strip, take in takes.all_takes(scene):
            if take.uid == uid:
                for key, value in values.items():
                    if key == "words":
                        takes.set_words(take, value)
                    else:
                        setattr(take, key, value)


def _start(uid, wav):
    out = wav + ".json"
    env = dict(os.environ)
    env["PYTHONPATH"] = deps.folder()
    env.setdefault("HF_HOME", os.path.join(bpy.utils.user_resource('CONFIG'), "plastron_models"))
    args = [deps._python() or sys.executable, WORKER, wav, out, cfg.TRANSCRIBE_MODEL,
            cfg.TRANSCRIBE_PROMPT]
    if fake():
        args.append("--fake")
    flags = 0x08000000 if sys.platform == "win32" else 0      # no console window
    _job.update(proc=subprocess.Popen(args, env=env, creationflags=flags,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                uid=uid, wav=wav, out=out)
    _set(uid, status='RUNNING')


def _finish():
    uid, out = _job["uid"], _job["out"]
    _job.update(proc=None, uid=None, wav=None, out=None)
    try:
        with open(out, encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError) as err:
        result = {"error": f"no result ({err})"}
    if "words" in result:
        _set(uid, words=result["words"], status='DONE', error="")
        _last_error[0] = ""
    else:
        _set(uid, status='FAILED', error=result.get("error", "unknown error"))
        _last_error[0] = "Transcription failed (select the clip, then Transcribe Again)"
        print("Plastron: transcription failed:", result.get("error"))
    for func in _listeners:
        func()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'SEQUENCE_EDITOR', 'TEXT_EDITOR'}:
                area.tag_redraw()


def _tick():
    proc = _job["proc"]
    if proc is not None:
        if proc.poll() is None:
            return 0.5
        _finish()
    if not _queue:
        return None
    if not fake() and not deps.ensure(cfg.PACKAGES, "transcription"):
        return 2.0                       # waiting for the one-time install
    uid, wav = _queue.pop(0)
    _start(uid, wav)
    return 0.5


def wait_all(timeout=60.0):
    """Tests: run the queue to the end now."""
    import time
    end = time.monotonic() + timeout
    while busy() and time.monotonic() < end:
        delay = _tick()
        if delay is None and not busy():
            break
        time.sleep(0.1)


def register():
    pass


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
