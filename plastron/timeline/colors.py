"""Clip colours: colour-code the selected clips (Blender's colour tags,
shown along the clip). The timeline header's colour button, and the Clip
panel. (Panels' colours also follow their shot status.)"""

import bpy

from . import clips, events

TAGS = ['NONE'] + [f'COLOR_{i:02d}' for i in range(1, 10)]


def icon(tag):
    return 'X' if tag == 'NONE' else f'STRIP_{tag}'


class PLASTRON_OT_clip_color(bpy.types.Operator):
    """Colour the selected clips (their linked clips too)"""
    bl_idname = "plastron.clip_color"
    bl_label = "Clip Colour"
    bl_options = {'REGISTER', 'UNDO'}
    tag: bpy.props.EnumProperty(items=[(t, t, "") for t in TAGS])

    def execute(self, context):
        chosen = [s for s in clips.top_clips(context.scene) if s.select]
        if not chosen:
            self.report({'INFO'}, "Select clips first")
            return {'CANCELLED'}
        for strip in clips.with_linked(chosen, clips.top_clips(context.scene)):
            strip.color_tag = self.tag
        events.clips_changed(context.scene)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def draw_swatches(layout):
    row = layout.row(align=True)
    for tag in TAGS:
        row.operator("plastron.clip_color", text="", icon=icon(tag)).tag = tag


class PLASTRON_PT_clip_color(bpy.types.Panel):
    """Colour the selected clips"""
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'HEADER'
    bl_label = "Clip Colour"
    bl_ui_units_x = 11

    def draw(self, context):
        draw_swatches(self.layout)


def draw_header(layout, context):
    if any(s.select for s in clips.top_clips(context.scene)):
        layout.popover("PLASTRON_PT_clip_color", text="", icon='COLOR')


classes = (PLASTRON_OT_clip_color, PLASTRON_PT_clip_color)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from . import header
    header.add_section(draw_header)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
