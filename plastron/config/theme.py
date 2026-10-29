"""Plastron's colours: dark teal, with orange and blue highlights.

PALETTE holds the colours. Everything else refers to them by name, so
changing one palette entry recolours everything that uses it. To change one
spot only, give it a hex colour directly instead of a palette name.
Colours are "#rrggbb" or "#rrggbbaa".
"""

PALETTE = {
    "deepest":      "#071311",   # borders, gaps between areas
    "bg_dark":      "#09201c",   # timeline background
    "bg":           "#132c28",   # area backgrounds, input fields
    "bg_raised":    "#14302e",   # panels, headers
    "bg_light":     "#1b403c",   # sidebars, buttons
    "button":       "#1c413e",
    "button_hover": "#28524e",
    "paper":        "#d2cec6",   # default drawing surface (changeable in the Canvas panel)
    "text":         "#d6e2e0",
    "text_dim":     "#83a4a0",
    "orange":       "#de7520",   # selection, active
    "orange_soft":  "#d97f37",   # slider fill
    "blue":         "#4d73b1",   # playhead, secondary highlight
    "blue_dark":    "#364b7f",
    "white":        "#ffffff",
}

# Applied to every editor's generic colours (back, header, text...).
EVERY_EDITOR = {
    "space.back":           "bg",
    "space.header":         "bg_raised",
    "space.header_text":    "text",
    "space.header_text_hi": "white",
    "space.title":          "text",
    "space.text":           "text",
    "space.text_hi":        "white",
}

# Specific colours. Path = where in Blender's theme.
COLORS = {
    # Interface
    "user_interface.editor_border":          "deepest",
    "user_interface.editor_outline":         "deepest",
    "user_interface.editor_outline_active":  "text_dim",
    "user_interface.panel_header":           "bg_raised",
    "user_interface.panel_back":             "bg_light",
    "user_interface.panel_sub_back":         "bg_raised",
    "user_interface.panel_outline":          "deepest",
    "user_interface.panel_title":            "text",
    "user_interface.panel_text":             "text",
    "user_interface.panel_active":           "orange",
    "user_interface.widget_text_cursor":     "orange",
    "regions.sidebars.back":                 "bg_light",
    "regions.sidebars.tab_back":             "bg_raised",
    "regions.channels.back":                 "bg_raised",
    "regions.channels.text":                 "text",
    "regions.channels.text_selected":        "orange",
    "regions.scrubbing.back":                "bg_raised",
    "regions.scrubbing.text":                "text",
    "regions.scrubbing.time_marker":         "text_dim",
    "regions.scrubbing.time_marker_selected": "orange",
    "common.anim.playhead":                  "blue",
    "common.anim.preview_range":             "#de752040",

    # Canvas
    "view_3d.space.gradients.high_gradient": "paper",
    "view_3d.space.gradients.gradient":      "paper",
    "view_3d.camera":                        "text_dim",
    "view_3d.object_active":                 "orange",
    "view_3d.object_selected":               "orange_soft",
    "view_3d.gp_vertex_select":              "orange",

    # Timeline
    "sequence_editor.space.back":            "bg_dark",
    "sequence_editor.grid":                  "deepest",
    "sequence_editor.row_alternate":         "#ffffff06",
    "sequence_editor.active_strip":          "orange",
    "sequence_editor.selected_strip":        "orange_soft",
    "sequence_editor.image_strip":           "#5d7a76",
    "sequence_editor.scene_strip":           "#5d7a76",
    "sequence_editor.movie_strip":           "blue_dark",
    "sequence_editor.audio_strip":           "#2f6a8a",

    # Script panel
    "text_editor.space.back":                "bg",
    "text_editor.line_numbers":              "text_dim",
    "text_editor.line_numbers_background":   "bg_raised",
    "text_editor.selected_text":             "blue_dark",
    "text_editor.cursor":                    "orange",

    # Top bar
    "topbar.space.back":                     "deepest",
    "topbar.space.header":                   "deepest",
    "statusbar.space.header":                "deepest",
}

# Canvas overlay drawn by Plastron (not part of Blender's theme).
CANVAS = {
    "outside_frame": "#0d191766",   # dims the canvas outside the camera frame
    "frame_line":    "#00000055",
}

# Canvas colour swatches in the Canvas panel (tools area). Any colour can also
# be picked there; the choice is remembered between sessions.
CANVAS_PRESETS = [
    # name          colour
    ("White",       "#ffffff"),
    ("Soft",        "#d2cec6"),
    ("Grey",        "#9a9893"),
    ("Dark",        "#4a4d4b"),
]

# Widget colours: every button type gets these, then WIDGET_OVERRIDES on top.
WIDGET = {
    "outline":   "deepest",
    "inner":     "button",
    "inner_sel": "orange",
    "item":      "text_dim",
    "text":      "text",
    "text_sel":  "white",
}

WIDGET_OVERRIDES = {
    "wcol_text":        {"inner": "bg"},                         # text fields
    "wcol_num":         {"inner": "bg"},                         # number fields
    "wcol_numslider":   {"inner": "bg", "item": "orange_soft"},  # sliders: orange fill
    "wcol_option":      {"inner": "bg", "item": "white"},        # checkboxes
    "wcol_toggle":      {"inner": "button"},
    "wcol_tool":        {"inner": "button", "inner_sel": "orange"},
    "wcol_toolbar_item": {"inner": "bg_light", "inner_sel": "orange"},
    "wcol_radio":       {"inner": "button", "inner_sel": "blue"},
    "wcol_tab":         {"inner": "bg_raised", "inner_sel": "bg_light"},
    "wcol_menu_back":   {"inner": "bg_raised"},
    "wcol_menu_item":   {"inner": "#00000000", "inner_sel": "orange"},
    "wcol_pulldown":    {"inner": "#00000000", "inner_sel": "button_hover"},
    "wcol_tooltip":     {"inner": "deepest"},
    "wcol_list_item":   {"inner": "#00000000", "inner_sel": "blue_dark"},
    "wcol_box":         {"inner": "bg_raised"},
    "wcol_scroll":      {"inner": "bg_dark", "item": "text_dim"},
    "wcol_progress":    {"item": "orange"},
}
