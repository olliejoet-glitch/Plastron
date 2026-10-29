"""Drawing tools, in the order they appear in the tool strip.

To reorder the strip, move lines. To drop a tool from the strip, set
in_strip to False (its shortcut in keymap.py still works).

Painting uses Blender's own Texture Paint brushes.
blender_tool: Blender's internal tool id.
brush:        the brush a tool starts with (from Blender's built-in brushes).
              Picking another brush while a tool is on makes the tool
              remember it (e.g. B brings back the last pencil you used).
icon:         Blender tool icon name.
"""

TOOLS = [
    # id         label      blender_tool            brush                    icon                          in_strip
    ("PENCIL",  "Pencil",  "builtin.brush",        "Paint Hard Pressure",   "brush.draw",                 True),
    ("ERASER",  "Eraser",  "builtin.brush",        "Erase Hard",            "brush.gpencil_draw.erase",   True),
    ("FILL",    "Fill",    "builtin_brush.fill",   "Fill",                  "brush.paint_texture.fill",   True),
    ("BLUR",    "Blur",    "builtin_brush.soften", "Blur",                  "brush.paint_texture.soften", True),
    ("SMUDGE",  "Smudge",  "builtin_brush.smear",  "Smear",                 "brush.paint_texture.smear",  True),
]

# Where Blender's built-in texture-paint brushes live.
BRUSH_LIBRARY = "brushes/essentials_brushes-mesh_texture.blend/Brush/"

# The brush palette (right-click the canvas) is this Blender brush shelf.
# Imported brushes go into this asset library (a folder in Blender's config).
BRUSH_SHELF = "VIEW3D_AST_brush_texture_paint"
BRUSH_LIBRARY_NAME = "Plastron Brushes"

# Onion skin: the panels before and after the one you're drawing on, shown
# faintly behind it. Toggle in the options bar; strength in the Canvas panel.
ONION_SKIN_ON = False         # starting state (your choice is remembered)
ONION_SKIN_OPACITY = 0.25
