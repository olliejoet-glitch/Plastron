"""Transcript bars: the bottom band of every audio track's row shows the
words of each voice clip, inside the clip's edges.

- Layout (transcript_layout.py) is worked out only when the view (zoom /
  scroll / size) or the clips / transcripts change, and kept; drawing reuses
  it, so playback and scrubbing never re-lay anything out.
- Hover a word: it and its exact spot on the waveform light up.
- Click a word: the playhead jumps to it and it's selected; Shift+click
  selects a run of words; Delete / Backspace cuts their audio (following the
  track's ripple setting). Clicking elsewhere clears the selection.
- The "…" button in an audio track's header collapses its bar to one line.
"""

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import voice as cfg
from ...core import handlers
from ...core.theme import _color
from ...timeline import clips, events, ops as timeline_ops, ripple, tracks
from . import takes, transcribe, transcript_layout

FONT = 0
FONT_PX = 11

_version = [0]
_cache = {}            # region pointer -> (key, boxes, ellipses, bands)
_hover = {"box": None}
_sel = {"strip": None, "take": None, "indices": set(), "anchor": None}


def changed(*_args, **_kw):
    """Clips, tracks or transcripts changed: lay out again at the next draw."""
    _version[0] += 1


def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def _fps(scene):
    return scene.render.fps / scene.render.fps_base


def word_frame(scene, strip, seconds):
    return strip.content_start + seconds * _fps(scene)


# --- layout ---------------------------------------------------------------------------

def _key(region, scene):
    v2d = region.view2d
    collapse = tuple(t.collapse for t in tracks.all_tracks(scene) if t.kind == 'AUDIO')
    return (v2d.region_to_view(0, 0), v2d.region_to_view(region.width, region.height),
            region.width, region.height, _ui(1), _version[0], collapse, scene.name)


def _widths(texts):
    blf.size(FONT, _ui(FONT_PX))
    return [blf.dimensions(FONT, t)[0] for t in texts]


