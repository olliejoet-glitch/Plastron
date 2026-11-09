"""Animatic export (the brief's "one click to export a video of the animatic
with sketches, voice, and temp music").

Renders the timeline as it plays: every panel (re-made at ANIMATIC_SIZE for
the video, not the small timeline picture, from where it starts: camera start
frame and layers at their start), voice, temp sounds and music, to an MP4
(H.264 + AAC; config/export.py). The project's own render settings and
panel pictures are put back afterwards.
"""

import os
import shutil
import tempfile

import bpy
import numpy as np
from bpy_extras.io_utils import ExportHelper

from ...config import export as cfg


def _panel_frames(scene, folder, size):
    """Each panel re-made at size into folder; returns {strip: (old dir, old file)}."""
    from ...layers.flatten import flatten
    from ..storyboard import panel_cache
    from ..storyboard.panels import all_panels
    swapped = {}
    for strip in all_panels(scene):
        mat = strip.plastron_panel.material
        if mat is None or not mat.plastron_stack.enabled:
            continue
        crop, offsets, para = panel_cache.view(strip, mat.plastron_stack)
        rgba = flatten(mat, crop=crop, out_size=size, offsets=offsets, para=para)
        alpha = rgba[..., 3:4]
        rgba[..., :3] = rgba[..., :3] * alpha + panel_cache.paper() * (1.0 - alpha)
        rgba[..., 3] = 1.0
        name = f"animatic_{strip.plastron_panel.uid}.png"
        panel_cache._write(os.path.join(folder, name), np.ascontiguousarray(rgba))
        swapped[strip.name] = (strip.directory, strip.elements[0].filename)
        strip.directory = folder + os.sep
        strip.elements[0].filename = name
    return swapped


def _settings(scene):
    r = scene.render
    f = r.ffmpeg
    return {
        "r": {k: getattr(r, k) for k in ("resolution_x", "resolution_y", "resolution_percentage",
                                          "filepath", "use_sequencer", "use_compositing")},
        "img": r.image_settings.file_format,
        "media": getattr(r.image_settings, "media_type", None),
        "ff": {k: getattr(f, k) for k in ("format", "codec", "audio_codec", "constant_rate_factor", "audio_bitrate")},
    }


def _restore(scene, saved):
    r = scene.render
    if saved["media"] is not None:
        r.image_settings.media_type = saved["media"]
    r.image_settings.file_format = saved["img"]
    for k, v in saved["ff"].items():
        try:
            setattr(r.ffmpeg, k, v)
        except (TypeError, AttributeError):
            pass
    for k, v in saved["r"].items():
        setattr(r, k, v)


QUALITY = {"HIGH": 'HIGH', "MEDIUM": 'MEDIUM', "LOW": 'LOW', "LOSSLESS": 'LOSSLESS', "PERC_LOSSLESS": 'PERC_LOSSLESS'}


def export(context, path, size=None, frames=None, codec=None, quality=None, audio=None, audio_bitrate=None):
    """Render the timeline to path. size: (w, h); frames: (start, end) or
    None; codec / quality / audio / audio_bitrate: export preset values
    (defaults: the animatic's, config/export.py)."""
    scene = context.scene
    size = size or cfg.ANIMATIC_SIZE
    saved = _settings(scene)
    range_saved = (scene.frame_start, scene.frame_end)
    folder = tempfile.mkdtemp(prefix="plastron_animatic_")
    swapped = _panel_frames(scene, folder, size)
    r = scene.render
    try:
        r.resolution_x, r.resolution_y = size
        r.resolution_percentage = 100
        r.use_sequencer = True
        r.use_compositing = False
        if hasattr(r.image_settings, "media_type"):
            r.image_settings.media_type = 'VIDEO'        # (Blender 5: video formats live here)
        r.image_settings.file_format = 'FFMPEG'
        r.ffmpeg.format = cfg.ANIMATIC_FORMAT
        r.ffmpeg.codec = codec or cfg.ANIMATIC_CODEC
        r.ffmpeg.audio_codec = audio or cfg.ANIMATIC_AUDIO
        r.ffmpeg.constant_rate_factor = QUALITY.get(quality, cfg.ANIMATIC_QUALITY) if quality else cfg.ANIMATIC_QUALITY
        if audio_bitrate:
            r.ffmpeg.audio_bitrate = int(audio_bitrate)
        r.filepath = path
        if frames:
            scene.frame_start, scene.frame_end = frames
        bpy.ops.render.render(animation=True)
    finally:
        scene.frame_start, scene.frame_end = range_saved
        sed = scene.sequence_editor
        for name, (directory, filename) in swapped.items():
            strip = sed.strips_all.get(name)
            if strip is not None:
                strip.directory = directory
                strip.elements[0].filename = filename
        _restore(scene, saved)
        shutil.rmtree(folder, ignore_errors=True)
    return path


def still(context, path, size):
    """The picture at the playhead as a PNG at size (panels re-made at that size)."""
    scene = context.scene
    saved = _settings(scene)
    folder = tempfile.mkdtemp(prefix="plastron_still_")
    swapped = _panel_frames(scene, folder, size)
    r = scene.render
    try:
        r.resolution_x, r.resolution_y = size
        r.resolution_percentage = 100
        r.use_sequencer = True
        r.use_compositing = False
        if hasattr(r.image_settings, "media_type"):
            r.image_settings.media_type = 'IMAGE'
        r.image_settings.file_format = 'PNG'
        r.filepath = path
        bpy.ops.render.render(write_still=True)
    finally:
        sed = scene.sequence_editor
        for name, (directory, filename) in swapped.items():
            strip = sed.strips_all.get(name)
            if strip is not None:
                strip.directory = directory
                strip.elements[0].filename = filename
        _restore(scene, saved)
        shutil.rmtree(folder, ignore_errors=True)
    return path


class PLASTRON_OT_export_animatic(bpy.types.Operator, ExportHelper):
    """Export the animatic as a video: panels, voice, temp sounds and music"""
    bl_idname = "plastron.export_animatic"
    bl_label = "Export Animatic"
    filename_ext = ".mp4"
    filter_glob: bpy.props.StringProperty(default="*.mp4", options={'HIDDEN'})

    def execute(self, context):
        export(context, self.filepath)
        self.report({'INFO'}, f"Animatic saved: {self.filepath}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(PLASTRON_OT_export_animatic)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_export_animatic)
