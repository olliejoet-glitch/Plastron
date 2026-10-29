"""Applies config/theme.py to Blender's theme."""

import bpy

from ..config import theme as cfg
from .util import resolve_path

# Theme sections that are editors (have generic .space colours).
_EDITORS = (
    "view_3d", "graph_editor", "file_browser", "nla_editor", "dopesheet_editor",
    "image_editor", "sequence_editor", "properties", "text_editor", "node_editor",
    "outliner", "info", "preferences", "console", "clip_editor", "topbar",
    "statusbar", "spreadsheet",
)


def _hex_to_rgba(text):
    text = text.lstrip("#")
    rgba = [int(text[i:i + 2], 16) / 255 for i in range(0, len(text), 2)]
    return rgba + [1.0] * (4 - len(rgba))


def _color(name_or_hex):
    value = cfg.PALETTE.get(name_or_hex, name_or_hex)
    if not value.startswith("#"):
        raise ValueError(f"Unknown palette colour {name_or_hex!r}")
    return _hex_to_rgba(value)


def _set(root, path, name_or_hex, problems):
    try:
        owner, attr = resolve_path(root, path)
        size = len(getattr(owner, attr))
        setattr(owner, attr, _color(name_or_hex)[:size])
    except (AttributeError, TypeError, ValueError) as ex:
        problems.append(f"{path}: {ex}")


def apply():
    """Apply the theme. Returns a list of problems (empty when all is well)."""
    theme = bpy.context.preferences.themes[0]
    problems = []
    for editor in _EDITORS:
        for path, colour in cfg.EVERY_EDITOR.items():
            owner, attr = resolve_path(getattr(theme, editor), path)
            if hasattr(owner, attr):          # not every editor has every colour
                _set(theme, f"{editor}.{path}", colour, problems)
    for path, colour in cfg.COLORS.items():
        _set(theme, path, colour, problems)
    ui = theme.user_interface
    for prop in ui.bl_rna.properties:
        if not prop.identifier.startswith("wcol_"):
            continue
        if not hasattr(getattr(ui, prop.identifier), "inner"):   # e.g. wcol_state
            continue
        values = {**cfg.WIDGET, **cfg.WIDGET_OVERRIDES.get(prop.identifier, {})}
        for attr, colour in values.items():
            _set(ui, f"{prop.identifier}.{attr}", colour, problems)
    for problem in problems:
        print("Plastron theme:", problem)
    return problems


def register():
    apply()


def unregister():
    try:
        bpy.ops.preferences.reset_default_theme()
    except RuntimeError:
        pass
