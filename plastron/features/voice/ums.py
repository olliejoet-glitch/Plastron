"""The um checker (Ollie: "an automatic 'um' checker that lets me find ums,
highlights them in the timeline, cuts them to separate them, and then lets
me delete them ... ripple effects to work with this").

Timeline header "Ums" pop-up:
  Transcribe       selected sound clips that have no transcript yet (footage
                   sound too: it becomes a clip with one take, its words
                   from the local speech model, like a voice recording)
  Find             every um / uh... (UMS["words"] in config/voice.py) in the
                   transcripts is lit red over its clip, with half the gap
                   either side (what a cut takes out); "n ums". Whisper
                   still leaves many out (Ollie: "missing 90% of them"), so
                   voiced sounds in a gap between two words with no word of
                   their own count too (gap_sounds; UMS "gap_*" / "sound_*")
  Separate         each um is cut out into its own clip (linked video
                   pieces too), all of them selected and marked red, so
                   they can be checked (play them, Shift+click to keep one)
  Delete           the um clips go, following ripple (later clips close up)
Delete / Backspace after Separate does the same (they're selected).
"""

import os
import wave

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from ...config import voice as cfg
from ...core.theme import _color
from ...timeline import clips, events, header, ripple, tracks
from . import takes, transcribe, transcript_bar

MARK = "plastron_um"           # strip flag: a clip separated out as an um
_state = {"show": False, "found": None}


def is_um(word):
    return word.strip(" ,.!?;:-…\"'").lower() in cfg.UMS["words"]


HOP = 0.02            # s: loudness steps for finding unworded sounds


def gap_sounds(env, words, hop=HOP, look=None):
    """Pure: [(start s, end s)] of voiced stretches in the gaps between words
    (and before the first / after the last) that no word covers: ums the
    transcript left out. env: dB per hop from the take's start."""
    look = look or cfg.UMS
    if not len(env):
        return []
    loud = float(np.percentile(env, 95))
    voiced = env >= loud - look["sound_db"]
    edges = [(-1e9, 0.0)] + [(s, e) for _w, s, e in words] + [(len(env) * hop, 1e9)]
    out = []
    for (_s0, e0), (s1, _e1) in zip(edges, edges[1:]):
        g0, g1 = max(0.0, e0) + look["edge_s"], min(len(env) * hop, s1) - look["edge_s"]
        if g1 - g0 < look["gap_min_s"] - 2 * look["edge_s"]:
            continue
        a, b = int(g0 / hop), int(g1 / hop)
        run = None
        for k in range(a, b + 1):
            on = k < b and voiced[k]
            if on and run is None:
                run = k
            elif not on and run is not None:
                t0, t1 = run * hop, k * hop
                if look["sound_min_s"] <= t1 - t0 <= look["sound_max_s"]:
                    out.append((t0, t1))
                run = None
    return out


def _gap_spans(scene, strip, word_list):
    """[(start s, end s)] (in the take) of the clip's unworded sounds, cut a
    little wider (as a word's cut: half the quiet either side, at most 0.15 s)."""
    if not cfg.UMS.get("gap_sounds"):
        return []
    from ..audio import analysis
    take = takes.active_take(strip)
    if take is None or take.sound is None:
        return []
    try:
        env = analysis.file_envelope(analysis.sound_path(take.sound), HOP)
    except Exception as err:            # (a sound aud can't read: words only)
        print("Plastron ums: couldn't read the sound:", err)
        return []
    pad = 0.15
    return [(max(0.0, a - pad), b + pad) for a, b in gap_sounds(env, word_list)]


def find(scene):
    """[(strip, first frame, end frame, word index or None)] of every um in
    the clips: um words in the transcripts (their stretch with half the gap
    either side), and voiced sounds between words with no word of their own
    (index None), in timeline order."""
    out = []
    fps = scene.render.fps / scene.render.fps_base
    for strip in clips.top_clips(scene):
        if not takes.is_voice(strip) or strip.get(MARK):
            continue
        word_list = takes.words(takes.active_take(strip))
        spans = []
        for i, (word, _s, _e) in enumerate(word_list):
            if is_um(word):
                spans.append((*transcript_bar.word_span(word_list, i, i), i))
        if word_list:
            spans += [(a, b, None) for a, b in _gap_spans(scene, strip, word_list)]
        for s, e, i in spans:
            f0 = max(clips.start(strip), round(strip.content_start + s * fps))
            f1 = min(clips.end(strip), round(strip.content_start + e * fps))
            if f1 > f0:
                out.append((strip, f0, f1, i))
    out.sort(key=lambda u: (u[1], u[0].channel))
    merged = []                         # (an um word and a sound overlapping: one)
    for u in out:
        if merged and merged[-1][0] == u[0] and u[1] < merged[-1][2]:
            m = merged[-1]
            merged[-1] = (m[0], m[1], max(m[2], u[2]), m[3] if m[3] is not None else u[3])
        else:
            merged.append(u)
    return merged


