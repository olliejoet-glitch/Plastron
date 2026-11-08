"""Shot status and notes per panel (the brief's "shot status" colour tag and
"panel notes"). Shown for the panel being drawn on, in the tools area: four
status swatches and a notes field. The status is also the clip's colour on
the timeline. Notes go into the panel sheet / shot list exports.
"""

import bpy

from ...config import review as cfg


def _status_items():
    return [(sid, label, f"Shot status: {label}") for sid, label, _tag, _hex in cfg.STATUS]


def _status_changed(self, context):
    """Colour the panel's clip on the timeline."""
    tag = next((t for sid, _l, t, _h in cfg.STATUS if sid == self.status), 'NONE')
    scene = self.id_data
    sed = getattr(scene, "sequence_editor", None)
    if sed is None:
        return
    for strip in sed.strips_all:
        if getattr(strip, "plastron_panel", None) is not None and strip.plastron_panel.uid \
                and strip.plastron_panel.as_pointer() == self.as_pointer():
            if strip.color_tag != tag:
                strip.color_tag = tag
            return


def panel_now(context):
    from ..storyboard import canvas_sync
    return canvas_sync.panel_on_canvas(context.scene) if context.scene else None


class PLASTRON_PT_panel_info(bpy.types.Panel):
    """The panel being drawn on: its status and notes"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Panel"
    bl_order = 12           # under the Layers panel

    @classmethod
    def poll(cls, context):
        return panel_now(context) is not None

    def draw(self, context):
        layout = self.layout
        strip = panel_now(context)
        info = strip.plastron_panel
        layout.label(text=strip.name, icon='IMAGE_DATA')
        row = layout.row(align=True)
        row.prop(info, "status", expand=True)
        layout.prop(info, "note", text="", icon='TEXT')
        if info.script_text:
            layout.label(text=info.script_text, icon='SCRIPT')


classes = (PLASTRON_PT_panel_info,)


def register():
    from ..storyboard.panels import PLASTRON_PG_panel as Panel
    Panel.status = bpy.props.EnumProperty(name="Status", items=_status_items(),
                                          default=cfg.STATUS_DEFAULT, update=_status_changed)
    Panel.note = bpy.props.StringProperty(
        name="Notes", description="Notes for this panel: camera moves, sound ideas, acting...")
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
