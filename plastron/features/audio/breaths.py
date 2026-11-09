"""Breath remover: finds breaths in voice clips (short, quiet, noise-like
stretches between words) and dips them (config/audio.py BREATH_*). Kept
as times in the recording, so the dips stay right when the clip is moved,
trimmed or split; written with the clip's other gain curves
(timeline/fades.py)."""

import bpy
import numpy as np

from ...config import audio as cfg
from ...timeline import clips, events, fades
from . import analysis

KEY = "plastron_breaths"          # on a clip: [(start, end)] seconds in its recording


def _runs(mask, step, lo, hi, offset=0.0):
    """[(start, end)] seconds of the True runs lo..hi long."""
    out = []
    i, m = 0, len(mask)
    while i < m:
        if mask[i]:
            j = i
            while j < m and mask[j]:
                j += 1
            if lo <= (j - i) * step <= hi:
                out.append((offset + i * step, offset + j * step))
            i = j
        else:
            i += 1
    return out


def find(x, rate, words=None):
    """[(start, end)] seconds of the breaths in mono samples. With the
    transcript's words ([(word, start, end)]): sound in the gaps between
    words that's over the silence and under the speech. Without: quiet,
    noise-like stretches."""
    step = 0.02
    hop = int(step * rate)
    m = len(x) // hop
    if m < 5:
        return []
    frames = x[:m * hop].reshape(m, hop)
    db = 20 * np.log10(np.maximum(np.sqrt(np.mean(frames ** 2, axis=1)), 1e-6))
    loud = np.percentile(db, 95)
    floor = np.percentile(db, 10)
    breathy = (db < loud - cfg.BREATH_BELOW_SPEECH_DB) & (db > floor + cfg.BREATH_ABOVE_FLOOR_DB)
    lo, hi = cfg.BREATH_SECONDS
    if words:
        gaps = np.zeros(m, bool)
        times = sorted((float(a), float(b)) for _w, a, b in words)
        edges = [(0.0, times[0][0])] + [(times[k][1], times[k + 1][0]) for k in range(len(times) - 1)] \
            + [(times[-1][1], m * step)]
        for a, b in edges:
            if b - a >= lo:
                gaps[int(a / step) + 1:int(b / step) - 1] = True      # (a little in from the words)
        return _runs(breathy & gaps, step, lo, hi)
    power = np.abs(np.fft.rfft(frames * np.hanning(hop), axis=1)) ** 2 + 1e-12
    flat = np.exp(np.mean(np.log(power), axis=1)) / np.mean(power, axis=1)
    return _runs(breathy & (flat > cfg.BREATH_FLATNESS), step, lo, hi)


def _words(strip):
    """The clip's transcript words (voice clips), else None."""
    import json
    voice = getattr(strip, "plastron_voice", None)
    if voice is None or not len(voice.takes):
        return None
    take = voice.takes[voice.active] if 0 <= voice.active < len(voice.takes) else None
    try:
        return json.loads(take.words_json) if take and take.words_json else None
    except ValueError:
        return None


def _clip_breaths(scene, strip):
    """Breaths of the whole recording behind a clip (seconds)."""
    data = analysis.read(analysis.sound_path(strip.sound), cfg.ANALYSIS_RATE)
    return find(data, cfg.ANALYSIS_RATE, _words(strip))


def points(scene, strip):
    """The clip's breath dips as a gain curve on the timeline (frames)."""
    fps = scene.render.fps / scene.render.fps_base
    g = 10 ** (cfg.BREATH_DB / 20.0)
    r = cfg.BREATH_RAMP
    out = []
    for a, b in strip.get(KEY, []):
        fa, fb = strip.content_start + a * fps, strip.content_start + b * fps
        out += [(fa - r * fps, 1.0), (fa, g), (fb, g), (fb + r * fps, 1.0)]
    s, e = clips.start(strip), clips.end(strip)
    return [(f, v) for f, v in out if s - 2 <= f <= e + 2]


def update(scene, **_info):
    """Keep each clip's breath dips where its recording is now."""
    sed = scene.sequence_editor if scene else None
    if sed is None:
        return
    changed = False
    for strip in clips.top_clips(scene):
        if strip.type == 'SOUND' and KEY in strip:
            changed = fades.set_gain(strip, points(scene, strip), "breath") or changed
    if changed:
        events.emit("mix_changed", scene)


def remove(scene, strips):
    """Dip the breaths in these clips. Returns how many were found."""
    n = 0
    for strip in strips:
        if strip.type != 'SOUND' or strip.sound is None:
            continue
        found = _clip_breaths(scene, strip)
        strip[KEY] = [list(p) for p in found]
        n += sum(1 for f, _v in points(scene, strip)) // 4
    update(scene)
    return n


def keep(scene, strips):
    for strip in strips:
        if KEY in strip:
            del strip[KEY]
        fades.set_gain(strip, [], "breath")
    events.emit("mix_changed", scene)


class PLASTRON_OT_breaths_remove(bpy.types.Operator):
    """Dip the breaths in the selected voice clips"""
    bl_idname = "plastron.breaths_remove"
    bl_label = "Remove Breaths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        chosen = [s for s in clips.top_clips(context.scene) if s.type == 'SOUND' and s.select]
        if not chosen:
            self.report({'INFO'}, "Select a voice clip first")
            return {'CANCELLED'}
        n = remove(context.scene, chosen)
        self.report({'INFO'}, f"{n} breath{'s' if n != 1 else ''} dipped" if n else
                    "No breaths found in the selected clips")
        return {'FINISHED'}


class PLASTRON_OT_breaths_keep(bpy.types.Operator):
    """Put the breaths back in the selected clips"""
    bl_idname = "plastron.breaths_keep"
    bl_label = "Keep Breaths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        keep(context.scene, [s for s in clips.top_clips(context.scene) if s.select])
        return {'FINISHED'}


def draw_tools(layout, context):
    layout.label(text="Breaths (voice clips)")
    row = layout.row(align=True)
    row.operator("plastron.breaths_remove", icon='MUTE_IPO_ON')
    row.operator("plastron.breaths_keep", text="", icon='LOOP_BACK')


classes = (PLASTRON_OT_breaths_remove, PLASTRON_OT_breaths_keep)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    events.listen("clips_changed", update)
    from . import panel
    panel.EXTRA.append(draw_tools)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
