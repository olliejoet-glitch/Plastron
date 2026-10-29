"""Canvas options bar (like Photoshop's): settings for the current tool.

Replaces Blender's tool header. Stage 3 adds brush presets, smoothing and
pressure settings here.
"""

from ...core import hidden_ui
from .tools import active_tool_id, tool_table


def draw(self, context):
    layout = self.layout
    current = active_tool_id(context)
    label = next((t["label"] for t in tool_table() if t["id"] == current), "")
    layout.label(text=label)

    if context.mode != 'PAINT_GREASE_PENCIL':
        return
    brush = context.tool_settings.gpencil_paint.brush
    if brush is None:
        return
    size = "unprojected_size" if brush.use_locked_size == 'SCENE' else "size"
    row = layout.row(align=True)
    row.ui_units_x = 8
    row.prop(brush, size, slider=True, text="Size")
    if brush.gpencil_brush_type != 'FILL':
        row = layout.row(align=True)
        row.ui_units_x = 8
        row.prop(brush, "strength", slider=True, text="Opacity")


def register():
    hidden_ui.replace("VIEW3D_HT_tool_header", "draw", draw)


def unregister():
    pass
