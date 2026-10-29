"""Test helpers that run inside Blender (with the real UI, under Xvfb).

A test file defines a generator of steps and calls run(steps). Each `yield`
hands control back to Blender so it can process simulated events and redraw;
yield a number to wait that many seconds.
"""

import importlib
import json
import os
import sys
import traceback

import bpy

# Blender imports the app template as bl_app_templates_user.plastron
plastron = importlib.import_module("bl_app_templates_user.plastron")


def module(name):
    """A Plastron module by dotted name, e.g. module("core.layout")."""
    return importlib.import_module(f"{plastron.__name__}.{name}")

_results = []
OUTPUT = os.environ.get("PLASTRON_TEST_OUTPUT", "")


def check(name, ok, detail=""):
    _results.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(f"CHECK {'PASS' if ok else 'FAIL'}: {name} {detail if not ok else ''}", flush=True)
    return ok


def close(a, b, tol=1e-3):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# --- UI lookups --------------------------------------------------------------

def window():
    return bpy.context.window_manager.windows[0]


def area(kind):
    return next((a for a in window().screen.areas if a.type == kind), None)


def region(area_, kind='WINDOW'):
    return next((r for r in area_.regions if r.type == kind), None)


def center(region_):
    return region_.x + region_.width // 2, region_.y + region_.height // 2


def override(kind, region_kind='WINDOW'):
    a = area(kind)
    return bpy.context.temp_override(window=window(), screen=window().screen, area=a,
                                     region=region(a, region_kind))


# --- Simulated input ---------------------------------------------------------

_mouse = [0, 0]
_MOD_KEYS = {"ctrl": 'LEFT_CTRL', "alt": 'LEFT_ALT', "shift": 'LEFT_SHIFT'}


def _event(type_, value, unicode=None, **mods):
    window().event_simulate(type_, value, unicode=unicode, x=_mouse[0], y=_mouse[1], **mods)


def move(x, y, **mods):
    _mouse[0], _mouse[1] = int(x), int(y)
    _event('MOUSEMOVE', 'NOTHING', **mods)


def hold_mods(mods, value):
    for name, on in mods.items():
        if on:
            _event(_MOD_KEYS[name], value)


def key(type_, unicode=None, **mods):
    """Tap a key, e.g. key('Z', ctrl=True)."""
    hold_mods(mods, 'PRESS')
    _event(type_, 'PRESS', unicode=unicode, **mods)
    _event(type_, 'RELEASE', **mods)
    hold_mods(mods, 'RELEASE')


def type_text(text):
    for ch in text:
        name = 'SPACE' if ch == " " else ch.upper()
        _event(name, 'PRESS', unicode=ch)
        _event(name, 'RELEASE')


def drag(start, end, button='LEFTMOUSE', steps=8, **mods):
    """Generator: press at start, move to end in steps, release."""
    hold_mods(mods, 'PRESS')
    move(*start, **mods)
    yield
    _event(button, 'PRESS', **mods)
    yield
    for i in range(1, steps + 1):
        t = i / steps
        move(start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t, **mods)
        yield
    _event(button, 'RELEASE', **mods)
    hold_mods(mods, 'RELEASE')
    yield


def redraw():
    """Force Blender to draw now (view matrices etc. update on draw)."""
    with bpy.context.temp_override(window=window()):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)


def screenshot(name):
    if not OUTPUT:
        return None
    import subprocess
    path = os.path.join(OUTPUT, name + ".png")
    # Grab the virtual display itself (Blender's own screenshot reads back black there).
    subprocess.run(["import", "-window", "root", path], check=False)
    return path


# --- Running -----------------------------------------------------------------

def _finish():
    path = os.environ.get("PLASTRON_TEST_RESULT")
    if path:
        with open(path, "w") as f:
            json.dump(_results, f, indent=1)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()


def run(steps, start_delay=1.5):
    """Run a generator of test steps, then write results and quit."""
    def tick():
        try:
            delay = next(steps)
        except StopIteration:
            _finish()
            return None
        except Exception:
            check("test raised no exception", False, traceback.format_exc())
            _finish()
            return None
        return 0.1 if delay is None else float(delay)
    bpy.app.timers.register(tick, first_interval=start_delay, persistent=True)
