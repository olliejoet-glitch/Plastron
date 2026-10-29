"""Script linking: the script panel's lines are matched to what was said
(through the transcripts), so

- clicking a line moves the playhead to where it's spoken;
- script words not recorded yet are underlined.

The match (difflib over normalised words: fluffs and ad-libs in the
recording are simply skipped) is redone only when the script or the
transcripts change.
"""

import difflib
import re

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import project_defaults as defaults, voice as cfg
from ...core.theme import _color
from ...timeline import clips, tracks
from . import takes, transcript_bar

_WORD = re.compile(r"[A-Za-z0-9']+")
_cache = {"key": None, "lines": {}, "unspoken": []}
_handles = []


def _norm(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


def spoken(scene):
    """[(normalised word, frame)] of everything heard, in time order."""
    out = []
    for i, track in enumerate(tracks.all_tracks(scene)):
        if track.kind != 'AUDIO':
            continue
        for strip in clips.on_channel(scene, tracks.channel(i)):
            take = takes.active_take(strip) if takes.is_voice(strip) else None
            for w, s, e in takes.words(take) if take else []:
                mid = transcript_bar.word_frame(scene, strip, (s + e) / 2)
                if clips.start(strip) <= mid < clips.end(strip) and _norm(w):
                    out.append((_norm(w), transcript_bar.word_frame(scene, strip, s)))
    out.sort(key=lambda p: p[1])
    return out


def script_words(text):
    """[(normalised word, line index, first column, end column)]."""
    out = []
    for li, line in enumerate(text.lines):
        for m in _WORD.finditer(line.body):
            if _norm(m.group()):
                out.append((_norm(m.group()), li, m.start(), m.end()))
    return out


def match(scene, text):
    """{line index: frame} for lines heard, and the script words not heard."""
    key = (text.as_string(), transcript_bar._version[0], scene.name)
    if _cache["key"] == key:
        return _cache["lines"], _cache["unspoken"]
    script = script_words(text)
    heard = spoken(scene)
    matcher = difflib.SequenceMatcher(None, [w for w, *_ in script], [w for w, _f in heard],
                                      autojunk=False)
    found = {}
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            found[a + k] = heard[b + k][1]
    lines = {}
    for i, (_w, li, _c0, _c1) in enumerate(script):
        if i in found and li not in lines:
            lines[li] = found[i]
    unspoken = [(li, c0, c1) for i, (_w, li, c0, c1) in enumerate(script) if i not in found]
    _cache.update(key=key, lines=lines, unspoken=unspoken)
    return lines, unspoken


def _script():
    return bpy.data.texts.get(defaults.SCRIPT_TEXT_NAME)


def jump_to_line(scene, line_index):
    text = _script()
    if text is None:
        return False
    lines, _unspoken = match(scene, text)
    frame = lines.get(line_index)
    if frame is None:
        return False
    scene.frame_current = int(round(frame))
    return True


class PLASTRON_OT_script_click(bpy.types.Operator):
    """Clicking a script line moves the playhead to where it's spoken"""
    bl_idname = "plastron.script_click"
    bl_label = "Script Click"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        text = context.space_data.text if context.space_data else None
        if text is None or text.name != defaults.SCRIPT_TEXT_NAME:
            return {'PASS_THROUGH'}
        scene = context.scene

        def after_click():       # Blender has placed the cursor on the clicked line by now
            jump_to_line(scene, text.current_line_index)
            return None
        bpy.app.timers.register(after_click, first_interval=0.01)
        return {'PASS_THROUGH'}


def draw():
    context = bpy.context
    space, region = context.space_data, context.region
    text = space.text if space else None
    if text is None or text.name != defaults.SCRIPT_TEXT_NAME or context.scene is None:
        return
    _lines, unspoken = match(context.scene, text)
    if not unspoken:
        return
    first = space.top
    last = first + space.visible_lines + 1
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.uniform_float("color", _color(cfg.WORD_COLORS["unspoken"]))
    thick = max(1.0, context.preferences.system.ui_scale * 1.5)
    tris = []
    for li, c0, c1 in unspoken:
        if not first <= li <= last:
            continue
        x0, y0 = space.region_location_from_cursor(li, c0)
        x1, _y1 = space.region_location_from_cursor(li, c1)
        if x1 <= x0 or y0 < 0 or y0 > region.height:
            continue
        y = y0 - thick - 1
        tris += [(x0, y), (x1, y), (x1, y + thick), (x0, y), (x1, y + thick), (x0, y + thick)]
    if tris:
        gpu.state.blend_set('ALPHA')
        batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
        gpu.state.blend_set('NONE')


classes = (PLASTRON_OT_script_click,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _handles.append(bpy.types.SpaceTextEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    for handle in _handles:
        bpy.types.SpaceTextEditor.draw_handler_remove(handle, 'WINDOW')
    _handles.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