def found(scene):
    if _state["found"] is None:
        _state["found"] = [(s.name, s.channel, f0, f1) for s, f0, f1, _i in find(scene)]
    return _state["found"]


def marked(scene):
    return [s for s in clips.top_clips(scene) if s.get(MARK)]


def _dirty(*_args, **_kw):
    _state["found"] = None


# --- separating and deleting --------------------------------------------------------------

def separate(scene):
    """Cut every um into its own clip (with its linked clips); they're marked
    and selected, everything else deselected. Returns the um clips."""
    pieces = []
    for strip, f0, f1, _i in reversed(find(scene)):          # (latest first: earlier cuts stay put)
        ch = strip.channel
        host = next((s for s in clips.on_channel(scene, ch) if clips.start(s) <= f0 < clips.end(s)), None)
        if host is None or clips.editor(scene).channels[ch].lock:
            continue
        if f1 < clips.end(host):
            ripple.split(scene, [host], f1)
        piece = [host]
        if f0 > clips.start(host):
            piece = ripple.split(scene, [host], f0) or []
        else:
            piece = clips.with_linked([host])
        for s in piece:
            s[MARK] = 1
        pieces += piece
    for s in clips.top_clips(scene):
        s.select = bool(s.get(MARK))
    _dirty()
    events.clips_changed(scene)
    return pieces


def delete(scene):
    """Remove the um clips (separating them first), following ripple."""
    if not marked(scene):
        separate(scene)
    gone = marked(scene)
    if gone:
        ripple.delete(scene, gone)
    _dirty()
    events.clips_changed(scene)
    return len(gone)


# --- transcribing footage sound -----------------------------------------------------------

def needs_transcript(strip):
    return strip.type == 'SOUND' and strip.sound is not None and not takes.is_voice(strip)


def transcribe_clip(scene, strip):
    """Give a sound clip (e.g. footage sound) a take of its own sound and
    queue it for the speech model. Its pieces (split copies) share it."""
    from ..audio import analysis
    rate = 16000
    data = analysis.read(analysis.sound_path(strip.sound), rate, keep=False)
    if not len(data):
        return False
    folder = os.path.join(bpy.app.tempdir, "plastron_recordings")
    os.makedirs(folder, exist_ok=True)
    sound = strip.sound
    same = [s for s in clips.top_clips(scene) if needs_transcript(s) and s.sound == sound]
    take = None
    for s in same:
        t = takes._add_take(s, sound, len(data) / rate)
        if take is None:
            take = t
        else:
            t.uid = take.uid                 # (one transcript for every piece of it)
        s.plastron_voice.active = len(s.plastron_voice.takes) - 1
    path = os.path.join(folder, take.uid + "_footage.wav")
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    transcribe.queue(take, path)
    return True


# --- operators ----------------------------------------------------------------------------

