"""Runs every Plastron test in Blender (real UI under a virtual display).

    python tests/run_tests.py            all tests
    python tests/run_tests.py keymap     only tests whose file name contains "keymap"

Tests run in parallel: PLASTRON_TEST_JOBS workers (default: 3, at most one
per two processor cores + 1), each with its own Blender copy, config,
temp folder and virtual display; the slowest tests (times kept in
.cache/test_times.json) start first. PLASTRON_TEST_JOBS=1: one at a time.

Each tests/test_*.py file runs in a fresh Blender started exactly as Plastron
starts for Ollie (portable install, app template). Any Python error printed
to the console also fails the test.
"""

import glob
import json
import os
import queue
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import blender_env  # noqa: E402

# Console lines that are harmless in the virtual display.
BENIGN = [
    r"XDG_RUNTIME_DIR", r"ALSA", r"GHOST", r"libwayland", r"Saved session recovery",
    r"Unable to open a display", r"Color management", r"OpenColorIO",
]
ERROR = re.compile(r"Traceback|Error:|Exception|Segmentation fault|Plastron theme:|couldn't hide")


def console_errors(output):
    lines = []
    for line in output.splitlines():
        if ERROR.search(line) and not any(re.search(b, line) for b in BENIGN):
            lines.append(line)
    return lines


def run_file(path, worker=0):
    name = os.path.splitext(os.path.basename(path))[0]
    result = os.path.join(blender_env.OUTPUT, name + ".json")
    if os.path.exists(result):
        os.remove(result)
    code, out = blender_env.run(
        ["--app-template", "plastron", "--enable-event-simulate"] + (["--debug-handlers"] if os.environ.get("PLASTRON_DEBUG_HANDLERS") else []) + [
         "--python-exit-code", "1", "--python", path],
        env={"PLASTRON_TEST_RESULT": result, "PLASTRON_TEST_OUTPUT": blender_env.OUTPUT,
             # no installs, no microphone, no speech model in tests: stand-ins
             "PLASTRON_NO_INSTALL": "1", "PLASTRON_FAKE_MIC": "1", "PLASTRON_FAKE_TRANSCRIBE": "1"},
        timeout=int(os.environ.get("PLASTRON_TEST_TIMEOUT", 300)),   # (test_layers needs > 180 s here)
        worker=worker)
    with open(os.path.join(blender_env.OUTPUT, name + ".log"), "w") as f:
        f.write(out)
    checks = json.load(open(result)) if os.path.exists(result) else []
    if not checks:
        checks.append({"name": "test produced results", "ok": False, "detail": out[-2000:]})
    errors = console_errors(out)
    checks.append({"name": "no errors in console", "ok": not errors,
                   "detail": "\n".join(errors[:20])})
    return name, checks


TIMES = os.path.join(blender_env.CACHE, "test_times.json")


def _load_times():
    try:
        with open(TIMES) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def jobs(n_files):
    want = os.environ.get("PLASTRON_TEST_JOBS")
    n = int(want) if want else max(1, min(3, (os.cpu_count() or 2) // 2 + 1))
    return max(1, min(n, n_files))


def report(name, checks):
    bad = [c for c in checks if not c["ok"]]
    print(f"{'FAIL' if bad else 'ok  '}  {name}: {len(checks) - len(bad)}/{len(checks)} checks passed", flush=True)
    for c in bad:
        print(f"      x {c['name']}\n        {c['detail'].strip()[:1500]}", flush=True)
    return len(bad)


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    files = sorted(f for f in glob.glob(os.path.join(HERE, "test_*.py")) if pattern in f)
    times = _load_times()
    name_of = lambda f: os.path.splitext(os.path.basename(f))[0]  # noqa: E731
    files.sort(key=lambda f: -times.get(name_of(f), 60.0))       # (longest first: the pool ends together)
    todo = queue.Queue()
    for f in files:
        todo.put(f)
    lock = threading.Lock()
    failed = [0]
    started = time.monotonic()

    def worker(i):
        while True:
            try:
                path = todo.get_nowait()
            except queue.Empty:
                return
            t0 = time.monotonic()
            name, checks = run_file(path, worker=i)
            with lock:
                times[name] = round(time.monotonic() - t0, 1)
                failed[0] += report(name, checks)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(jobs(len(files)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    try:
        with open(TIMES, "w") as f:
            json.dump(times, f, indent=1, sort_keys=True)
    except OSError:
        pass
    took = int(time.monotonic() - started)
    print(f"\n({len(files)} test files, {len(threads)} at a time, {took // 60}:{took % 60:02d})")
    print("\nAll tests passed." if not failed[0] else f"\n{failed[0]} check(s) failed.")
    sys.exit(1 if failed[0] else 0)


if __name__ == "__main__":
    main()
