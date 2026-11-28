"""Breath detector + remover: finds breaths in voice clips (short, quiet,
noise-like stretches between words; config/audio.py BREATH_*).

Like the um checker (Ollie: "I need a breath detector too"): Find shows
each breath tinted over its clip on the timeline (kept ONCE on the
recording: sound["plastron_breaths_found"] = flat [start, end, ...] seconds,
so cuts / moves keep them right); then Dip (the volume dips there: kept as
times in the recording, strip["plastron_breaths"], written with the clip's
other gain curves, timeline/fades.py), Separate (each breath cut out into
its own clip, marked plastron_breath, all selected) or Delete (those clips
removed, following ripple). Keep Breaths undoes the dips; Forget clears
what was found."""

import bisect

import gpu
from gpu_extras.batch import batch_for_shader

import bpy
import numpy as np

from ...config import audio as cfg
from ...timeline import clips, events, fades
from . import analysis

KEY = "plastron_breaths"          # on a clip: [(start, end)] seconds in its recording (dipped)
FOUND = "plastron_breaths_found"  # on a Sound: flat [start, end, ...] seconds (found)
MARK = "plastron_breath"          # on a clip: a breath separated out


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
    power = np.abs(np.fft.rfft(frames * np.hanning(hop), axis=1)) ** 2 + 1e-12
    # Not a sibilant ("s", "sh": noisy too, but nearly all its energy is high
    # up; a breath's is spread lower) (Ollie: "it's marking sibilant noises").
    freqs = np.fft.rfftfreq(hop, 1.0 / rate)
    high = power[:, freqs >= cfg.BREATH_SIBILANT_HZ].sum(axis=1) / power.sum(axis=1)
    k = max(1, int(cfg.BREATH_SIBILANT_SMOOTH / step))          # (averaged: 20 ms slices wobble)
    high = np.convolve(high, np.ones(k) / k, mode="same")
    breathy &= high < cfg.BREATH_MAX_HIGH
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


def _found_of(sound):
    flat = list(sound.get(FOUND, [])) if sound is not None else []
    return list(zip(flat[0::2], flat[1::2]))


def detect(scene, strips):
    """Find the breaths in the recordings behind these clips (once per
    recording). Returns how many breaths are in their clips now."""
    done = set()
    for strip in strips:
        if strip.type != 'SOUND' or strip.sound is None or strip.sound.name in done:
            continue
        done.add(strip.sound.name)
        strip.sound[FOUND] = [t for span in _clip_breaths(scene, strip) for t in span]
    _dirty()
    return len(found(scene, strips))


_cache = {"list": None}


def _dirty(*_args, **_info):
    _cache["list"] = None


def found(scene, among=None):
    """[(clip, frame0, frame1)]: found breaths inside clips (only those
    clips: among), at timeline frames."""
    if _cache["list"] is None:
        fps = scene.render.fps / scene.render.fps_base
        out = []
        for strip in clips.top_clips(scene):
            if strip.type != 'SOUND' or strip.get(MARK) or strip.sound is None or FOUND not in strip.sound:
                continue
            spans = _found_of(strip.sound)
            s, e = clips.start(strip), clips.end(strip)
            a = (s - strip.content_start) / fps
            starts = [x for x, _y in spans]
            for x, y in spans[max(0, bisect.bisect_left(starts, a) - 1):]:
                f0, f1 = strip.content_start + x * fps, strip.content_start + y * fps
                if f0 >= e:
                    break
                if f1 > s:
                    out.append((strip.name, max(f0, s), min(f1, e)))
        _cache["list"] = out
    sed = scene.sequence_editor
    keep = {s.name for s in among} if among is not None else None
    return [(sed.strips_all[n], f0, f1) for n, f0, f1 in _cache["list"]
            if (keep is None or n in keep) and n in sed.strips_all]


def marked(scene):
    return [s for s in clips.top_clips(scene) if s.get(MARK)]


def separate(scene, among=None):
    """Cut each found breath out into its own clip (its linked picture too),
    marked and selected. Returns the breath clips."""
    from ...timeline import ripple
    with events.batch():
        for strip, f0, f1 in reversed(sorted(found(scene, among), key=lambda t: t[1])):
            f0, f1 = round(f0), round(f1)
            ch = strip.channel
            host = next((s for s in clips.on_channel(scene, ch) if clips.start(s) <= f0 < clips.end(s)), None)
            if host is None or f1 - f0 < 1 or clips.editor(scene).channels[ch].lock:
                continue
            if f1 < clips.end(host):
                ripple.split(scene, [host], f1)
            if f0 > clips.start(host):
                piece = ripple.split(scene, [host], f0) or []
            else:
                piece = clips.with_linked([host])
            for s in piece:
                s[MARK] = 1
        for s in clips.top_clips(scene):
            s.select = bool(s.get(MARK))
        _dirty()
        events.clips_changed(scene)
    return marked(scene)


def delete(scene, among=None):
    """Remove the breath clips (separating them first), following ripple."""
    from ...timeline import ripple
    with events.batch():
        if not marked(scene):
            separate(scene, among)
        gone = marked(scene)
        if gone:
            ripple.delete(scene, gone)
        _dirty()
        events.clips_changed(scene)
    return len(gone)


