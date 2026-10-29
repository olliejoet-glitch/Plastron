"""Photoshop-style tool switching and the canvas tool strip.

One operator picks any tool from config/tools.py, switching between
drawing and selecting modes automatically.
"""

import bpy
from bl_ui.space_toolsystem_common import ToolSelectPanelHelper

from ...config.tools import TOOLS

_MODES = {"PAINT": 'PAINT_GREASE_PENCIL', "EDIT": 'EDIT'}
_CONTEXT_MODES = {"PAINT": 'PAINT_GREASE_PENCIL', "EDIT": 'EDIT_GREASE_PENCIL'}


def tool_table():
    return [dict(zip(("id", "label", "mode", "blender_tool", "icon", "in_strip"), row))
            for row in TOOLS]


def _tool(tool_id):
    return next(t for t in tool_table() if t["id"] == tool_id)


def drawing_object(context):
    obj = context.view_layer.objects.active
    return obj if obj and obj.type == 'GREASEPENCIL' else None


def active_tool_id(context):
    """Plastron id of the active tool, or None."""
    for mode, context_mode in _CONTEXT_MODES.items():
        if context.mode != context_mode:
            continue
        active = context.workspace.tools.from_space_view3d_mode(context_mode, create=False)
        for tool in tool_table():
            if tool["mode"] == mode and active and active.idname == tool["blender_tool"]:
                return tool["id"]
    return None


class PLASTRON_OT_canvas_tool(bpy.types.Operator):
    """Pick a drawing tool"""
    bl_idname = "plastron.canvas_tool"
    bl_label = "Pick Tool"
    bl_options = {'INTERNAL'}

    tool: bpy.props.EnumProperty(
        items=[(row[0], row[1], "") for row in TOOLS], name="Tool")

    @classmethod
    def poll(cls, context):
        return drawing_object(context) is not None

    @classmethod
    def description(cls, context, properties):
        return _tool(properties.tool)["label"]

    def execute(self, context):
        tool = _tool(self.tool)
        obj = drawing_object(context)
        if obj.mode != _MODES[tool["mode"]]:
            bpy.ops.object.mode_set(mode=_MODES[tool["mode"]])
        bpy.ops.wm.tool_set_by_id(name=tool["blender_tool"], space_type='VIEW_3D')
        return {'FINISHED'}


class PLASTRON_PT_tool_strip(bpy.types.Panel):
    # Shown in the tools area: Blender's Properties "Tool" tab draws the
    # canvas sidebar's "Tool" category (Blender's own panels there are hidden).
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Tools"
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.scale_y = 1.4
        current = active_tool_id(context)
        for tool in tool_table():
            if not tool["in_strip"]:
                continue
            icon = ToolSelectPanelHelper._icon_value_from_icon_handle(tool["icon"])
            col.operator("plastron.canvas_tool", text=tool["label"], icon_value=icon,
                         depress=(tool["id"] == current)).tool = tool["id"]


class PLASTRON_PT_layers(bpy.types.Panel):
    """Stage 1: Blender's layer tree. Stage 3 replaces it with Plastron's."""
    # Shown in the tools area: Blender's Properties "Tool" tab draws the
    # canvas sidebar's "Tool" category (Blender's own panels there are hidden).
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Layers"

    @classmethod
    def poll(cls, context):
        return drawing_object(context) is not None

    def draw(self, context):
        self.layout.template_grease_pencil_layer_tree()


classes = (PLASTRON_OT_canvas_tool, PLASTRON_PT_tool_strip, PLASTRON_PT_layers)
