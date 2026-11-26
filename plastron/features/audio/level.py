"""Level Voice (Ollie: "I need a normalise audio feature: I have some areas
where I talk more quietly and lean back away from the mic"). Normalise sets
one volume per clip; this evens out the level INSIDE a recording: a smooth
gain curve lifts the quiet stretches and eases down the loud ones to the
voice's typical level (config/audio.py LEVEL_*).

How: loudness in LEVEL_STEP steps, averaged over LEVEL_WINDOW seconds of
SPEECH only (pauses and silence don't count, so leaning back doesn't read as
a pause); gain = typical level - that, partly (LEVEL_AMOUNT), within
LEVEL_MAX_BOOST / LEVEL_MAX_CUT; pauses longer than LEVEL_PAUSE fall back
to no boost (room noise isn't pumped up); smoothed (LEVEL_SMOOTH), then
thinned to the points where it changes.

Kept ONCE on the recording (the Sound: sound["plastron_level"] = flat
[seconds, gain, ...]), so every clip cut from it (um separation, splits,
copies) is levelled, and moves / trims keep it right; each clip's part is
written with its other gain curves (timeline/fades.py, curve "level")."""

import bisect

import bpy
import numpy as np

from ...config import audio as cfg
from ...timeline import clips, events, fades
from . import analysis

KEY = "plastron_level"
RATE = 8000                       # (voice level: plenty, and an hour stays small)


def gain_curve(x, rate):
    """[(seconds, gain)] evening out a voice recording's level (mono samples)."""
    step = cfg.LEVEL_STEP
    hop = max(1, int(step * rate))
    m = len(x) // hop
    if m < 4:
        return []
    frames = x[:m * hop].reshape(m, hop).astype(np.float64)
    power = np.mean(frames ** 2, axis=1) + 1e-12
    db = 10 * np.log10(power)
    loud, floor = np.percentile(db, 95), np.percentile(db, 10)
    speech = (db > loud - cfg.LEVEL_SPEECH_RANGE_DB) & (db > floor + cfg.LEVEL_ABOVE_FLOOR_DB)
    if speech.sum() < 4:
        return []
    # Speech-only loudness over a window: sum of speech power / speech frames in it.
    w = max(1, int(cfg.LEVEL_WINDOW / step))
    kernel = np.ones(w)
    sp = np.convolve(np.where(speech, power, 0.0), kernel, mode="same")
    cnt = np.convolve(speech.astype(np.float64), kernel, mode="same")
    known = cnt >= max(1.0, cfg.LEVEL_MIN_SPEECH / step)
    level = np.full(m, np.nan)
    level[known] = 10 * np.log10(sp[known] / cnt[known])
    typical = float(np.median(level[known & speech])) if np.any(known & speech) else float(np.median(db[speech]))
    gain_db = np.clip((typical - level) * cfg.LEVEL_AMOUNT, -cfg.LEVEL_MAX_CUT, cfg.LEVEL_MAX_BOOST)
    idx = np.arange(m)
    if not np.any(known):
        return []
    gain_db = np.interp(idx, idx[known], gain_db[known])          # (between speech: carried across)
    # Long pauses: no boost in them (room noise stays where it was).
    quiet = ~speech
    pause = int(cfg.LEVEL_PAUSE / step)
    i = 0
    while i < m:
        if quiet[i]:
            j = i
            while j < m and quiet[j]:
                j += 1
            if j - i >= pause:
                ramp = max(1, int(0.2 / step))
                for k in range(i, j):
                    inside = min(k - i, j - 1 - k) / ramp
                    if inside >= 1:
                        gain_db[k] = min(gain_db[k], 0.0)
                    elif gain_db[k] > 0:
                        gain_db[k] *= (1 - inside)
            i = j
        else:
            i += 1
    s = max(1, int(cfg.LEVEL_SMOOTH / step))
    pad = np.pad(gain_db, (s, s), mode="edge")
    gain_db = np.convolve(pad, np.ones(2 * s + 1) / (2 * s + 1), mode="same")[s:-s]
    # Thin out: keep points where the curve turns or has moved LEVEL_TOLERANCE_DB.
    pts = [(0.0, float(gain_db[0]))]
    for k in range(1, m - 1):
        if abs(gain_db[k] - pts[-1][1]) >= cfg.LEVEL_TOLERANCE_DB:
            pts.append(((k + 0.5) * step, float(gain_db[k])))
    pts.append(((m - 0.5) * step, float(gain_db[-1])))
    return [(t, 10 ** (g / 20.0)) for t, g in pts]


