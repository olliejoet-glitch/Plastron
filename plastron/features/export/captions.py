"""Captions (File > Export Captions...): an .srt file from the voice clips'
transcripts, at their places on the timeline (trimmed-off words left out,
muted clips too), "um"s left out, grouped into short lines that break at
sentence ends and pauses (config/export.py CAPTION_*)."""

import bpy
from bpy_extras.io_utils import ExportHelper

from ...config import export as cfg
from ...timeline import clips


def timeline_words(scene):
    """[(word, start s, end s)] on the timeline, in order."""
    from ..voice import takes
    fps = scene.render.fps / scene.render.fps_base
    out = []
    for strip in clips.top_clips(scene):
        if strip.type != 'SOUND' or strip.mute or not takes.is_voice(strip):
            continue
        take = takes.active_take(strip)
        s, e = clips.start(strip), clips.end(strip)
        for word, a, b in takes.words(take):
            fa, fb = strip.content_start + a * fps, strip.content_start + b * fps
            if fa < s or fb > e:
                continue                                   # (trimmed off)
            if word.strip(" ,.!?;:-…").lower() in cfg.CAPTION_FLUFFS:
                continue
            out.append((word.strip(), (fa - scene.frame_start) / fps, (fb - scene.frame_start) / fps))
    return sorted(out, key=lambda w: w[1])


def group(words):
    """[(text, start, end)] captions."""
    cues, cur = [], []
    for w in words:
        if cur:
            text = " ".join(x[0] for x in cur + [w])
            if (len(text) > cfg.CAPTION_MAX_CHARS or w[1] - cur[-1][2] >= cfg.CAPTION_GAP
                    or w[2] - cur[0][1] > cfg.CAPTION_MAX_SECONDS or cur[-1][0][-1:] in ".!?"):
                cues.append(cur)
                cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    out = []
    for i, cue in enumerate(cues):
        start, end = cue[0][1], cue[-1][2]
        nxt = cues[i + 1][0][1] if i + 1 < len(cues) else None
        if end - start < cfg.CAPTION_MIN_SECONDS:
            end = start + cfg.CAPTION_MIN_SECONDS if nxt is None else min(start + cfg.CAPTION_MIN_SECONDS, nxt)
        out.append((" ".join(x[0] for x in cue), start, end))
    return out


def stamp(seconds):
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(cues):
    return "".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n\n" for i, (text, a, b) in enumerate(cues, 1))


def export(scene, path):
    cues = group(timeline_words(scene))
    with open(path, "w", encoding="utf-8") as f:
        f.write(srt(cues))
    return len(cues)


class PLASTRON_OT_export_captions(bpy.types.Operator, ExportHelper):
    """Export captions (.srt) from the voice clips' transcripts, for YouTube"""
    bl_idname = "plastron.export_captions"
    bl_label = "Export Captions"
    filename_ext = ".srt"
    filter_glob: bpy.props.StringProperty(default="*.srt", options={'HIDDEN'})

    def execute(self, context):
        n = export(context.scene, self.filepath)
        if not n:
            self.report({'WARNING'}, "No transcribed voice clips: nothing to caption")
            return {'CANCELLED'}
        self.report({'INFO'}, f"{n} captions saved: {self.filepath}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(PLASTRON_OT_export_captions)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_export_captions)
