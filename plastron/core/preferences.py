"""Applies config/preferences.py at startup; restores Blender's values on exit."""

import bpy

from ..config.preferences import PREFERENCES
from .util import get_path, set_path

_original = {}


def register():
    prefs = bpy.context.preferences
    for path, value in PREFERENCES.items():
        _original[path] = get_path(prefs, path)
        set_path(prefs, path, value)


def unregister():
    prefs = bpy.context.preferences
    for path, value in _original.items():
        set_path(prefs, path, value)
    _original.clear()
