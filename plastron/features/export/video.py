"""Export Video (File menu): the whole timeline rendered to a video file
with an export preset (plastron/presets/export/: size, codec, quality,
audio). YouTube 4K by default. Panels are re-made at the export size from
their paintings, footage renders at full size (not the preview's copies).
Export Frame: the picture at the playhead as a full-size PNG.
"""

import os

import bpy
from bpy_extras.io_utils import ExportHelper

from ...core import presets
from . import animatic

KIND = "export"


def preset_list():
    return presets.all_presets(KIND)


def preset_named(name):
    return next((p for p in preset_list() if p["name"] == name), None) or (preset_list() or [None])[0]


def export(context, path, preset, frames=None):
    """Render the timeline to path with preset (a dict). A Shorts preset
    renders the vertical version (each shot slid to its Shorts box)."""
    size = (preset["width"], preset["height"])
    kw = dict(codec=preset.get("codec", "H264"), quality=preset.get("quality", "HIGH"),
              audio=preset.get("audio", "AAC"), audio_bitrate=preset.get("audio_bitrate", 320))
    if preset.get("shorts"):
        from ..edit import shorts
        return shorts.render(context, path, size, frames=frames, **kw)
    return animatic.export(context, path, size=size, frames=frames, **kw)


def export_frame(context, path, size=None):
    """The picture at the playhead as a PNG (full project size by default)."""
    scene = context.scene
    r = scene.render
    size = size or (r.resolution_x, r.resolution_y)
    return animatic.still(context, path, size)


def _items(_self, _context):
    return [(p["name"], p["name"], f'{p["width"]}×{p["height"]}') for p in preset_list()] or [("", "(none)", "")]


class PLASTRON_OT_export_video(bpy.types.Operator, ExportHelper):
    """Export the video (YouTube 4K, 1080p...: the export presets)"""
    bl_idname = "plastron.export_video"
    bl_label = "Export Video"
    filename_ext = ".mp4"
    filter_glob: bpy.props.StringProperty(default="*.mp4", options={'HIDDEN'})
    preset: bpy.props.EnumProperty(name="Preset", items=_items)

    def execute(self, context):
        preset = preset_named(self.preset)
        if preset is None:
            self.report({'WARNING'}, "No export presets")
            return {'CANCELLED'}
        export(context, self.filepath, preset)
        self.report({'INFO'}, f"Video saved ({preset['name']}): {self.filepath}")
        return {'FINISHED'}


class PLASTRON_OT_export_frame(bpy.types.Operator, ExportHelper):
    """Save the picture at the playhead as a full-size PNG"""
    bl_idname = "plastron.export_frame"
    bl_label = "Export Frame"
    filename_ext = ".png"
    filter_glob: bpy.props.StringProperty(default="*.png", options={'HIDDEN'})

    def execute(self, context):
        export_frame(context, self.filepath)
        self.report({'INFO'}, f"Frame saved: {self.filepath}")
        return {'FINISHED'}


classes = (PLASTRON_OT_export_video, PLASTRON_OT_export_frame)


def register():
    presets.register_kind(KIND, apply=lambda preset, context=None: None, capture=lambda context=None: {})
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
