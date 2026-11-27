"""Export Audio (File menu; Ollie: "an export audio option that lets me
export only selected"). The project's sound mixed down to a file (WAV /
FLAC / MP3: AUDIO_FORMATS in config/export.py). With "Selected clips only"
(on by default when clips are selected): every other sound is silenced and
only the selected clips' stretch of time is written (from the first one's
start to the last one's end). A selected video counts by its linked sound.
Volumes, fades, ducking, levelling, breath dips: as they play.
"""

import bpy
from bpy_extras.io_utils import ExportHelper

from ...config import export as cfg
from ...timeline import clips

HAS_SOUND = {'SOUND', 'SCENE'}         # (a scene clip plays its own timeline's sound)


def chosen_sounds(scene):
    """The selected clips' sounds (a video's linked sound too)."""
    picked = [s for s in clips.top_clips(scene) if s.select]
    return [s for s in clips.with_linked(picked) if s.type in HAS_SOUND]


def mixdown(scene, path, fmt="WAV", only=None):
    """Write the mix to path. only: the clips to hear (others silenced; the
    range = their span). Everything is put back after."""
    name, _ext, container, codec, sample = next(f for f in cfg.AUDIO_FORMATS if f[0] == fmt)
    muted = []
    rng = (scene.frame_start, scene.frame_end)
    try:
        if only:
            keep = set(only)
            for s in clips.top_clips(scene):
                if s.type in HAS_SOUND and s not in keep and not s.mute:
                    s.mute = True
                    muted.append(s)
            scene.frame_start = min(clips.start(s) for s in only)
            scene.frame_end = max(clips.end(s) for s in only) - 1
        with bpy.context.temp_override(scene=scene):
            bpy.ops.sound.mixdown(filepath=path, check_existing=False, container=container, codec=codec,
                                  format=sample, mixrate=cfg.AUDIO_RATE, accuracy=1024)
    finally:
        for s in muted:
            s.mute = False
        scene.frame_start, scene.frame_end = rng
    return path


def _formats(_self, _context):
    return [(f[0], f[0], f"Save as {f[0]}") for f in cfg.AUDIO_FORMATS]


class PLASTRON_OT_export_audio(bpy.types.Operator, ExportHelper):
    """Export the sound: the whole mix, or only the selected clips"""
    bl_idname = "plastron.export_audio"
    bl_label = "Export Audio"
    filename_ext = ".wav"
    filter_glob: bpy.props.StringProperty(default="*.wav;*.flac;*.mp3", options={'HIDDEN'})
    fmt: bpy.props.EnumProperty(name="Format", items=_formats)
    selected_only: bpy.props.BoolProperty(name="Selected clips only",
                                          description="Only the selected clips' sound, over their stretch of time")

    def invoke(self, context, event):
        self.selected_only = bool(chosen_sounds(context.scene))
        return ExportHelper.invoke(self, context, event)

    def check(self, context):
        ext = next(f[1] for f in cfg.AUDIO_FORMATS if f[0] == self.fmt)
        self.filename_ext = ext
        return ExportHelper.check(self, context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "fmt")
        row = layout.row()
        row.enabled = bool(chosen_sounds(context.scene))
        row.prop(self, "selected_only")

    def execute(self, context):
        scene = context.scene
        only = chosen_sounds(scene) if self.selected_only else None
        if self.selected_only and not only:
            self.report({'WARNING'}, "No sound clips selected")
            return {'CANCELLED'}
        ext = next(f[1] for f in cfg.AUDIO_FORMATS if f[0] == self.fmt)
        path = bpy.path.ensure_ext(self.filepath, ext)
        mixdown(scene, path, self.fmt, only)
        what = f"{len(only)} selected clip{'s' if len(only) != 1 else ''}" if only else "the whole mix"
        self.report({'INFO'}, f"Audio saved ({what}): {path}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(PLASTRON_OT_export_audio)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_export_audio)
