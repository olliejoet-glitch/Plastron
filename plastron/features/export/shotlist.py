"""Shot list export (the brief's "panel notes exported as a shot list"):
one row per panel, in time order: number, panel, start, length, status,
notes, script line. CSV, so it opens in any spreadsheet."""

import csv

import bpy
from bpy_extras.io_utils import ExportHelper

from ...timeline import clips


def rows(scene):
    from . import panels_in_order, status_label, timecode
    fps = scene.render.fps / scene.render.fps_base
    out = [["#", "Panel", "Start", "Length (s)", "Status", "Notes", "Script"]]
    for i, strip in enumerate(panels_in_order(scene), 1):
        info = strip.plastron_panel
        out.append([i, strip.name, timecode(scene, clips.start(strip)), f"{clips.length(strip) / fps:.1f}",
                    status_label(strip), getattr(info, "note", ""), info.script_text])
    return out


def export(scene, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:      # (BOM: Excel reads the accents)
        csv.writer(f).writerows(rows(scene))
    return path


class PLASTRON_OT_export_shot_list(bpy.types.Operator, ExportHelper):
    """Export the panels' notes as a shot list (a spreadsheet)"""
    bl_idname = "plastron.export_shot_list"
    bl_label = "Export Shot List"
    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(default="*.csv", options={'HIDDEN'})

    def execute(self, context):
        export(context.scene, self.filepath)
        self.report({'INFO'}, f"Shot list saved: {self.filepath}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(PLASTRON_OT_export_shot_list)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_export_shot_list)