def forget(scene, strips):
    for strip in strips:
        if strip.type == 'SOUND' and strip.sound is not None and FOUND in strip.sound:
            del strip.sound[FOUND]
    _dirty()


def remove(scene, strips):
    """Dip the breaths in these clips. Returns how many were found."""
    n = 0
    for strip in strips:
        if strip.type != 'SOUND' or strip.sound is None:
            continue
        found_here = _found_of(strip.sound) if FOUND in strip.sound else _clip_breaths(scene, strip)
        strip[KEY] = [list(p) for p in found_here]
        n += sum(1 for f, _v in points(scene, strip)) // 4
    update(scene)
    return n


def keep(scene, strips):
    for strip in strips:
        if KEY in strip:
            del strip[KEY]
        fades.set_gain(strip, [], "breath")
    events.emit("mix_changed", scene)


def _sound_clips(context):
    """The selected sound clips (a video's linked sound too), else every sound clip."""
    scene = context.scene
    picked = [s for s in clips.with_linked([s for s in clips.top_clips(scene) if s.select]) if s.type == 'SOUND']
    return picked or [s for s in clips.top_clips(scene) if s.type == 'SOUND']


class PLASTRON_OT_breaths_find(bpy.types.Operator):
    """Find the breaths in the selected voice clips (else every sound clip) and show them on the timeline"""
    bl_idname = "plastron.breaths_find"
    bl_label = "Find Breaths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        chosen = _sound_clips(context)
        if not chosen:
            self.report({'INFO'}, "No sound clips")
            return {'CANCELLED'}
        n = detect(context.scene, chosen)
        self.report({'INFO'}, f"{n} breath{'s' if n != 1 else ''} found" if n else "No breaths found")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_breaths_cut(bpy.types.Operator):
    """Separate: cut each found breath out into its own clip (selected). Delete: remove them, following ripple"""
    bl_idname = "plastron.breaths_cut"
    bl_label = "Separate Breaths"
    bl_options = {'REGISTER', 'UNDO'}

    delete: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, _context, props):
        return ("Remove the breaths (cut out first if needed), closing up on ripple tracks" if props.delete
                else "Cut each found breath out into its own clip, all selected")

    def execute(self, context):
        scene = context.scene
        if self.delete:
            n = delete(scene)
            self.report({'INFO'}, f"{n} breath clip{'s' if n != 1 else ''} removed" if n else "No breaths to remove")
        else:
            n = len(separate(scene))
            self.report({'INFO'}, f"{n} breath clip{'s' if n != 1 else ''} cut out" if n else
                        "No breaths found: Find Breaths first")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'} if n else {'CANCELLED'}


class PLASTRON_OT_breaths_forget(bpy.types.Operator):
    """Stop showing the breaths found in the selected clips (else all)"""
    bl_idname = "plastron.breaths_forget"
    bl_label = "Forget Breaths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        forget(context.scene, _sound_clips(context))
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_breaths_remove(bpy.types.Operator):
    """Dip the breaths in the selected voice clips (quieter, not cut)"""
    bl_idname = "plastron.breaths_remove"
    bl_label = "Dip Breaths"
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
    scene = context.scene
    n = len(found(scene)) if scene and scene.sequence_editor else 0
    m = len(marked(scene)) if scene and scene.sequence_editor else 0
    layout.label(text="Breaths" + (f"  ({n} found" + (f", {m} cut out)" if m else ")") if n or m else ""))
    row = layout.row(align=True)
    row.operator("plastron.breaths_find", icon='VIEWZOOM')
    row.operator("plastron.breaths_forget", text="", icon='X')
    row = layout.row(align=True)
    row.operator("plastron.breaths_remove", text="Dip", icon='MUTE_IPO_ON')
    row.operator("plastron.breaths_keep", text="", icon='LOOP_BACK')
    row.operator("plastron.breaths_cut", text="Separate", icon='SCULPTMODE_HLT').delete = False
    row.operator("plastron.breaths_cut", text="Delete", icon='TRASH').delete = True


def draw():
    """Found breaths (and cut-out breath clips) tinted on the timeline."""
    context = bpy.context
    scene, region = context.scene, context.region
    if scene is None or scene.sequence_editor is None:
        return
    from ...core.views import is_timeline
    if not is_timeline(context.space_data):
        return
    spans = [(s.channel, f0, f1) for s, f0, f1 in found(scene)]
    spans += [(s.channel, clips.start(s), clips.end(s)) for s in marked(scene)]
    if not spans:
        return
    from ...core.theme import _color
    v2d = region.view2d
    tris = []
    for ch, f0, f1 in spans:
        x0, y0 = v2d.view_to_region(f0, ch + 0.05, clip=False)
        x1, y1 = v2d.view_to_region(f1, ch + 0.95, clip=False)
        x1 = max(x1, x0 + 2)
        tris += [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.uniform_float("color", (*_color(cfg.BREATH_COLOR)[:3], cfg.BREATH_ALPHA))
    batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    gpu.state.blend_set('NONE')


_handles = []
classes = (PLASTRON_OT_breaths_find, PLASTRON_OT_breaths_cut, PLASTRON_OT_breaths_forget,
           PLASTRON_OT_breaths_remove, PLASTRON_OT_breaths_keep)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    events.listen("clips_changed", update)
    events.listen("clips_changed", _dirty)
    from . import panel
    panel.EXTRA.append(draw_tools)
    _handles.append(bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
