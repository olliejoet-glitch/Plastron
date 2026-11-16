"""Panels from the script (Ollie): one panel per line of the script panel.

File > Import Script... reads a text file into the script panel, then makes
the panels; File > Panels from Script makes them from what's typed there.
Blank lines are skipped. Panels go on the active video track (else the top
one) after its last clip; the untouched starter panel of a new project is
replaced. Lines that already have a panel are left alone, so running it
again after adding lines only adds the new ones. Each panel lasts a little
longer than its line takes to read aloud: reading time + a pause after the
line (+ a shorter one per other sentence in it) (SCRIPT_PANELS in
config/timeline.py). The pause is the script bar's Pause slider
(remembered); moving it re-times script panels not trimmed by hand.

The script bar (on top of the script panel): Paste Script pastes what you
copied into the script (replacing an empty one, else added at the end) and
makes the panels; Make Panels does it for what's typed; Import reads a file.

A panel remembers its line, so clicking that line in the script jumps to
it (until it's been recorded: then to where it's spoken).
"""

import os

import re

import bpy
import numpy as np
from bpy_extras.io_utils import ImportHelper

from ...config import project_defaults as defaults, timeline as timeline_cfg
from ...core import user_settings
from ...timeline import clips, events, ripple, tracks
from . import panels

CFG = timeline_cfg.SCRIPT_PANELS


def script_text():
    return bpy.data.texts.get(defaults.SCRIPT_TEXT_NAME)


def script_lines(text):
    """[(line index, line)] of the script's non-blank lines."""
    return [(i, line.body.strip()) for i, line in enumerate(text.lines) if line.body.strip()]


PAUSE_KEY = "script_pause"


def pause():
    """The pause after each line (s): the script bar's slider, remembered."""
    return float(user_settings.get(PAUSE_KEY, CFG["pause_seconds"]))


def seconds_for(line, pause_s=None):
    """How long a line's panel lasts: reading it aloud, then a pause (Ollie:
    pauses between sentences), plus a shorter pause per sentence inside it."""
    pause_s = pause() if pause_s is None else pause_s
    words = len(line.split())
    ends = len(re.findall(r"[.!?]+(?=\s|$)", line.strip()))
    inner = max(0, ends - 1)
    seconds = words * CFG["seconds_per_word"] + pause_s * (1 + inner * CFG["sentence_pause_share"])
    return min(CFG["max_seconds"], max(CFG["min_seconds"], seconds))


def frames_for(scene, line, pause_s=None):
    fps = scene.render.fps / scene.render.fps_base
    return max(1, round(seconds_for(line, pause_s) * fps))


def retime(scene, old_pause, new_pause):
    """Panels made from the script that still have the length the old pause
    gave them get the new one (ones trimmed by hand stay). Ripple tracks
    close up / make room. Returns how many changed."""
    changed = 0
    script = [s for s in panels.all_panels(scene) if s.plastron_panel.script_line >= 0
              and s.plastron_panel.script_text]
    for strip in sorted(script, key=clips.start, reverse=True):     # (from the end: starts stay put)
        line = strip.plastron_panel.script_text
        if clips.length(strip) != frames_for(scene, line, old_pause):
            continue
        want = frames_for(scene, line, new_pause)
        if want != clips.length(strip):
            ripple.trim(scene, strip, 'RIGHT', clips.start(strip) + want)
            changed += 1
    return changed


_slider = {"applied": None}


def _apply_pause():
    scene = bpy.context.scene
    new, old = pause(), _slider["applied"]
    _slider["applied"] = None
    if scene is None or old is None or abs(new - old) < 1e-6:
        return None
    if retime(scene, old, new):
        win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
        if win is not None:
            with bpy.context.temp_override(window=win):
                bpy.ops.ed.undo_push(message="Script Pause")
    return None


def _get_pause(_wm):
    return pause()


def _set_pause(_wm, value):
    """Remembered at once; the panels follow a moment after the slider stops."""
    if _slider["applied"] is None:
        _slider["applied"] = pause()
    user_settings.set(PAUSE_KEY, round(float(value), 2))
    if bpy.app.timers.is_registered(_apply_pause):
        bpy.app.timers.unregister(_apply_pause)
    bpy.app.timers.register(_apply_pause, first_interval=0.35)


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


class PLASTRON_OT_script_paste(bpy.types.Operator):
    """Paste the script you copied (from anywhere) and make a panel for each line"""
    bl_idname = "plastron.script_paste"
    bl_label = "Paste Script"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        body = context.window_manager.clipboard.replace("\r\n", "\n").replace("\r", "\n")
        if not body.strip():
            self.report({'INFO'}, "Copy a script first (nothing to paste)")
            return {'CANCELLED'}
        text = script_text() or bpy.data.texts.new(defaults.SCRIPT_TEXT_NAME)
        old = text.as_string()
        text.from_string(body if not old.strip() else old.rstrip("\n") + "\n" + body)
        return _report(self, make_panels(context.scene, text))


def draw_bar(self, context):
    """The script bar (replaces Blender's text editor header)."""
    row = self.layout.row(align=True)
    row.operator("plastron.script_paste", text="Paste Script", icon='PASTEDOWN')
    row.operator("plastron.script_panels", text="Make Panels", icon='SEQ_STRIP_DUPLICATE')
    pause_row = self.layout.row()
    pause_row.ui_units_x = 6
    pause_row.prop(context.window_manager, "plastron_script_pause", text="Pause", slider=True)
    self.layout.operator("plastron.script_import", text="", icon='FILEBROWSER')


classes = (PLASTRON_OT_script_panels, PLASTRON_OT_script_import, PLASTRON_OT_script_paste)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    lo, hi = CFG["pause_range"]
    bpy.types.WindowManager.plastron_script_pause = bpy.props.FloatProperty(
        name="Pause", description="The pause after each script line (your natural pauses between "
        "sentences): panels made from the script are this much longer than their line takes to read",
        min=lo, max=hi, step=10, precision=1, unit='TIME_ABSOLUTE', get=_get_pause, set=_set_pause)
    from ...core import hidden_ui
    hidden_ui.replace("TEXT_HT_header", "draw", draw_bar)


def unregister():
    if bpy.app.timers.is_registered(_apply_pause):
        bpy.app.timers.unregister(_apply_pause)
    del bpy.types.WindowManager.plastron_script_pause
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
