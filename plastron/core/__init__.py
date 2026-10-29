"""Shared systems. No feature logic lives here.

keymaps registers separately (last), from plastron/__init__.py, once every
feature's operators exist.
"""

from . import (handlers, preferences, theme, user_settings, project, modes, hidden_ui,  # noqa: F401
               autosave, presets, keymaps)

_MODULES = (handlers, preferences, theme, user_settings, project, modes, hidden_ui, autosave, presets)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
