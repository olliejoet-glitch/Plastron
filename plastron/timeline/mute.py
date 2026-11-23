"""Muting / unmuting clips (Ollie: "any reason why I can't hear the audio?":
a muted clip had no way back, Blender's own mute key being stripped).

H over the timeline (or the header's speaker button, shown while clips are
selected; red when one of them is muted) mutes / unmutes the selected clips
and their linked clips; muted clips draw faded. The Clip panel has the same
toggle. (Whole tracks: the header's checkbox.)
"""

import bpy

from . import clips, events


def selected(scene):
    return [s for s in clips.top_clips(scene) if s.select]


class PLASTRON_OT_clip_mute(bpy.types.Operator):
    """Mute / unmute the selected clips (and their linked clips)"""
    bl_idname = "plastron.clip_mute"
    bl_label = "Mute Clips"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.sequence_editor is not None

    def execute(self, context):
        scene = context.scene
        strips = clips.with_linked(selected(scene))
        if not strips:
            self.report({'INFO'}, "Select clips to mute or unmute")
            return {'CANCELLED'}
        mute = not any(s.mute for s in strips)        # (any muted: unmute them all)
        for s in strips:
            s.mute = mute
        events.emit("mix_changed", scene)
        self.report({'INFO'}, f"{'Muted' if mute else 'Unmuted'} {len(strips)} clip{'s' if len(strips) > 1 else ''}")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def draw_header(layout, context):
    strips = selected(context.scene)
    if strips:
        muted = any(s.mute for s in clips.with_linked(strips))
        row = layout.row()
        row.alert = muted
        row.operator("plastron.clip_mute", text="Muted" if muted else "",
                     icon='MUTE_IPO_ON' if muted else 'OUTLINER_OB_SPEAKER', depress=muted)


def register():
    bpy.utils.register_class(PLASTRON_OT_clip_mute)
    from . import header
    header.add_section(draw_header)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_clip_mute)
