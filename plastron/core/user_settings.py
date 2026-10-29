"""Settings Ollie changes inside Plastron that must be remembered (e.g. the
canvas colour). Blender's own preferences aren't saved (see
config/preferences.py), so these live in a small JSON file in the portable
Blender's config folder, which updates keep.

Saving is debounced, so dragging a colour picker doesn't write on every step.
"""

import json
import os

import bpy

FILE_NAME = "plastron_settings.json"
_values = None


def path():
    return os.path.join(bpy.utils.user_resource('CONFIG'), FILE_NAME)


def _load():
    global _values
    if _values is None:
        try:
            with open(path(), encoding="utf-8") as f:
                _values = json.load(f)
        except (OSError, ValueError):
            _values = {}
    return _values


def get(key, default=None):
    return _load().get(key, default)


def set(key, value):
    _load()[key] = value
    if not bpy.app.timers.is_registered(save):
        bpy.app.timers.register(save, first_interval=0.5, persistent=True)


def save():
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    with open(path(), "w", encoding="utf-8") as f:
        json.dump(_load(), f, indent=1)
    return None


def reload():
    """Forget the in-memory copy (tests)."""
    global _values
    _values = None


def register():
    pass


def unregister():
    if bpy.app.timers.is_registered(save):
        bpy.app.timers.unregister(save)
        save()
