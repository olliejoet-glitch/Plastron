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
            {"size": 0.12, "area": "tools"},      # Ollie: tools on the left,
            {"size": 0.70, "area": "canvas"},
            {"size": 0.18, "rows": [               # on the right: script, 3D scene, its keyframes
                {"size": 0.40, "area": "script"},
                {"size": 0.38, "area": "scene3d"},
                {"size": 0.22, "area": "keys"},
            ]},
        ]},
        {"size": 0.30, "area": "timeline"},
    ]},
    # Cutting the real video on the same timeline: media (your files, drag
    # them onto the timeline) | the video preview; the timeline below.
    "Edit": {"rows": [
        {"size": 0.58, "columns": [
            {"size": 0.24, "area": "media"},
            {"size": 0.76, "area": "preview"},
        ]},
        {"size": 0.42, "area": "timeline"},
    ]},
    # Colour grading: the picture big (Grade panel at its side), the scopes
    # beside it, the timeline below.
    "Grade": {"rows": [
        {"size": 0.64, "columns": [
            {"size": 0.74, "area": "preview"},
            {"size": 0.26, "rows": [
                {"size": 0.5, "area": "scope_waveform"},
                {"size": 0.5, "area": "scope_vector"},
            ]},
        ]},
        {"size": 0.36, "area": "timeline"},
    ]},
    # Sound design on the same timeline: the picture small on top, a big
    # timeline with the Sound panel (mix, loudness, ducking, beats) at its side.
    "Audio": {"rows": [
        {"size": 0.34, "area": "preview_plain"},
        {"size": 0.66, "area": "timeline_sound"},
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
        "header": True, "footer": False, "sidebar": False,     # header: the script bar
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
    # The 3D scene (features/scene3d, config/scene3d.py): Blender's own 3D
    # view with its header menus; no toolbar (Ollie): selecting something
    # shows move + rotate gizmos.
    "scene3d": {
        "editor": 'VIEW_3D',
        "header": True, "tool_header": False, "toolbar": False, "sidebar": False, "hud": False,
        "scene_view": True,
        "settings": {
            "use_local_camera": True,
            "show_gizmo_object_translate": True,     # select something: move + rotate gizmos
            "show_gizmo_object_rotate": True,
            "shading.type": 'MATERIAL',
            "shading.use_scene_world": True,
            "overlay.show_floor": False,
            "overlay.show_axis_x": True,
            "overlay.show_axis_y": True,
            "show_gizmo_navigate": True,
            "clip_end": 1000.0,
        },
    },
    # The 3D scene's keyframes (Ollie: "an editable keyframe view so I know
    # what transforms I've done"): Blender's Dope Sheet. The camera and each
    # card ("Card: <track>"); select / drag / delete keys there.
    "keys": {
        "editor": 'DOPESHEET_EDITOR',
        "header": True, "sidebar": False,
        "settings": {
            "ui_mode": 'DOPESHEET',
            "dopesheet.show_only_selected": False,
            "show_region_channels": True,
        },
    },
    # Edit mode: Blender's file browser as the media bin (thumbnails; drag a
    # file onto the timeline). Plastron puts dropped clips on the right tracks.
    "media": {
        "editor": 'FILE_BROWSER',
        "header": True, "toolbar": True, "sidebar": False,     # toolbar: drives / bookmarks
        "media_browser": True,
    },
    # Edit mode: the video as it plays (the timeline's picture).
    "preview": {
        "editor": 'SEQUENCE_EDITOR',
        "header": True, "footer": False, "toolbar": False, "sidebar": True, "hud": False,   # sidebar: Clip panel
        "settings": {
            "view_type": 'PREVIEW',
            "show_overlays": True,
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
            "timeline_overlay.thumbnail_display_style": 'CONTINUOUS',  # pictures along every clip (rows ~40 px+)
            "timeline_overlay.show_strip_tag_color": True,             # clip colours (Colour button in the header)
            "timeline_overlay.waveform_display_type": 'ALL_WAVEFORMS',  # voice clips show their sound
        },
    },
}

# Audio mode's timeline: the same, with its sidebar (the Sound panel) showing;
# its picture without a sidebar (Blender's own Metadata tab can't be hidden).
AREAS["timeline_sound"] = dict(AREAS["timeline"], sidebar=True)
AREAS["preview_plain"] = dict(AREAS["preview"], sidebar=False)
# Grade mode's scopes: the picture's brightness (waveform) and colours (vectorscope).
AREAS["scope_waveform"] = dict(AREAS["preview_plain"], header=False,
                               settings=dict(AREAS["preview"]["settings"], display_mode='WAVEFORM'))
AREAS["scope_vector"] = dict(AREAS["preview_plain"], header=False,
                             settings=dict(AREAS["preview"]["settings"], display_mode='VECTOR_SCOPE'))

# Whole-window options.
WINDOW = {
    "status_bar": False,
}
