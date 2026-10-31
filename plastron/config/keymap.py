"""Every Plastron shortcut, in one table.

To change a shortcut, edit its key. To remove one, delete its line.
Blender's own shortcuts are switched off except for the essentials listed in
BLENDER_KEEP at the bottom.

Key format: modifiers joined with "+", then the key, e.g. "Ctrl+Shift+Z".
  Modifiers: Ctrl, Alt, Shift, Cmd
  Keys:      A-Z, 0-9, F1-F12, Space, Esc, Enter, Tab, Delete, Backspace,
             "=", "-", "[", "]", Left, Right, Up, Down, Home, End
  Mouse:     LMB, MMB, RMB, WheelUp, WheelDown, MouseMove (hover)
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
    "track_headers": ("Sequencer Channels", 'SEQUENCE_EDITOR', 'WINDOW'),
    "script":     ("Text", 'TEXT_EDITOR', 'WINDOW'),
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
    ("canvas",       "Shift+B",          "plastron.canvas_tool",         "Blur",                   {"tool": 'BLUR'}),
    ("canvas",       "Shift+S",          "plastron.canvas_tool",         "Smudge",                 {"tool": 'SMUDGE'}),
    ("canvas",       "RMB",              "wm.call_asset_shelf_popover",  "Brush palette",          {"name": "VIEW3D_AST_brush_texture_paint"}),
    ("canvas",       "Alt+LMB",          "paint.sample_color",           "Pick colour (what you see)", {"merged": True}),
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
    # --- Canvas: selecting and transforming pixels --------------------------
    ("canvas",       "L",                "plastron.select_tool",         "Lasso select",           {"shape": 'LASSO'}),
    ("canvas",       "M",                "plastron.select_tool",         "Rectangle select",       {"shape": 'RECT'}),
    ("canvas",       "V",                "plastron.move_tool",           "Move"),
    ("canvas",       "Ctrl+T",           "plastron.transform",           "Transform (scale, rotate, distort, warp)"),
    ("canvas",       "Ctrl+D",           "plastron.select_none",         "Deselect"),
    ("canvas",       "Ctrl+A",           "plastron.select_all",          "Select all"),
    ("canvas",       "Ctrl+Shift+I",     "plastron.select_invert",       "Invert selection"),
    ("canvas",       "Delete",           "plastron.select_erase",        "Erase the selected pixels"),
    ("canvas",       "Backspace",        "plastron.select_erase",        "Erase the selected pixels"),
    ("canvas",       "Ctrl+C",           "plastron.pixels_copy",         "Copy pixels"),
    ("canvas",       "Ctrl+X",           "plastron.pixels_copy",         "Cut pixels",             {"cut": True}),
    ("canvas",       "Ctrl+V",           "plastron.pixels_paste",        "Paste in place (new layer)"),
    ("canvas",       "Ctrl+Alt+F",       "plastron.layer_flip",          "Flip selection / layer left-right"),
    ("canvas",       "Ctrl+Alt+Shift+F", "plastron.layer_flip",          "Flip upside down",       {"vertical": True}),

    # --- Timeline: view ---------------------------------------------------
    ("timeline_view", "Alt+Shift+LMB",   "view2d.pan",                   "Pan (drag)"),
    ("timeline_view", "Ctrl+Alt+LMB",    "view2d.zoom",                  "Zoom (drag)"),
    ("timeline_view", "Ctrl+=",          "view2d.zoom_in",               "Zoom in"),
    ("timeline_view", "Ctrl+-",          "view2d.zoom_out",              "Zoom out"),
    ("timeline",     "Ctrl+0",           "sequencer.view_all",           "Fit to screen"),

    # --- Voice -------------------------------------------------------------
    ("playback",     "Ctrl+R",           "plastron.voice_record",        "Record voice at the playhead (again: stop)"),

    ("script",       "LMB",              "plastron.script_click",        "Click a script line: playhead to where it's spoken"),

    # --- Timeline: editing -------------------------------------------------
    ("timeline",     "MouseMove",        "plastron.transcript_hover",    "Light up the transcript word under the mouse"),
    ("timeline",     "LMB",              "plastron.clip_trim",           "Drag a clip edge to retime (else select / move)"),
    ("timeline",     "Ctrl+LMB",         "plastron.clip_trim",           "...snapping (Ctrl flips snapping)"),
    ("timeline",     "Shift+LMB",        "plastron.clip_trim",           "Shift+click: add a clip to the selection", {"extend": True}),
    # (after the edge drag: of two actions on one key, the later line is tried first)
    ("timeline",     "LMB",              "plastron.transcript_click",    "Click a transcript word: playhead there, select it"),
    ("timeline",     "Shift+LMB",        "plastron.transcript_click",    "Select words up to this one", {"extend": True}),
    ("timeline",     "N",                "plastron.panel_new",           "New panel at playhead"),
    ("canvas",       "N",                "plastron.panel_new",           "New panel at playhead"),
    ("timeline",     "Ctrl+K",           "plastron.clip_split",          "Split at playhead"),
    ("canvas",       "Ctrl+K",           "plastron.clip_split",          "Split at playhead"),
    ("timeline",     "Delete",           "plastron.clip_delete",         "Delete clip"),
    ("timeline",     "Backspace",        "plastron.clip_delete",         "Delete clip"),
    ("timeline",     "S",                "plastron.timeline_tool",       "Slice tool (click a clip to cut it)", {"tool": 'SLICE'}),
    ("canvas",       "S",                "plastron.timeline_tool",       "Slice tool (click a clip to cut it)", {"tool": 'SLICE'}),
    ("timeline",     "A",                "plastron.timeline_tool",       "Move tool (move / resize clips)", {"tool": 'MOVE'}),
    ("canvas",       "A",                "plastron.timeline_tool",       "Move tool (move / resize clips)", {"tool": 'MOVE'}),
    ("timeline",     "I",                "plastron.loop_set",            "Loop range start",       {"side": 'IN'}),
    ("timeline",     "O",                "plastron.loop_set",            "Loop range end",         {"side": 'OUT'}),
    ("track_headers", "LMB",             "plastron.track_header_click",  "Ripple / solo / volume; pick active track"),
]


# Plastron actions that act and then pass the click on, so Blender's own
# item on the same key keeps working (e.g. the script click still places
# the text cursor).
PASSES_ON = {"plastron.script_click", "plastron.transcript_click", "plastron.transcript_hover"}

# Blender items switched off even though BLENDER_KEEP keeps their keymap.
BLENDER_DROP = {
    # Its press-to-select grabs clip edges itself (a plain resize, no ripple)
    # before Plastron's edge drag sees the click.
    "Sequencer Tool: Select Box*": ["sequencer.select"],
}

# Keys that keep firing while held down (like holding a key in a text box).
REPEAT = {"Q", "W", "Ctrl+Z", "Ctrl+Shift+Z", "Ctrl+=", "Ctrl+-"}


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
    "Image Paint":           ["paint.image_paint"],       # painting itself
    "Sequencer":             ["sequencer.select", "sequencer.select_box",
                              "transform.seq_slide"],
    "Sequencer Channels":    ["*"],                       # rename a track (double-click)
    # Tool keymaps (what a tool does on click/drag) keep everything.
    "3D View Tool: *":       ["*"],
    "Sequencer Tool: *":     ["*"],
    "File Browser*":         ["*"],                       # Open / Save / Import dialogs
    "Sequence Editor Tool: Sequencer, Slice": ["*"],      # Plastron's Slice tool
    "Generic Gizmo*":        ["*"],
}
