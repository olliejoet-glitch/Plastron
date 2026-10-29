# SPDX-License-Identifier: GPL-3.0-or-later
"""Plastron: an audiovisual video editor built as a Blender app template.

Registration order: core systems, app UI, timeline, features, then the
keymap last (so every feature's actions exist when shortcuts are bound).
"""

import bpy

from . import core, ui, timeline, features
from .core import handlers, keymaps

_PARTS = (core, ui, timeline, features)


def _first_file():
    # load_post doesn't fire for the file already open while we register.
    handlers.run_on_load()
    return None


def register():
    for part in _PARTS:
        part.register()
    keymaps.register()
    bpy.app.timers.register(_first_file, first_interval=0.05)


def unregister():
    keymaps.unregister()
    for part in reversed(_PARTS):
        part.unregister()
