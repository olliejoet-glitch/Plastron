"""Music fitting: Fit to Video stretches a music clip a little (at most
config/audio.py FIT_MAX_STRETCH, keeping its pitch) so one of its beats
lands on the end of the video, cuts it there and fades it out."""

import bpy

from ...config import audio as cfg
from ...timeline import clips, events, fades, ripple
from . import beats


def video_end(scene):
    ends = [clips.end(s) for s in clips.top_clips(scene) if s.type != 'SOUND']
    return max(ends) if ends else None


def fit(scene, strip, target=None):
    """Returns the speed used, or a message."""
    target = video_end(scene) if target is None else target
    if target is None:
        return "There's no video to fit the music to"
    s = clips.start(strip)
    if target <= s:
        return "The music starts after the video ends"
    fps = scene.render.fps / scene.render.fps_base
    lo, hi = 1 - cfg.FIT_MAX_STRETCH, 1 + cfg.FIT_MAX_STRETCH
    # Beats at speed 1 (the clip as it is now, normal speed assumed).
    marks = beats.beat_frames(scene, strip)
    choices = [((b - s) / (target - s), b) for b in marks if b > s]
    choices = [(r, b) for r, b in choices if lo <= r <= hi]
    speed = min(choices, key=lambda c: abs(c[0] - 1.0))[0] if choices else None
    if speed is None:                                    # (no beat near: speed only if the clip is too short)
        full = clips.length(strip)
        speed = full / (target - s) if full < target - s and full / (target - s) >= lo else 1.0
    if abs(speed - 1.0) > 1e-4:
        ripple.set_speed(scene, strip, speed)
    if clips.end(strip) > target:
        ripple.trim(scene, strip, 'RIGHT', target)
    fades.set_fade(scene, strip, 'OUT', min(clips.length(strip) // 2, round(cfg.FIT_FADE * fps)))
    events.clips_changed(scene)
    return speed


class PLASTRON_OT_music_fit(bpy.types.Operator):
    """Fit the selected music clip to the video: a beat lands on the end, then it fades out"""
    bl_idname = "plastron.music_fit"
    bl_label = "Fit to Video"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sed = context.scene.sequence_editor
        strip = sed.active_strip if sed else None
        if strip is None or not strip.select or strip.type != 'SOUND':
            self.report({'INFO'}, "Select a music clip first")
            return {'CANCELLED'}
        result = fit(context.scene, strip)
        if isinstance(result, str):
            self.report({'WARNING'}, result)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Music fitted (speed {result:.3f}×)")
        return {'FINISHED'}


def draw_tools(layout, context):
    layout.label(text="Music (selected clip)")
    layout.operator("plastron.music_fit", icon='MOD_TIME')


classes = (PLASTRON_OT_music_fit,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from . import panel
    panel.EXTRA.append(draw_tools)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
