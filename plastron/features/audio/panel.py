"""The Sound panel (Audio mode: the timeline's sidebar): every audio
track's mix (volume, solo, duck), loudness, beats."""

import bpy

from ...core.views import is_timeline
from ...timeline import tracks


class PLASTRON_PT_sound(bpy.types.Panel):
    """Mixing and sound tools"""
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Sound"
    bl_label = "Mix"

    @classmethod
    def poll(cls, context):
        return is_timeline(context.space_data) and context.scene is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        col = layout.column(align=True)
        for track in tracks.all_tracks(scene):
            if track.kind != 'AUDIO':
                continue
            row = col.row(align=True)
            row.label(text=tracks.name(scene, track))
            row.prop(track, "volume", text="", slider=True)
            row.prop(track, "solo", text="S", toggle=True)
            if hasattr(track, "duck"):
                row.prop(track, "duck", text="Duck", toggle=True)


class PLASTRON_PT_sound_tools(bpy.types.Panel):
    """Loudness, ducking, beats"""
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Sound"
    bl_label = "Sound Tools"

    @classmethod
    def poll(cls, context):
        return is_timeline(context.space_data) and context.scene is not None

    def draw(self, context):
        layout = self.layout
        layout.label(text="Loudness (YouTube-style)")
        row = layout.row(align=True)
        row.operator("plastron.audio_normalise", text="Selected").which = 'SELECTED'
        row.operator("plastron.audio_normalise", text="All").which = 'ALL'
        sed = context.scene.sequence_editor
        strip = sed.active_strip if sed else None
        if strip is not None and strip.type == 'SOUND' and "plastron_lufs" in strip:
            layout.label(text=f"{strip.name}: was {strip['plastron_lufs']:.1f} LUFS", icon='SOUND')
        for draw in EXTRA:
            layout.separator()
            draw(layout, context)


EXTRA = []        # other audio tools add their sections: draw(layout, context)

classes = (PLASTRON_PT_sound, PLASTRON_PT_sound_tools)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
