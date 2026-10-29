"""Canvas (paper) colour: swatches + colour picker in the tools area.

The colour is Blender's 3D-view background colour, so changing it costs
nothing at draw time. The choice is remembered via core.user_settings.
Swatches: CANVAS_PRESETS in config/theme.py.
"""

import bpy

from ...config import theme as theme_cfg
from ...core import user_settings
from ...core.theme import _color

SETTING = "canvas_color"


def current():
    saved = user_settings.get(SETTING)
    return tuple(saved) if saved else tuple(_color("paper")[:3])


def apply(rgb):
    gradients = bpy.context.preferences.themes[0].view_3d.space.gradients
    gradients.high_gradient = rgb
    gradients.gradient = rgb
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _get(_self):
    return current()


def _set(_self, value):
    rgb = tuple(value)
    user_settings.set(SETTING, list(rgb))
    apply(rgb)


class PLASTRON_OT_canvas_color(bpy.types.Operator):
    """Set the canvas colour"""
    bl_idname = "plastron.canvas_color"
    bl_label = "Canvas Colour"
    bl_options = {'INTERNAL'}

    color: bpy.props.StringProperty(name="Colour (#rrggbb)")

    def execute(self, context):
        context.window_manager.plastron_canvas_color = _color(self.color)[:3]
        return {'FINISHED'}


class PLASTRON_PT_canvas(bpy.types.Panel):
    # Shown in the tools area (see tools.py for why it's VIEW_3D / "Tool").
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Canvas"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        for name, hex_color in theme_cfg.CANVAS_PRESETS:
            row.operator("plastron.canvas_color", text=name).color = hex_color
        layout.prop(context.window_manager, "plastron_canvas_color", text="")


classes = (PLASTRON_OT_canvas_color, PLASTRON_PT_canvas)


def register():
    bpy.types.WindowManager.plastron_canvas_color = bpy.props.FloatVectorProperty(
        name="Canvas Colour", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0,
        get=_get, set=_set)
    for cls in classes:
        bpy.utils.register_class(cls)
    apply(current())


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.plastron_canvas_color
