"""Every Plastron shortcut, in one table.

To change a shortcut, edit its key. To remove one, delete its line.
Blender's own shortcuts are switched off except for the essentials listed in
BLENDER_KEEP at the bottom.

Key format: modifiers joined with "+", then the key, e.g. "Ctrl+Shift+Z".
  Modifiers: Ctrl, Alt, Shift, Cmd
  Keys:      A-Z, 0-9, F1-F12, Space, Esc, Enter, Tab, Delete, Backspace,
             "=", "-", "[", "]", Left, Right, Up, Down, Home, End
  Mouse:     LMB, MMB, RMB, WheelUp, WheelDown
             (a mouse button entry starts a drag: it runs until release)

Lines whose action isn't built yet are skipped quietly, so later-stage
shortcuts can be listed here already.
"""

# Where a shortcut works -> Blender keymap it lives in.
# (keymap name, space type, region type)
WHERE = {
    "everywhere": ("Window", 'EMPTY', 'WINDOW'),
    "edit":       ("Screen", 'EMPTY', 'WINDOW'),          # undo / redo
    "playback":   ("Frames", 'EMPTY', 'WINDOW'),          # over canvas and timeline
    "canvas":     ("3D View", 'VIEW_3D', 'WINDOW'),
    "timeline":   ("Sequencer", 'SEQUENCE_EDITOR', 'WINDOW'),
    "timeline_view": ("View2D", 'EMPTY', 'WINDOW'),       # timeline pan / zoom
}

