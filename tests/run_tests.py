"""Runs every Plastron test in Blender (real UI under a virtual display).

    python tests/run_tests.py            all tests
    python tests/run_tests.py keymap     only tests whose file name contains "keymap"

Each tests/test_*.py file runs in a fresh Blender started exactly as Plastron
starts for Ollie (portable install, app template). Any Python error printed
to the console also fails the test.
"""

import glob
import json
import os
import re
import sys

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


def run_file(path):
    name = os.path.splitext(os.path.basename(path))[0]
    result = os.path.join(blender_env.OUTPUT, name + ".json")
    if os.path.exists(result):
        os.remove(result)
    code, out = blender_env.run(
        ["--app-template", "plastron", "--enable-event-simulate",
         "--python-exit-code", "1", "--python", path],
        env={"PLASTRON_TEST_RESULT": result, "PLASTRON_TEST_OUTPUT": blender_env.OUTPUT,
             # no installs, no microphone, no speech model in tests: stand-ins
             "PLASTRON_NO_INSTALL": "1", "PLASTRON_FAKE_MIC": "1", "PLASTRON_FAKE_TRANSCRIBE": "1"},
        timeout=180)
    with open(os.path.join(blender_env.OUTPUT, name + ".log"), "w") as f:
        f.write(out)
    checks = json.load(open(result)) if os.path.exists(result) else []
    if not checks:
        checks.append({"name": "test produced results", "ok": False, "detail": out[-2000:]})
    errors = console_errors(out)
    checks.append({"name": "no errors in console", "ok": not errors,
                   "detail": "\n".join(errors[:20])})
    return name, checks


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    files = sorted(f for f in glob.glob(os.path.join(HERE, "test_*.py")) if pattern in f)
    failed = 0
    for path in files:
        name, checks = run_file(path)
        bad = [c for c in checks if not c["ok"]]
        failed += len(bad)
        print(f"{'FAIL' if bad else 'ok  '}  {name}: {len(checks) - len(bad)}/{len(checks)} checks passed")
        for c in bad:
            print(f"      x {c['name']}\n        {c['detail'].strip()[:1500]}")
    print("\nAll tests passed." if not failed else f"\n{failed} check(s) failed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
