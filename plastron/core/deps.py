"""Extra Python packages (shared): installed once, in the background, into a
folder in Blender's config folder (kept across Plastron updates), which is
put on Python's path at start.

Features list what they need (e.g. config/voice.py PACKAGES) and call
ensure(); status() says what's happening, for the UI.
"""

import importlib.util
import os
import subprocess
import sys

import bpy

_state = {"proc": None, "status": "", "failed": False, "log": None}


def folder():
    version = f"py{sys.version_info.major}{sys.version_info.minor}"
    return os.path.join(bpy.utils.user_resource('CONFIG'), "plastron_python", version)


def add_to_path():
    path = folder()
    os.makedirs(path, exist_ok=True)
    if path not in sys.path:
        sys.path.append(path)
    importlib.invalidate_caches()


def available(module):
    return importlib.util.find_spec(module) is not None


def missing(packages):
    """packages: {module name: pip name} -> pip names not installed."""
    return [pip for module, pip in packages.items() if not available(module)]


def installing():
    return _state["proc"] is not None


def status():
    return _state["status"]


def python():
    """Blender's bundled Python executable (never Blender itself), or None."""
    exe = sys.executable
    if exe and "python" in os.path.basename(exe).lower() and os.path.exists(exe):
        return exe
    import glob
    here = os.path.dirname(bpy.app.binary_path)
    version = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
    for pattern in ("python.exe", "python3.*[0-9]", "python3"):
        found = sorted(glob.glob(os.path.join(here, version, "python", "bin", pattern)))
        if found:
            return found[0]
    return None


def ensure(packages, label):
    """Start installing whatever's missing (in the background). Returns True
    if everything is already there."""
    need = missing(packages)
    if not need:
        return True
    if installing() or os.environ.get("PLASTRON_NO_INSTALL"):
        return False
    py = python()
    if py is None:
        _state.update(status=f"Can't install {label}: Blender's Python not found", failed=True)
        return False
    log_path = os.path.join(folder(), "install.log")
    log = open(log_path, "w", encoding="utf-8")
    flags = 0x08000000 if sys.platform == "win32" else 0      # no console window
    _state["proc"] = subprocess.Popen(
        [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
         "--target", folder(), *need],
        stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    _state.update(status=f"Setting up {label} (one time, needs internet)...", failed=False, log=log)
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=1.0, persistent=True)
    return False


def _poll():
    proc = _state["proc"]
    if proc is None:
        return None
    if proc.poll() is None:
        return 1.0
    _state["log"].close()
    _state["proc"] = None
    importlib.invalidate_caches()
    if proc.returncode == 0:
        _state.update(status="", failed=False)
    else:
        _state.update(status="Setup failed (no internet?). Plastron will try again next start.",
                      failed=True)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def register():
    add_to_path()


def unregister():
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)