def curve(sound):
    flat = sound.get(KEY) if sound is not None else None
    if not flat:
        return [], []
    flat = list(flat)
    return flat[0::2], flat[1::2]


def points(scene, strip):
    """The clip's part of its recording's level curve, on the timeline (frames)."""
    times, gains = curve(strip.sound)
    if not times:
        return []
    fps = scene.render.fps / scene.render.fps_base
    s, e = clips.start(strip), clips.end(strip)
    a = (s - strip.content_start) / fps
    b = (e - strip.content_start) / fps
    i = max(0, bisect.bisect_left(times, a) - 1)
    j = min(len(times), bisect.bisect_right(times, b) + 1)
    return [(strip.content_start + times[k] * fps, gains[k]) for k in range(i, j)]


def update(scene, **_info):
    """Keep each clip's level curve where its recording is now."""
    sed = scene.sequence_editor if scene else None
    if sed is None:
        return
    changed = False
    for strip in clips.top_clips(scene):
        if strip.type != 'SOUND':
            continue
        has = strip.sound is not None and KEY in strip.sound
        if has or fades.gain_points(strip, "level"):
            changed = fades.set_gain(strip, points(scene, strip) if has else [], "level") or changed
    if changed:
        events.emit("mix_changed", scene)


def level(scene, strips):
    """Even out the level of the recordings behind these clips. Returns how many."""
    done = set()
    for strip in strips:
        snd = strip.sound if strip.type == 'SOUND' else None
        if snd is None or snd.name in done:
            continue
        done.add(snd.name)
        x = analysis.read(analysis.sound_path(snd), RATE, keep=False)
        pts = gain_curve(x, RATE)
        snd[KEY] = [v for p in pts for v in p]
    update(scene)
    return len(done)


def clear(scene, strips):
    for strip in strips:
        if strip.type == 'SOUND' and strip.sound is not None and KEY in strip.sound:
            del strip.sound[KEY]
    update(scene)


def _chosen(context):
    return [s for s in clips.top_clips(context.scene) if s.type == 'SOUND' and s.select]


class PLASTRON_OT_level_voice(bpy.types.Operator):
    """Even out the level of the selected clips' recordings: quiet stretches
    (talking softly, leaning back from the mic) come up, loud ones come down"""
    bl_idname = "plastron.level_voice"
    bl_label = "Level Voice"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        chosen = _chosen(context)
        if not chosen:
            self.report({'INFO'}, "Select a voice clip first")
            return {'CANCELLED'}
        n = level(context.scene, chosen)
        self.report({'INFO'}, f"Levelled {n} recording{'s' if n != 1 else ''}")
        return {'FINISHED'}


class PLASTRON_OT_level_clear(bpy.types.Operator):
    """Put the selected clips' recordings back to their own level"""
    bl_idname = "plastron.level_clear"
    bl_label = "Clear Level"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clear(context.scene, _chosen(context))
        return {'FINISHED'}


def draw_tools(layout, context):
    layout.label(text="Level (quiet / loud stretches evened out)")
    row = layout.row(align=True)
    row.operator("plastron.level_voice", icon='NORMALIZE_FCURVES')
    row.operator("plastron.level_clear", text="", icon='LOOP_BACK')


classes = (PLASTRON_OT_level_voice, PLASTRON_OT_level_clear)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    events.listen("clips_changed", update)
    from . import panel
    panel.EXTRA.append(draw_tools)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
