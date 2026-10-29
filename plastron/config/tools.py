"""Drawing tools, in the order they appear in the tool strip.

To reorder the strip, move lines. To drop a tool from the strip, set
in_strip to False (its shortcut in keymap.py still works).

mode:  "PAINT" = drawing mode, "EDIT" = selecting / moving strokes.
       Plastron switches mode for you, Photoshop-style.
blender_tool: Blender's internal tool id.
icon:  Blender tool icon name.
"""

TOOLS = [
    # id         label               mode     blender_tool            icon                          in_strip
    ("PENCIL",  "Pencil",           "PAINT", "builtin.brush",        "brush.draw",                 True),
    ("ERASER",  "Eraser",           "PAINT", "builtin_brush.Erase",  "brush.gpencil_draw.erase",   True),
    ("FILL",    "Fill",             "PAINT", "builtin_brush.Fill",   "brush.gpencil_draw.fill",    True),
    ("LASSO",   "Lasso select",     "EDIT",  "builtin.select_lasso", "ops.generic.select_lasso",   True),
    ("RECT",    "Rectangle select", "EDIT",  "builtin.select_box",   "ops.generic.select_box",     True),
    ("MOVE",    "Move",             "EDIT",  "builtin.move",         "ops.transform.translate",    True),
]
