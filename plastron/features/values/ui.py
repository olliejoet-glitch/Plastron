"""Value groups on screen: four swatches in the canvas options bar (click a
number: paint with that grey; click a swatch: change it), the Values panel
(tools area: swatches, sample from a picture / this panel, Values view),
and a Values toggle in the video preview's header."""

import os

import bpy
import numpy as np
from bpy_extras.io_utils import ImportHelper

from ...config import values as cfg
from . import groups, view


def _get_swatch(i):
    def get(_self):
        g = groups.get()[i]
        return (g, g, g)
    return get


def _set_swatch(i):
    def set_(_self, value):
        gs = groups.get()
        gs[i] = float(groups.luminance(np.array(value[:3])))
        groups.put(gs)
    return set_


def _get_view(_self):
    scene = bpy.context.scene
    return scene is not None and view.values_clip(scene) is not None


def _set_view(_self, on):
    view.show(bpy.context.scene, on)


def paint_with(context, grey):
    ts = context.tool_settings
    ip = ts.image_paint
    for owner in (ip.unified_paint_settings, ip.brush):
        if owner is not None and hasattr(owner, "color"):
            owner.color = (grey, grey, grey)


class PLASTRON_OT_value_use(bpy.types.Operator):
    """Paint with this value group's grey"""
    bl_idname = "plastron.value_use"
    bl_label = "Paint With This Value"
    index: bpy.props.IntProperty()

    def execute(self, context):
        paint_with(context, groups.get()[self.index])
        return {'FINISHED'}


class PLASTRON_OT_values_from_panel(bpy.types.Operator):
    """Set the value groups from the panel being drawn (its greys split into four)"""
    bl_idname = "plastron.values_from_panel"
    bl_label = "From This Panel"

    def execute(self, context):
        from ..storyboard import canvas_sync
        strip = canvas_sync.panel_on_canvas(context.scene)
        if strip is None:
            self.report({'INFO'}, "Scrub onto a panel first")
            return {'CANCELLED'}
        path = bpy.path.abspath(os.path.join(strip.directory, strip.elements[0].filename))
        return self._from(path)

    def _from(self, path):
        if not os.path.exists(path):
            self.report({'WARNING'}, "That picture isn't there")
            return {'CANCELLED'}
        img = bpy.data.images.load(path, check_existing=False)
        try:
            img.scale(min(img.size[0], cfg.SAMPLE_SIZE), min(img.size[1], cfg.SAMPLE_SIZE))
            px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
            img.pixels.foreach_get(px)
            linear = img.is_float
        finally:
            bpy.data.images.remove(img)
        gs = groups.put(groups.from_pixels(px, is_linear=linear))
        self.report({'INFO'}, "Value groups: " + ", ".join(f"{round(g * 100)}%" for g in gs))
        return {'FINISHED'}


class PLASTRON_OT_values_from_image(bpy.types.Operator, ImportHelper):
    """Set the value groups from a picture (its greys split into four)"""
    bl_idname = "plastron.values_from_image"
    bl_label = "From a Picture..."
    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.webp;*.exr",
                                          options={'HIDDEN'})

    def execute(self, context):
        return PLASTRON_OT_values_from_panel._from(self, self.filepath)


class PLASTRON_OT_values_reset(bpy.types.Operator):
    """Back to the default value groups"""
    bl_idname = "plastron.values_reset"
    bl_label = "Reset Values"

    def execute(self, context):
        groups.put(cfg.DEFAULT_GROUPS)
        return {'FINISHED'}


def draw_swatches(layout, context, paint=True):
    wm = context.window_manager
    row = layout.row(align=True)
    for i in range(cfg.COUNT):
        sub = row.row(align=True)
        sub.ui_units_x = 2.2
        sub.prop(wm, f"plastron_value_{i}", text="")
        if paint:
            sub.operator("plastron.value_use", text=str(i + 1)).index = i


class PLASTRON_PT_values(bpy.types.Panel):
    """Your value groups"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Values"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        draw_swatches(layout, context)
        row = layout.row(align=True)
        row.operator("plastron.values_from_panel", icon='IMAGE_DATA')
        row.operator("plastron.values_from_image", text="", icon='FILEBROWSER')
        row.operator("plastron.values_reset", text="", icon='LOOP_BACK')
        layout.prop(context.window_manager, "plastron_values_view", text="Values View", toggle=True,
                    icon='IMAGE_ZDEPTH')


def draw_options_bar(layout, context):
    draw_swatches(layout, context)


def draw_options_bar_right(layout, context):
    layout.prop(context.window_manager, "plastron_values_view", text="Values", toggle=True, icon='IMAGE_ZDEPTH')


def draw_preview(layout, context):
    layout.prop(context.window_manager, "plastron_values_view", text="Values", toggle=True, icon='IMAGE_ZDEPTH')


classes = (PLASTRON_OT_value_use, PLASTRON_OT_values_from_panel, PLASTRON_OT_values_from_image,
           PLASTRON_OT_values_reset, PLASTRON_PT_values)


def register():
    wm = bpy.types.WindowManager
    for i in range(cfg.COUNT):
        setattr(wm, f"plastron_value_{i}", bpy.props.FloatVectorProperty(
            name=f"Value {i + 1}", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0,
            description="This value group's grey (click to change it)", get=_get_swatch(i), set=_set_swatch(i)))
    wm.plastron_values_view = bpy.props.BoolProperty(
        name="Values View", description="See the picture in your value groups only", get=_get_view, set=_set_view)
    for cls in classes:
        bpy.utils.register_class(cls)
    from ..storyboard import options_bar
    options_bar.AFTER_COLOR.append(draw_options_bar)
    options_bar.RIGHT.append(draw_options_bar_right)
    from ...timeline import header
    header.add_preview_section(draw_preview)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for i in range(cfg.COUNT):
        delattr(bpy.types.WindowManager, f"plastron_value_{i}")
    del bpy.types.WindowManager.plastron_values_view