def build(region, scene):
    """Word boxes for every visible voice clip: dicts with text, position,
    times and state; plus "…" positions and each audio track's bar."""
    v2d = region.view2d
    gap = _ui(cfg.WORD_GAP_PX)
    line_h = _ui(FONT_PX) * 1.4
    ell_w = _widths([transcript_layout.ELLIPSIS])[0]
    boxes, ellipses, bands = [], [], []
    for i, track in enumerate(tracks.all_tracks(scene)):
        if track.kind != 'AUDIO':
            continue
        ch = tracks.channel(i)
        y0 = v2d.view_to_region(0, ch, clip=False)[1]
        y1 = v2d.view_to_region(0, ch + 1, clip=False)[1]
        if y1 < 0 or y0 > region.height:
            continue
        top = y0 + (y1 - y0) * cfg.BAR_FRACTION
        bands.append((y0 + 1, top, y1))
        lines = 1 if track.collapse else max(1, int((top - y0 - 2) // line_h))
        for strip in clips.on_channel(scene, ch):
            take = takes.active_take(strip) if takes.is_voice(strip) else None
            word_list = takes.words(take) if take else []
            if not word_list:
                continue
            x0 = v2d.view_to_region(clips.start(strip), 0, clip=False)[0]
            x1 = v2d.view_to_region(clips.end(strip), 0, clip=False)[0]
            if x1 < 0 or x0 > region.width:
                continue
            widths = _widths([w for w, _s, _e in word_list])
            items = []
            for (text, s, e), w in zip(word_list, widths):
                f0, f1 = word_frame(scene, strip, s), word_frame(scene, strip, e)
                mid = (f0 + f1) / 2
                trimmed = not (clips.start(strip) <= mid < clips.end(strip))
                items.append((v2d.view_to_region(f0, 0, clip=False)[0], w, trimmed))
            _mode, placed, ellipsis = transcript_layout.layout(items, x0, x1, lines, gap, ell_w)
            for index, x, line in placed:
                text, s, e = word_list[index]
                baseline = top - line_h * (line + 1) + _ui(3)
                boxes.append({
                    "strip": strip.name, "take": take.uid, "index": index, "text": text,
                    "x": x, "y": baseline - _ui(3), "w": widths[index], "h": line_h,
                    "baseline": baseline, "trimmed": items[index][2],
                    "f0": word_frame(scene, strip, s), "f1": word_frame(scene, strip, e),
                    "wave": (top, y1)})
            if ellipsis:
                ellipses.append((ellipsis[0], top - line_h * (ellipsis[1] + 1) + _ui(3)))
    return boxes, ellipses, bands


def layout_for(region, scene):
    key = _key(region, scene)
    cached = _cache.get(region.as_pointer())
    if cached is None or cached[0] != key:
        cached = (key, *build(region, scene))
        _cache[region.as_pointer()] = cached
    return cached[1], cached[2], cached[3]


def hit(region, scene, x, y):
    cached = _cache.get(region.as_pointer())
    if cached is None:
        return None
    for box in cached[1]:
        if box["x"] - 2 <= x <= box["x"] + box["w"] + 2 and box["y"] <= y <= box["y"] + box["h"]:
            return box
    return None


# --- drawing ---------------------------------------------------------------------------

def _rect(shader, x0, y0, x1, y1, colour):
    shader.uniform_float("color", colour)
    batch_for_shader(shader, 'TRI_FAN', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(shader)


def _c(name, alpha=None):
    c = list(_color(cfg.WORD_COLORS[name]))
    if alpha is not None:
        c[3] = alpha
    return c


def _selected(box):
    return box["strip"] == _sel["strip"] and box["index"] in _sel["indices"]


def draw():
    context = bpy.context
    scene, region = context.scene, context.region
    if scene is None or not hasattr(scene, "plastron_timeline") or scene.sequence_editor is None:
        return
    boxes, ellipses, bands = layout_for(region, scene)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    for y0, top, _y1 in bands:
        _rect(shader, 0, y0, region.width, top, _c("bar", 0.55))
    hover = _hover["box"]
    for box in boxes:
        if _selected(box):
            _rect(shader, box["x"] - 2, box["y"], box["x"] + box["w"] + 2, box["y"] + box["h"],
                  _c("selected", 0.45))
    if hover is not None:
        _rect(shader, hover["x"] - 2, hover["y"], hover["x"] + hover["w"] + 2, hover["y"] + hover["h"],
              _c("hover", 0.5))
        v2d = region.view2d
        wx0 = v2d.view_to_region(hover["f0"], 0, clip=False)[0]
        wx1 = v2d.view_to_region(hover["f1"], 0, clip=False)[0]
        _rect(shader, wx0, hover["wave"][0], max(wx1, wx0 + 2), hover["wave"][1], _c("hover", 0.4))
    blf.size(FONT, _ui(FONT_PX))
    for box in boxes:
        colour = _c("trimmed") if box["trimmed"] else _c("text")
        blf.color(FONT, *colour)
        blf.position(FONT, box["x"], box["baseline"], 0)
        blf.draw(FONT, box["text"])
        if box["trimmed"]:          # struck through
            mid = box["baseline"] + _ui(FONT_PX) * 0.35
            _rect(shader, box["x"], mid, box["x"] + box["w"], mid + max(1, _ui(1)), colour)
    blf.color(FONT, *_c("text"))
    for x, baseline in ellipses:
        blf.position(FONT, x, baseline, 0)
        blf.draw(FONT, transcript_layout.ELLIPSIS)
    gpu.state.blend_set('NONE')


# --- hover, click, cut -----------------------------------------------------------------

def _main_region(context):
    return context.region is not None and context.region.type == 'WINDOW' and \
        context.area is not None and context.area.type == 'SEQUENCE_EDITOR'


class PLASTRON_OT_transcript_hover(bpy.types.Operator):
    """Light up the word under the mouse and its spot on the waveform"""
    bl_idname = "plastron.transcript_hover"
    bl_label = "Transcript Hover"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if not _main_region(context):
            return {'PASS_THROUGH'}
        box = hit(context.region, context.scene, event.mouse_region_x, event.mouse_region_y)
        if box is not _hover["box"]:
            _hover["box"] = box
            context.region.tag_redraw()
        return {'PASS_THROUGH'}


def _near_clip_edge(context, box, x):
    from ...config import timeline as timeline_cfg
    sed = context.scene.sequence_editor
    strip = sed.strips_all.get(box["strip"]) if sed else None
    if strip is None:
        return False
    v2d = context.region.view2d
    grab = _ui(timeline_cfg.EDGE_GRAB_PX)
    return any(abs(x - v2d.view_to_region(f, 0, clip=False)[0]) <= grab
               for f in (clips.start(strip), clips.end(strip)))


class PLASTRON_OT_transcript_click(bpy.types.Operator):
    """Click a word: jump the playhead there and select it (Shift: select up to it)"""
    bl_idname = "plastron.transcript_click"
    bl_label = "Transcript Click"
    bl_options = {'REGISTER', 'UNDO'}

    extend: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if not _main_region(context):
            return {'PASS_THROUGH'}
        box = hit(context.region, context.scene, event.mouse_region_x, event.mouse_region_y)
        if box is not None and _near_clip_edge(context, box, event.mouse_region_x):
            box = None                   # a clip edge: let the edge drag have it
        if box is None:
            if _sel["indices"]:
                clear_selection()
                context.region.tag_redraw()
            return {'PASS_THROUGH'}
        i = box["index"]
        if self.extend and _sel["strip"] == box["strip"] and _sel["anchor"] is not None:
            a = _sel["anchor"]
            _sel["indices"] = set(range(min(a, i), max(a, i) + 1))
        else:
            _sel.update(strip=box["strip"], take=box["take"], indices={i}, anchor=i)
        context.scene.frame_current = int(round(box["f0"]))
        context.region.tag_redraw()
        return {'FINISHED'}


def clear_selection():
    _sel.update(strip=None, take=None, indices=set(), anchor=None)


def selection():
    return dict(_sel)


def cut_words(scene, strip, indices):
    """Cut the audio of the given words out of strip (following the track's
    ripple setting). Returns True if anything was cut."""
    take = takes.active_take(strip)
    word_list = takes.words(take) if take else []
    if not word_list or not indices:
        return False
    if clips.editor(scene).channels[strip.channel].lock:
        return False
    a, b = min(indices), max(indices)
    s = word_list[a][1] if a == 0 else (word_list[a - 1][2] + word_list[a][1]) / 2
    e = word_list[b][2] if b + 1 >= len(word_list) else (word_list[b][2] + word_list[b + 1][1]) / 2
    f0 = max(clips.start(strip), round(word_frame(scene, strip, s)))
    f1 = min(clips.end(strip), round(word_frame(scene, strip, e)))
    if f1 <= f0:
        return False
    piece = strip
    if f1 < clips.end(strip):
        ripple.split(scene, [strip], f1)
    if f0 > clips.start(strip):
        right = ripple.split(scene, [strip], f0)
        piece = right[0] if right else None
    if piece is None:
        return False
    ripple.delete(scene, [piece])
    return True


class PLASTRON_OT_transcript_cut(bpy.types.Operator):
    """Cut the selected words' audio out (follows the track's ripple setting)"""
    bl_idname = "plastron.transcript_cut"
    bl_label = "Cut Words"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sed = context.scene.sequence_editor
        return bool(_sel["indices"]) and sed is not None and _sel["strip"] in sed.strips_all

    def execute(self, context):
        scene = context.scene
        strip = scene.sequence_editor.strips_all[_sel["strip"]]
        done = cut_words(scene, strip, set(_sel["indices"]))
        clear_selection()
        return {'FINISHED'} if done else {'CANCELLED'}


def _delete(context):
    """Delete / Backspace on the timeline: cut the selected words, if any."""
    sed = context.scene.sequence_editor
    if not _sel["indices"] or sed is None or _sel["strip"] not in sed.strips_all:
        return False
    cut_words(context.scene, sed.strips_all[_sel["strip"]], set(_sel["indices"]))
    clear_selection()
    return True


classes = (PLASTRON_OT_transcript_hover, PLASTRON_OT_transcript_click, PLASTRON_OT_transcript_cut)
_handles = []


def _after_undo(*_args):
    changed()
    clear_selection()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for event in ("clips_changed", "tracks_changed"):
        events.listen(event, changed)
    transcribe.listen(changed)
    timeline_ops.delete_handlers.append(_delete)
    handlers.add("undo_post", _after_undo)
    handlers.add("redo_post", _after_undo)
    handlers.on_load(_after_undo)
    _handles.append(bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    for handle in _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(handle, 'WINDOW')
    _handles.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
