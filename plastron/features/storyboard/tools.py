"""Photoshop-style tool switching and the canvas tool strip.

Tools are Blender's Texture Paint tools + brushes (config/tools.py). Each
tool remembers the last brush you used with it, so B after picking another
pencil brush brings that one back.
"""

import bpy
from bl_ui.space_toolsystem_common import ToolSelectPanelHelper

from ...config.tools import BRUSH_LIBRARY, TOOLS

PAINT_MODE = 'TEXTURE_PAINT'      # object mode
CONTEXT_MODE = 'PAINT_TEXTURE'    # context.mode while painting

_last_brush = {}   # tool id -> (library type, library id, relative id)


def tool_table():
    return [dict(zip(("id", "label", "blender_tool", "brush", "icon", "in_strip"), row))
            for row in TOOLS]


def _tool(tool_id):
    return next(t for t in tool_table() if t["id"] == tool_id)


def drawing_object(context):
    obj = context.view_layer.objects.active
    return obj if obj and obj.type == 'MESH' else None


def brush(context):
    return context.tool_settings.image_paint.brush


def active_tool_id(context):
    """Plastron id of the active tool, or None."""
    if context.mode != CONTEXT_MODE:
        return None
    active = context.workspace.tools.from_space_view3d_mode(CONTEXT_MODE, create=False)
    if active is None:
        return None
    b = brush(context)
    erasing = b is not None and b.blend == 'ERASE_ALPHA'
    for tool in tool_table():
        if active.idname != tool["blender_tool"]:
            continue
        if tool["blender_tool"] == "builtin.brush" and erasing != (tool["id"] == "ERASER"):
            continue
        return tool["id"]
    return None


def _remember(context):
    tool_id = active_tool_id(context)
    ref = context.tool_settings.image_paint.brush_asset_reference
    if tool_id and ref and ref.relative_asset_identifier:
        _last_brush[tool_id] = (ref.asset_library_type, ref.asset_library_identifier,
                                ref.relative_asset_identifier)


def activate_brush(tool):
    lib_type, lib_id, rel = _last_brush.get(
        tool["id"], ('ESSENTIALS', "", BRUSH_LIBRARY + tool["brush"]))
    try:
        bpy.ops.brush.asset_activate(asset_library_type=lib_type, asset_library_identifier=lib_id,
                                     relative_asset_identifier=rel)
    except RuntimeError:          # a remembered brush that's gone: back to the default
        _last_brush.pop(tool["id"], None)
        bpy.ops.brush.asset_activate(asset_library_type='ESSENTIALS',
                                     relative_asset_identifier=BRUSH_LIBRARY + tool["brush"])


class PLASTRON_OT_canvas_tool(bpy.types.Operator):
    """Pick a painting tool"""
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
        if obj.mode != PAINT_MODE:
            bpy.ops.object.mode_set(mode=PAINT_MODE)
        _remember(context)
        activate_brush(tool)
        if context.workspace.tools.from_space_view3d_mode(CONTEXT_MODE, create=False).idname \
                != tool["blender_tool"]:
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


classes = (PLASTRON_OT_canvas_tool, PLASTRON_PT_tool_strip)
