"""Canvas options bar (like Photoshop's): settings for the current tool.

Replaces Blender's tool header: tool name, brush picker, colour, size,
opacity (+ pen pressure toggles), smoothing.
"""

from ...config.tools import BRUSH_SHELF
from ...core import hidden_ui
from .tools import CONTEXT_MODE, active_tool_id, tool_table


def _owner(ups, brush, unified_flag):
    return ups if getattr(ups, unified_flag, False) else brush


def _pressure(row, brush, prop):
    if hasattr(brush, prop):
        row.prop(brush, prop, text="", icon='STYLUS_PRESSURE')


def draw(self, context):
    layout = self.layout
    _brush_options(layout, context)
    # Drawing aids at the right end of the bar.
    layout.separator_spacer()
    wm = context.window_manager
    layout.prop(wm, "plastron_onion", text="Onion Skin", toggle=True,
                icon='ONIONSKIN_ON' if wm.plastron_onion else 'ONIONSKIN_OFF')


def _brush_options(layout, context):
    current = active_tool_id(context)
    label = next((t["label"] for t in tool_table() if t["id"] == current), "")
    layout.label(text=label)

    if context.mode != CONTEXT_MODE:
        return
    ip = context.tool_settings.image_paint
    brush = ip.brush
    if brush is None:
        return
    ups = ip.unified_paint_settings
    from .brush_presets import current_name
    layout.menu("PLASTRON_MT_brush_presets", text=current_name(context) or "Presets", icon='PRESET')
    row = layout.row(align=True)
    row.template_asset_shelf_popover(BRUSH_SHELF, name=brush.name, icon='BRUSH_DATA')
    row.operator("plastron.brushes_import", text="", icon='IMPORT')
    if current != "ERASER" and brush.image_brush_type in {'DRAW', 'FILL'}:
        layout.prop(_owner(ups, brush, "use_unified_color"), "color", text="")
    if current == "FILL":
        return
    row = layout.row(align=True)
    row.ui_units_x = 8
    row.prop(_owner(ups, brush, "use_unified_size"), "size", slider=True, text="Size")
    _pressure(row, brush, "use_pressure_size")
    row = layout.row(align=True)
    row.ui_units_x = 8
    row.prop(_owner(ups, brush, "use_unified_strength"), "strength", slider=True, text="Opacity")
    _pressure(row, brush, "use_pressure_strength")
    row = layout.row(align=True)
    row.prop(brush, "use_smooth_stroke", text="Smooth", toggle=True)
    if brush.use_smooth_stroke:
        sub = row.row(align=True)
        sub.ui_units_x = 6
        sub.prop(brush, "smooth_stroke_radius", text="Radius", slider=True)


def register():
    hidden_ui.replace("VIEW3D_HT_tool_header", "draw", draw)


def unregister():
    pass
