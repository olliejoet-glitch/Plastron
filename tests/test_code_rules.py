"""Rules the code keeps (checked by reading it):
- clips are removed only through timeline/ripple.remove (Blender's Delete,
  which stops the frames-ahead thread first: Python's strips.remove crashed
  Blender while that thread was rendering the clip, e.g. a big dropped video)."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as h  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plastron")


def steps():
    yield 0.5
    found = []
    for folder, _dirs, files in os.walk(ROOT):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if re.search(r"strips\.remove\(", line):
                        found.append(f"{os.path.relpath(path, ROOT)}:{n}")
    allowed = {"timeline/ripple.py"}
    bad = [w for w in found if w.split(":")[0].replace(os.sep, "/") not in allowed]
    h.check("clips are only removed through ripple.remove", not bad, bad)


h.run(steps())