class PLASTRON_OT_ums(bpy.types.Operator):
    """Ums: find / separate / delete the ums in the transcripts"""
    bl_idname = "plastron.ums"
    bl_label = "Ums"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(items=[
        ('TRANSCRIBE', "Transcribe", "Transcribe the selected sound clips (footage sound too)"),
        ('AGAIN', "Transcribe Again", "Transcribe the selected clips again (keeps more ums)"),
        ('FIND', "Find", "Light up every um in the timeline"),
        ('HIDE', "Hide", "Stop lighting up the ums"),
        ('SEPARATE', "Separate", "Cut each um out into its own clip and select them all, to check"),
        ('DELETE', "Delete", "Delete the ums (following ripple: later clips close up)")])

    @classmethod
    def description(cls, _context, props):
        return {'TRANSCRIBE': "Transcribe the selected sound clips (footage sound too), so their ums can be found",
                'AGAIN': "Transcribe the selected clips again: transcripts made before now left most ums out",
                'FIND': "Light up every um / uh in the timeline",
                'HIDE': "Stop lighting up the ums",
                'SEPARATE': "Cut each um out into its own clip and select them all, so you can check them "
                            "(Shift+click one to keep it), then Delete",
                'DELETE': "Delete every um, following ripple (later clips close up)"}[props.action]

    def execute(self, context):
        scene = context.scene
        if self.action == 'TRANSCRIBE':
            todo = [s for s in clips.top_clips(scene) if s.select and needs_transcript(s)]
            done, seen = 0, set()
            for s in todo:
                if s.sound not in seen and needs_transcript(s):
                    seen.add(s.sound)
                    done += transcribe_clip(scene, s)
            if not done:
                self.report({'INFO'}, "Select sound clips without a transcript first")
                return {'CANCELLED'}
            self.report({'INFO'}, f"Transcribing {done} sound{'s' if done > 1 else ''}...")
            _state["show"] = True
        elif self.action == 'AGAIN':
            seen, n = set(), 0
            for s in clips.top_clips(scene):
                take = takes.active_take(s) if s.select and takes.is_voice(s) else None
                if take is not None and take.uid not in seen:
                    seen.add(take.uid)
                    n += transcribe.queue_again(take)
            if not n:
                self.report({'INFO'}, "Select transcribed clips first")
                return {'CANCELLED'}
            self.report({'INFO'}, f"Transcribing {n} clip{'s' if n > 1 else ''} again...")
            _state["show"] = True
        elif self.action == 'FIND':
            _state["show"] = True
            _dirty()
            n = len(found(scene))
            self.report({'INFO'}, f"{n} um{'s' if n != 1 else ''} found" if n else "No ums found")
        elif self.action == 'HIDE':
            _state["show"] = False
        elif self.action == 'SEPARATE':
            n = len([p for p in separate(scene) if p.type == 'SOUND'])
            _state["show"] = True
            self.report({'INFO'}, f"{n} um{'s' if n != 1 else ''} cut out and selected: Delete removes them"
                        if n else "No ums found")
        else:
            had = len([s for s in marked(scene) if s.type == 'SOUND']) or len(find(scene))
            delete(scene)
            self.report({'INFO'}, f"Deleted {had} um{'s' if had != 1 else ''}" if had else "No ums found")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_PT_ums(bpy.types.Panel):
    bl_idname = "PLASTRON_PT_ums"
    bl_label = "Ums"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 12

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        if any(s.select and needs_transcript(s) for s in clips.top_clips(scene)):
            layout.operator("plastron.ums", text="Transcribe Selected", icon='REC').action = 'TRANSCRIBE'
        if any(s.select and takes.is_voice(s) for s in clips.top_clips(scene)):
            layout.operator("plastron.ums", text="Transcribe Selected Again", icon='FILE_REFRESH').action = 'AGAIN'
        if transcribe.busy():
            layout.label(text=transcribe.status() or "Transcribing...", icon='SORTTIME')
        n, m = len(found(scene)), len([s for s in marked(scene) if s.type == 'SOUND'])
        row = layout.row(align=True)
        if _state["show"]:
            row.operator("plastron.ums", text=f"Find ({n})", icon='VIEWZOOM').action = 'FIND'
            row.operator("plastron.ums", text="", icon='HIDE_OFF').action = 'HIDE'
        else:
            row.operator("plastron.ums", text="Find", icon='VIEWZOOM').action = 'FIND'
        row = layout.row(align=True)
        row.operator("plastron.ums", text="Separate", icon='SCULPTMODE_HLT').action = 'SEPARATE'
        row.operator("plastron.ums", text=f"Delete ({m})" if m else "Delete", icon='TRASH').action = 'DELETE'


def draw_header(layout, context):
    n = len(found(context.scene)) if _state["show"] else 0
    layout.popover("PLASTRON_PT_ums", text=f"Ums {n}" if n else "Ums")


# --- drawing ------------------------------------------------------------------------------

def draw():
    context = bpy.context
    scene, region = context.scene, context.region
    if not _state["show"] or scene is None or scene.sequence_editor is None:
        return
    from ...core.views import is_timeline
    if not is_timeline(context.space_data):
        return
    v2d = region.view2d
    look = cfg.UMS
    rgb = _color(look["color"])[:3]
    tris = []
    for _name, ch, f0, f1 in found(scene):
        tris += _box(v2d, f0, f1, ch, ch + 1)
    for s in marked(scene):
        tris += _box(v2d, clips.start(s), clips.end(s), s.channel, s.channel + 1)
    words = []
    for box in transcript_bar.layout_for(region, scene)[0]:
        if is_um(box["text"]) and not box["trimmed"]:
            words += _rect(box["x"] - 2, box["y"], box["x"] + box["w"] + 2, box["y"] + box["h"])
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    if tris:
        shader.uniform_float("color", (*rgb, look["alpha"]))
        batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    if words:
        shader.uniform_float("color", (*rgb, look["word_alpha"]))
        batch_for_shader(shader, 'TRIS', {"pos": words}).draw(shader)
    gpu.state.blend_set('NONE')


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]


def _box(v2d, f0, f1, c0, c1):
    x0, y0 = v2d.view_to_region(f0, c0 + 0.05, clip=False)
    x1, y1 = v2d.view_to_region(f1, c1 - 0.05, clip=False)
    return _rect(x0, y0, max(x1, x0 + 2), y1)


_handles = []
classes = (PLASTRON_OT_ums, PLASTRON_PT_ums)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    header.add_section(draw_header)
    events.listen("clips_changed", _dirty)
    transcribe.listen(_dirty)
    _handles.append(bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
