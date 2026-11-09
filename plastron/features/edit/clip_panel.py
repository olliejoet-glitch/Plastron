"""The Clip panel (Edit mode: the preview's sidebar) for the selected clip:
opacity, blend, flips, speed, volume, Reset Position (moving / sizing /
turning it by hand: frame_box).
"""

import bpy

from ...config import edit as cfg


def active_clip(context):
    scene = context.scene
    sed = scene.sequence_editor if scene else None
    strip = sed.active_strip if sed else None
    return strip if strip is not None and strip.select else None


def _is_panel(strip):
    from ..storyboard.panels import is_panel
    return is_panel(strip)


def speed_of(strip):
    return float(strip.get("plastron_speed", 1.0))


def _get_speed(wm):
    strip = active_clip(bpy.context)
    return speed_of(strip) if strip is not None else 1.0


def _set_speed(wm, value):
    from ...timeline import ripple
    strip = active_clip(bpy.context)
    if strip is not None and strip.type in {'MOVIE', 'SOUND'}:
        ripple.set_speed(bpy.context.scene, strip, value)


class PLASTRON_OT_clip_speed(bpy.types.Operator):
    """Play the selected clip at this speed (its sound too)"""
    bl_idname = "plastron.clip_speed"
    bl_label = "Clip Speed"
    bl_options = {'REGISTER', 'UNDO'}
    speed: bpy.props.FloatProperty(default=1.0)

    @classmethod
    def poll(cls, context):
        strip = active_clip(context)
        return strip is not None and strip.type in {'MOVIE', 'SOUND'}

    def execute(self, context):
        from ...timeline import ripple
        ripple.set_speed(context.scene, active_clip(context), self.speed)
        return {'FINISHED'}


def fit_scale(scene, strip):
    """The scale at which the clip's picture fits the frame (as it came in)."""
    e = strip.elements[0] if getattr(strip, "elements", None) else None
    if e is None or not e.orig_width or not e.orig_height:
        return 1.0
    r = scene.render
    return min(r.resolution_x / e.orig_width, r.resolution_y / e.orig_height)


class PLASTRON_OT_clip_reset_frame(bpy.types.Operator):
    """Put the clip back in the middle of the picture, fitting the frame, not turned"""
    bl_idname = "plastron.clip_reset_frame"
    bl_label = "Reset Position"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        strip = active_clip(context)
        return strip is not None and hasattr(strip, "transform")

    def execute(self, context):
        strip = active_clip(context)
        t = strip.transform
        t.offset_x = t.offset_y = 0.0
        t.rotation = 0.0
        t.scale_x = t.scale_y = fit_scale(context.scene, strip)
        return {'FINISHED'}


class PLASTRON_PT_clip(bpy.types.Panel):
    """The selected clip"""
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Clip"
    bl_label = "Clip"

    @classmethod
    def poll(cls, context):
        if context.workspace is not None and context.workspace.name == "Grade":
            return False                       # (Grade mode: the Grade panel has this tab)
        return active_clip(context) is not None

    def draw(self, context):
        layout = self.layout
        strip = active_clip(context)
        layout.prop(strip, "name", text="", icon='SEQUENCE')
        from ...timeline.colors import draw_swatches
        draw_swatches(layout)
        from .windows import is_window_clip
        if is_window_clip(strip):
            layout.operator("plastron.window_toggle", text="Edit Inside (Tab)", icon='WINDOW')
        visual = strip.type != 'SOUND'
        if visual and not _is_panel(strip):
            col = layout.column(align=True)
            col.prop(strip.plastron, "opacity", text="Opacity", slider=True)
            col.prop(strip, "blend_type", text="")
            row = layout.row(align=True)
            row.prop(strip, "use_flip_x", text="Flip ↔", toggle=True)
            row.prop(strip, "use_flip_y", text="Flip ↕", toggle=True)
            layout.label(text="Drag it in the picture to move / size / turn it")
            layout.operator("plastron.clip_reset_frame", icon='LOOP_BACK')
        layout.separator()
        row = layout.row(align=True)                 # (or drag the clip's corner handles on the timeline)
        row.prop(strip.plastron, "fade_in", text="Fade In")
        row.prop(strip.plastron, "fade_out", text="Out")
        if strip.type in {'MOVIE', 'SOUND'}:
            layout.separator()
            layout.label(text="Speed")
            row = layout.row(align=True)
            for speed in cfg.SPEED_BUTTONS:
                op = row.operator("plastron.clip_speed", text=f"{speed:g}×",
                                  depress=abs(speed_of(strip) - speed) < 1e-3)
                op.speed = speed
            layout.prop(context.window_manager, "plastron_clip_speed", text="Speed")
        if strip.type == 'SOUND':
            layout.separator()
            layout.prop(strip.plastron, "volume", text="Volume", slider=True)


classes = (PLASTRON_OT_clip_speed, PLASTRON_OT_clip_reset_frame, PLASTRON_PT_clip)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.plastron_clip_speed = bpy.props.FloatProperty(
        name="Speed", description="How fast the selected clip plays (2 = twice as fast; a voice keeps its pitch)",
        min=0.1, max=10.0, soft_min=0.25, soft_max=4.0, step=10, precision=2,
        get=_get_speed, set=_set_speed)



def unregister():
    del bpy.types.WindowManager.plastron_clip_speed
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