SHORTCUTS = [
    # where          key                 action                          description               settings

    # --- File -------------------------------------------------------------
    ("everywhere",   "Ctrl+N",           "plastron.file_new",            "New project"),
    ("everywhere",   "Ctrl+O",           "wm.open_mainfile",             "Open project"),
    ("everywhere",   "Ctrl+S",           "wm.save_mainfile",             "Save"),
    ("everywhere",   "Ctrl+Shift+S",     "wm.save_as_mainfile",          "Save as"),
    ("everywhere",   "Ctrl+Q",           "wm.quit_blender",              "Quit"),

    # --- Undo -------------------------------------------------------------
    ("edit",         "Ctrl+Z",           "ed.undo",                      "Undo"),
    ("edit",         "Ctrl+Shift+Z",     "ed.redo",                      "Redo"),

    # --- Playback ---------------------------------------------------------
    ("playback",     "Space",            "screen.animation_play",        "Play / pause"),

    # --- Canvas: tools (Photoshop keys) -----------------------------------
    ("canvas",       "B",                "plastron.canvas_tool",         "Pencil",                 {"tool": 'PENCIL'}),
    ("canvas",       "E",                "plastron.canvas_tool",         "Eraser",                 {"tool": 'ERASER'}),
    ("canvas",       "G",                "plastron.canvas_tool",         "Fill",                   {"tool": 'FILL'}),
    ("canvas",       "L",                "plastron.canvas_tool",         "Lasso select",           {"tool": 'LASSO'}),
    ("canvas",       "M",                "plastron.canvas_tool",         "Rectangle select",       {"tool": 'RECT'}),
    ("canvas",       "V",                "plastron.canvas_tool",         "Move",                   {"tool": 'MOVE'}),
    ("canvas",       "Q",                "brush.scale_size",             "Smaller brush",          {"scalar": 0.8}),
    ("canvas",       "W",                "brush.scale_size",             "Bigger brush",           {"scalar": 1.25}),

    # --- Canvas: view -----------------------------------------------------
    ("canvas",       "Alt+Shift+LMB",    "view3d.move",                  "Pan (drag)"),
    ("canvas",       "MMB",              "view3d.move",                  "Pan (drag)"),
    ("canvas",       "Ctrl+Alt+LMB",     "view3d.zoom",                  "Zoom (drag)"),
    ("canvas",       "WheelUp",          "plastron.canvas_zoom",         "Zoom in",                {"step": 1}),
    ("canvas",       "WheelDown",        "plastron.canvas_zoom",         "Zoom out",               {"step": -1}),
    ("canvas",       "Ctrl+=",           "plastron.canvas_zoom",         "Zoom in",                {"step": 1}),
    ("canvas",       "Ctrl+-",           "plastron.canvas_zoom",         "Zoom out",               {"step": -1}),
    ("canvas",       "Ctrl+0",           "plastron.canvas_fit",          "Fit to screen"),
    ("canvas",       "Ctrl+1",           "plastron.canvas_zoom_actual",  "100 % zoom"),
    ("canvas",       "R",                "plastron.canvas_rotate",       "Rotate view (hold + drag)"),
    ("canvas",       "Ctrl+F",           "plastron.canvas_flip_view",    "Flip view (drawing unchanged)"),

    # --- Canvas: later stages ----------------------------------------------
    ("canvas",       "Ctrl+T",           "plastron.transform",           "Transform"),
    ("canvas",       "Ctrl+C",           "plastron.strokes_copy",        "Copy strokes"),
    ("canvas",       "Ctrl+V",           "plastron.strokes_paste",       "Paste strokes in place"),
    ("canvas",       "Ctrl+Alt+F",       "plastron.strokes_flip",        "Flip strokes / layers"),
    ("canvas",       "Alt+LMB",          "plastron.eyedropper",          "Eyedropper"),

    # --- Timeline: view ---------------------------------------------------
    ("timeline_view", "Alt+Shift+LMB",   "view2d.pan",                   "Pan (drag)"),
    ("timeline_view", "Ctrl+Alt+LMB",    "view2d.zoom",                  "Zoom (drag)"),
    ("timeline_view", "Ctrl+=",          "view2d.zoom_in",               "Zoom in"),
    ("timeline_view", "Ctrl+-",          "view2d.zoom_out",              "Zoom out"),
    ("timeline",     "Ctrl+0",           "sequencer.view_all",           "Fit to screen"),

    # --- Timeline: editing (stage 2) ---------------------------------------
    ("timeline",     "N",                "plastron.panel_new",           "New panel at playhead"),
    ("timeline",     "Ctrl+K",           "plastron.clip_split",          "Split at playhead"),
    ("timeline",     "Delete",           "plastron.clip_delete",         "Delete clip"),
    ("timeline",     "Backspace",        "plastron.clip_delete",         "Delete clip"),
    ("timeline",     "I",                "plastron.loop_in",             "Loop range start"),
    ("timeline",     "O",                "plastron.loop_out",            "Loop range end"),
]


# Blender shortcuts that stay switched on. Everything else is turned off.
# keymap name -> list of action patterns to keep ("*" = all of them).
# Pop-up/modal keymaps (e.g. inside a drag or a text field) are always kept.
BLENDER_KEEP = {
    "Screen Editing":        ["*"],                       # resize areas
    "Screen":                ["screen.animation_step", "screen.region_blend"],  # playback timer
    "User Interface":        ["ui.*"],                    # buttons, lists, eyedroppers in fields
    "View2D Buttons List":   ["*"],                       # scrolling panels
    "View2D":                ["view2d.scroll*", "view2d.zoom_in", "view2d.zoom_out",
                              "view2d.scroller_activate", "view2d.pan", "view2d.ndof"],
    "Time Scrub":            ["*"],                       # click/drag the ruler to scrub
    "Text":                  ["*"],                       # typing in the script panel
    "Text Generic":          ["text.start_find", "text.replace"],
    "Grease Pencil Brush Stroke": ["grease_pencil.brush_stroke"],  # drawing itself
    "Grease Pencil Fill Tool": ["*"],
    "Sequencer":             ["sequencer.select", "sequencer.select_box",
                              "sequencer.select_handle", "transform.seq_slide"],
    # Tool keymaps (what a tool does on click/drag) keep everything.
    "3D View Tool: *":       ["*"],
    "Sequencer Tool: *":     ["*"],
    "Generic Gizmo*":        ["*"],
}
