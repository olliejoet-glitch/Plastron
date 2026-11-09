"""The Grade panel (Grade mode, the picture's sidebar): the selected clip's
lift / gamma / gain wheels, brightness, contrast, saturation, white balance,
looks, copy / paste, and Grade Everything."""

import bpy

from ...core.views import is_preview
from . import grade


class PLASTRON_PT_grade(bpy.types.Panel):
    """Colour grade the selected clip"""
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Clip"           # (the Clip tab: under the Clip panel; Grade mode shows it alone)
    bl_label = "Grade"

    @classmethod
    def poll(cls, context):
        return is_preview(context.space_data) and context.scene is not None

    def draw(self, context):
        layout = self.layout
        sed = context.scene.sequence_editor
        strip = sed.active_strip if sed else None
        row = layout.row(align=True)
        row.operator("plastron.grade_everything", icon='WORLD')
        if not grade.gradable(strip) or not strip.select:
            layout.label(text="Select a clip to grade it")
            return
        layout.label(text=strip.name, icon='COLOR')
        if not grade.is_graded(strip):
            layout.operator("plastron.grade_start", icon='COLOR')
            return
        m = grade.mods(strip)
        cb = m['COLOR_BALANCE'].color_balance
        wheels = layout.grid_flow(columns=3, even_columns=True, align=True)
        for key, label in (("lift", "Shadows"), ("gamma", "Midtones"), ("gain", "Highlights")):
            col = wheels.column(align=True)
            col.label(text=label)
            col.template_color_picker(cb, key, value_slider=True, cubic=False)
            col.prop(cb, key, text="")
        col = layout.column(align=True)
        col.prop(m['BRIGHT_CONTRAST'], "bright", text="Brightness")
        col.prop(m['BRIGHT_CONTRAST'], "contrast", text="Contrast")
        col.prop(strip, "color_saturation", text="Saturation", slider=True)
        row = layout.row(align=True)
        row.prop(m['WHITE_BALANCE'], "white_value", text="White")
        row = layout.row(align=True)
        row.menu("PLASTRON_MT_grade_looks", text="Looks", icon='PRESET')
        row.operator("plastron.grade_copy", text="", icon='COPYDOWN')
        row.operator("plastron.grade_paste", text="", icon='PASTEDOWN')
        row.operator("plastron.grade_reset", text="", icon='LOOP_BACK')


classes = (PLASTRON_PT_grade,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
