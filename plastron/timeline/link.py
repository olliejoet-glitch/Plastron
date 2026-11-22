"""Link / unlink clips by hand (Ollie: "link a video and an audio track so
they automatically stay connected, like in DaVinci").

Ctrl+Alt+L (Resolve's key) or the header's chain button on the selected
clips: not all linked together -> linked (they select, move, trim, cut,
delete and ripple together, like a video and its own sound); already linked
together -> unlinked.
"""

import bpy

from . import clips, events


def selected(scene):
    return [s for s in clips.top_clips(scene) if s.select]


def linked_together(strips):
    ids = {s.get(clips.LINK) for s in strips}
    return len(strips) > 1 and len(ids) == 1 and None not in ids


class PLASTRON_OT_clip_link(bpy.types.Operator):
    """Link the selected clips so they stay together (or unlink them if they already are)"""
    bl_idname = "plastron.clip_link"
    bl_label = "Link Clips"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.sequence_editor is not None

    def execute(self, context):
        scene = context.scene
        strips = selected(scene)
        if linked_together(strips):
            clips.unlink_all(strips)
            self.report({'INFO'}, f"Unlinked {len(strips)} clips")
        elif len(strips) < 2:
            strips = clips.with_linked(strips)
            if len(strips) > 1:
                clips.unlink_all(strips)
                self.report({'INFO'}, "Unlinked")
            else:
                self.report({'INFO'}, "Select two or more clips to link")
                return {'CANCELLED'}
        else:
            clips.unlink_all(clips.with_linked(strips))
            clips.link(strips)
            self.report({'INFO'}, f"Linked {len(strips)} clips")
        events.clips_changed(scene)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def draw_header(layout, context):
    strips = selected(context.scene)
    if strips:
        together = linked_together(strips) or (len(strips) == 1 and bool(strips[0].get(clips.LINK)))
        layout.operator("plastron.clip_link", text="", icon='LINKED' if together else 'UNLINKED',
                        depress=together)


def register():
    bpy.utils.register_class(PLASTRON_OT_clip_link)
    from . import header
    header.add_section(draw_header)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_clip_link)
