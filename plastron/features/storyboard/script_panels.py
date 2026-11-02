"""Panels from the script (Ollie): one panel per line of the script panel.

File > Import Script... reads a text file into the script panel, then makes
the panels; File > Panels from Script makes them from what's typed there.
Blank lines are skipped. Panels go on the active video track (else the top
one) after its last clip; the untouched starter panel of a new project is
replaced. Lines that already have a panel are left alone, so running it
again after adding lines only adds the new ones. Each panel lasts about as
long as its line takes to read (SCRIPT_PANELS in config/timeline.py).

A panel remembers its line, so clicking that line in the script jumps to
it (until it's been recorded: then to where it's spoken).
"""

import os

import bpy
import numpy as np
from bpy_extras.io_utils import ImportHelper

from ...config import project_defaults as defaults, timeline as timeline_cfg
from ...timeline import clips, events, tracks
from . import panels

CFG = timeline_cfg.SCRIPT_PANELS


def script_text():
    return bpy.data.texts.get(defaults.SCRIPT_TEXT_NAME)


def script_lines(text):
    """[(line index, line)] of the script's non-blank lines."""
    return [(i, line.body.strip()) for i, line in enumerate(text.lines) if line.body.strip()]


def frames_for(scene, line):
    fps = scene.render.fps / scene.render.fps_base
    seconds = min(CFG["max_seconds"], max(CFG["min_seconds"], len(line.split()) * CFG["seconds_per_word"]))
    return max(1, round(seconds * fps))


def _untouched(strip):
    """A panel nobody has drawn on (nor tied to a line)?"""
    if strip.plastron_panel.script_line >= 0:
        return False
    mat = strip.plastron_panel.material
    if mat is None:
        return True
    for layer in mat.plastron_stack.layers:
        if layer.layer_type != "PAINT" or layer.paint_image is None:
            return False
        px = np.empty(len(layer.paint_image.pixels), np.float32)
        layer.paint_image.pixels.foreach_get(px)
        if px[3::4].max(initial=0.0) > 0.0:
            return False
    return True


def _track(scene):
    track = tracks.active(scene)
    if track is None or track.kind != 'VIDEO':
        videos = tracks.video_tracks(scene)
        track = videos[-1] if videos else None
    return track


def make_panels(scene, text=None):
    """Panels for the script's lines that don't have one yet. Returns how
    many were made, or an error message."""
    text = text or script_text()
    if text is None:
        return "There's no script"
    lines = script_lines(text)
    if not lines:
        return "The script is empty"
    track = _track(scene)
    if track is None:
        return "There's no video track"
    if tracks.is_locked(scene, track):
        return "That track is locked"
    channel = tracks.channel_of(scene, track)
    on_track = clips.on_channel(scene, channel)
    done = {s.plastron_panel.script_line for s in panels.all_panels(scene)
            if s.plastron_panel.script_line >= 0}
    start = max((clips.end(s) for s in on_track), default=scene.frame_start)
    starters = [s for s in on_track if panels.is_panel(s)]
    if len(on_track) == 1 and len(starters) == 1 and _untouched(starters[0]):
        start = clips.start(starters[0])        # replace the blank starter panel
        clips.editor(scene).strips.remove(starters[0])
    made = 0
    first = None
    for index, line in lines:
        if index in done:
            continue
        length = frames_for(scene, line)
        strip = panels.create(scene, channel, start, length)
        strip.plastron_panel.script_line = index
        strip.plastron_panel.script_text = line[:500]
        first = first or strip
        start += length
        made += 1
    if first is not None:
        for s in clips.all_clips(scene):
            s.select = False
        scene.sequence_editor.active_strip = first
        scene.frame_current = clips.start(first)
    events.clips_changed(scene)
    return made


def panel_for_line(scene, line_index):
    return next((s for s in panels.all_panels(scene) if s.plastron_panel.script_line == line_index), None)


def _report(op, result):
    if isinstance(result, str):
        op.report({'WARNING'}, result)
        return {'CANCELLED'}
    op.report({'INFO'}, f"{result} panel{'s' if result != 1 else ''} made from the script"
              if result else "Every line already has a panel")
    return {'FINISHED'}


class PLASTRON_OT_script_panels(bpy.types.Operator):
    """Make a panel for each line of the script (lines that already have one are left alone)"""
    bl_idname = "plastron.script_panels"
    bl_label = "Panels from Script"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return _report(self, make_panels(context.scene))


class PLASTRON_OT_script_import(bpy.types.Operator, ImportHelper):
    """Read a script from a text file into the script panel and make a panel for each line"""
    bl_idname = "plastron.script_import"
    bl_label = "Import Script"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(default=CFG["file_types"], options={'HIDDEN'})

    def execute(self, context):
        try:
            with open(self.filepath, encoding="utf-8", errors="replace") as f:
                body = f.read().replace("\r\n", "\n")
        except OSError as err:
            self.report({'WARNING'}, f"Couldn't read {os.path.basename(self.filepath)}: {err}")
            return {'CANCELLED'}
        text = script_text() or bpy.data.texts.new(defaults.SCRIPT_TEXT_NAME)
        text.from_string(body)
        for strip in panels.all_panels(context.scene):     # the old script's lines are gone
            strip.plastron_panel.script_line = -1
        return _report(self, make_panels(context.scene, text))


classes = (PLASTRON_OT_script_panels, PLASTRON_OT_script_import)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
