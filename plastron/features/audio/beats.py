"""Beat markers: Find Beats on a music clip puts a marker on every beat
(named config/audio.py BEAT_MARKER); clip edges snap to them like to any
marker (Ctrl while dragging, or the snap magnet)."""

import bpy

from ...config import audio as cfg
from ...timeline import clips
from . import analysis


def beat_frames(scene, strip):
    fps = scene.render.fps / scene.render.fps_base
    x = analysis.clip_samples(scene, strip, cfg.ANALYSIS_RATE)
    times = analysis.beats(x, cfg.ANALYSIS_RATE)
    return [round(clips.start(strip) + t * fps) for t in times if t * fps < clips.length(strip)]


def clear(scene, start=None, end=None):
    for m in [m for m in scene.timeline_markers if m.name == cfg.BEAT_MARKER
              and (start is None or start <= m.frame < end)]:
        scene.timeline_markers.remove(m)


def mark(scene, strip):
    """Beat markers along the clip (its old ones replaced). Returns their frames."""
    clear(scene, clips.start(strip), clips.end(strip))
    frames = sorted(set(beat_frames(scene, strip)))
    for f in frames:
        scene.timeline_markers.new(cfg.BEAT_MARKER, frame=f)
    return frames


class PLASTRON_OT_beats_find(bpy.types.Operator):
    """Put a marker on every beat of the selected music clips (clips snap to them)"""
    bl_idname = "plastron.beats_find"
    bl_label = "Find Beats"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        chosen = [s for s in clips.top_clips(scene) if s.type == 'SOUND' and s.select]
        if not chosen:
            self.report({'INFO'}, "Select a music clip first")
            return {'CANCELLED'}
        n = sum(len(mark(scene, s)) for s in chosen)
        self.report({'INFO'}, f"{n} beats marked")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_beats_clear(bpy.types.Operator):
    """Remove every beat marker"""
    bl_idname = "plastron.beats_clear"
    bl_label = "Clear Beats"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clear(context.scene)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def draw_tools(layout, context):
    layout.label(text="Ducking: tracks with Duck on dip under " + ", ".join(cfg.VOICE_TRACKS))
    layout.label(text="Beats (clips snap to them)")
    row = layout.row(align=True)
    row.operator("plastron.beats_find", icon='MARKER_HLT')
    row.operator("plastron.beats_clear", text="", icon='X')


classes = (PLASTRON_OT_beats_find, PLASTRON_OT_beats_clear)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from . import panel
    panel.EXTRA.append(draw_tools)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
