"""Normalise: set clip volumes so each clip lands on its kind's loudness
target (config/audio.py TARGETS; measured in LUFS like YouTube)."""

import bpy

from ...config import audio as cfg
from ...timeline import clips, events, tracks
from . import analysis

RATE = 48000


def kind_of(scene, strip):
    track = tracks.track_of_clip(scene, strip)
    name = tracks.name(scene, track) if track else ""
    voice = getattr(strip, "plastron_voice", None)
    if name in cfg.VOICE_TRACKS or (voice is not None and len(voice.takes)):
        return "voice"
    if name in cfg.MUSIC_TRACKS:
        return "music"
    return "other"


def measure(scene, strip):
    """The clip's loudness (LUFS) as it plays at volume 1, or None."""
    return analysis.loudness(analysis.clip_samples(scene, strip, RATE), RATE)


def normalise(scene, strips):
    """Returns [(strip, loudness before, new clip volume)] (silent clips left alone)."""
    out = []
    for strip in strips:
        if strip.type != 'SOUND':
            continue
        level = measure(scene, strip)
        if level is None:
            continue
        gain = 10 ** ((cfg.TARGETS[kind_of(scene, strip)] - level) / 20.0)
        gain = min(gain, strip.plastron.bl_rna.properties["volume"].hard_max)
        strip.plastron.volume = gain
        strip["plastron_lufs"] = level
        out.append((strip, level, gain))
    events.emit("mix_changed", scene)
    return out


class PLASTRON_OT_normalise(bpy.types.Operator):
    """Set the clips' volumes so each lands on its loudness target (voice, music, other)"""
    bl_idname = "plastron.audio_normalise"
    bl_label = "Normalise Loudness"
    bl_options = {'REGISTER', 'UNDO'}
    which: bpy.props.EnumProperty(items=[('SELECTED', "Selected", "The selected sound clips"),
                                         ('ALL', "All", "Every sound clip")])

    def execute(self, context):
        scene = context.scene
        strips = [s for s in clips.top_clips(scene) if s.type == 'SOUND'
                  and (self.which == 'ALL' or s.select)]
        done = normalise(scene, strips)
        if not done:
            self.report({'INFO'}, "No sound clips to normalise" if not strips else "Those clips are silent")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Normalised {len(done)} clip{'s' if len(done) != 1 else ''}")
        return {'FINISHED'}


classes = (PLASTRON_OT_normalise,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
