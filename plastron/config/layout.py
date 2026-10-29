"""Screen layout of each mode.

A mode is a layout of the one app: switching modes keeps the same project,
timeline and media. Sizes are fractions of the space being divided.

After changing anything here, the startup file must be rebuilt:
    python tools/build_startup.py
(the tests fail with a clear message if it's out of date).
"""

# Each mode: a tree of "rows" (top to bottom) and "columns" (left to right).
# A leaf names an area from AREAS below.
MODES = {
    "Storyboard": {"rows": [
        {"size": 0.70, "columns": [
            {"size": 0.18, "area": "script"},
            {"size": 0.70, "area": "canvas"},
            {"size": 0.12, "area": "tools"},
        ]},
        {"size": 0.30, "area": "timeline"},
    ]},
}

# The mode Plastron opens in.
DEFAULT_MODE = "Storyboard"

# What each area is and which of its parts are visible.
#   header       the bar along the top of the area
#   tool_header  canvas only: Plastron's options bar (like Photoshop's)
#   toolbar      Blender's own tool column (Plastron uses its tool strip instead)
#   sidebar      Blender's right-hand panel
#   hud          Blender's "adjust last operation" pop-up panel
#   channels     timeline only: the track headers column
#   channels_width  timeline only: its width in pixels (at 100 % UI scale)
#   settings     any other editor setting, as "property path": value
# The "tools" area is a panel holder that shows only Plastron's panels
# (tool strip + layers); see plastron/features/storyboard/tools.py.
AREAS = {
    "script": {
        "editor": 'TEXT_EDITOR',
        "header": False, "footer": False, "sidebar": False,
        "settings": {
            "show_line_numbers": True,
            "show_word_wrap": True,
            "show_syntax_highlight": False,
            "font_size": 14,
        },
    },
    "canvas": {
        "editor": 'VIEW_3D',
        "header": False, "tool_header": True, "toolbar": False, "sidebar": False, "hud": False,
        "settings": {
            "show_gizmo_navigate": False,
            "overlay.show_floor": False,
            "overlay.show_axis_x": False,
            "overlay.show_axis_y": False,
            "overlay.show_axis_z": False,
            "overlay.show_cursor": False,
            "overlay.show_object_origins": False,
            "overlay.show_text": False,
            "overlay.show_stats": False,
            "overlay.show_extras": False,     # Plastron draws the camera frame itself
            # Material Preview shows the panels' layer stacks; the paper
            # colour is the project's world colour (Canvas panel).
            "shading.type": 'MATERIAL',
            "shading.use_scene_world": True,
            "shading.use_scene_lights": True,
        },
    },
    "tools": {
        "editor": 'PROPERTIES',
        "header": False,
        "settings": {"context": 'TOOL'},
    },
    "timeline": {
        "editor": 'SEQUENCE_EDITOR',
        "header": True, "footer": False, "toolbar": False, "sidebar": False, "hud": False,
        "channels": True,
        "channels_width": 260,
        "settings": {
            "view_type": 'SEQUENCER',
            "show_markers": True,
            "timeline_overlay.show_strip_source": False,   # no file paths on clips
            "timeline_overlay.show_strip_duration": False,
        },
    },
}

# Whole-window options.
WINDOW = {
    "status_bar": False,
}
