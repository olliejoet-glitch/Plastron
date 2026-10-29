"""Modes: each is a workspace built from config/layout.py.

Switching mode only switches the workspace, so the project, timeline and
media stay exactly as they are.
"""

import bpy

from ..config import layout as cfg


def _items(_self, _context):
    return [(name, name, f"Switch to {name} mode") for name in cfg.MODES]


def _get(self):
    window = bpy.context.window
    names = list(cfg.MODES)
    if window and window.workspace.name in names:
        return names.index(window.workspace.name)
    return 0


def _set(self, value):
    switch_to(list(cfg.MODES)[value])


def switch_to(mode_name):
    workspace = bpy.data.workspaces.get(mode_name)
    window = bpy.context.window
    if workspace and window and window.workspace != workspace:
        window.workspace = workspace


def register():
    bpy.types.WindowManager.plastron_mode = bpy.props.EnumProperty(
        name="Mode", items=_items, get=_get, set=_set,
    )


def unregister():
    del bpy.types.WindowManager.plastron_mode
