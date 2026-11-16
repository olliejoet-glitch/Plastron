"""The script follows the playhead (Ollie: "when I scrub and play, I want the
correct lines in the script to be highlighted").

The line at the playhead is highlighted in the script panel (a band behind
it) and scrolled into view. Which line: where a recorded voice clip is
playing, the line last heard (script_link's match); elsewhere the script
line of the panel under the playhead (panels made from the script remember
theirs).

Cost: the lines are worked out once into a table of stretches (frame from,
frame to, line), redone on edits (clips_changed) or when the script /
transcripts change (seen by the draw). The frame hook only checks "still
inside the same stretch?" and returns; on leaving it, it looks the new line
up and redraws the script area.
"""

import bisect

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import project_defaults as defaults, voice as cfg
from ...core import handlers
from ...core.theme import _color
from ...timeline import clips, events, tracks
from . import script_link, takes

_table = {"key": None, "starts": [], "rows": [], "dirty": True}
_now = {"line": None, "lo": 0, "hi": -1, "scene": None}
_handles = []


def _stretches(scene, text):
    """[(from, to, line)] sorted, not overlapping: panels' lines, then heard
    lines over voice clips (they win)."""
    from ..storyboard import panels
    out = []
    n = len(text.lines)
    for s in panels.all_panels(scene):
        li = s.plastron_panel.script_line
        if 0 <= li < n and s.plastron_panel.script_text:
            out.append((clips.start(s), clips.end(s), li))
    heard, _unspoken = script_link.match(scene, text)
    if heard:
        starts = sorted((f, li) for li, f in heard.items())
        spans = []
        for i, track in enumerate(tracks.all_tracks(scene)):
            if track.kind == 'AUDIO':
                spans += [(clips.start(s), clips.end(s)) for s in clips.on_channel(scene, tracks.channel(i))
                          if takes.is_voice(s)]
        for a, b in spans:
            inside = [(f, li) for f, li in starts if a <= f < b]
            before = [li for f, li in starts if f < a]
            first = [(a, before[-1])] if before and (not inside or inside[0][0] > a) else []
            seq = first + inside
            for k, (f, li) in enumerate(seq):
                end = seq[k + 1][0] if k + 1 < len(seq) else b
                out.append((max(a, int(f)), end, li))
    if not out:
        return []
    # Voice stretches (added last) cover panel ones: paint them in order.
    edges = sorted({e for a, b, _l in out for e in (a, b)})
    rows = []
    for a, b in zip(edges, edges[1:]):
        line = None
        for x0, x1, li in out:                        # (last added wins)
            if x0 <= a < x1:
                line = li
        if rows and rows[-1][2] == line and rows[-1][1] == a:
            rows[-1] = (rows[-1][0], b, line)
        else:
            rows.append((a, b, line))
    return rows


def _rebuild(scene):
    text = bpy.data.texts.get(defaults.SCRIPT_TEXT_NAME)
    rows = _stretches(scene, text) if text else []
    _table.update(rows=rows, starts=[r[0] for r in rows], dirty=False,
                  key=script_link._cache["key"])
    _now.update(hi=-1)                                # (look the line up again)


def line_at(scene, frame=None):
    """The script line at the frame (default: the playhead), or None."""
    if _table["dirty"]:
        _rebuild(scene)
    frame = scene.frame_current if frame is None else frame
    i = bisect.bisect_right(_table["starts"], frame) - 1
    if i >= 0:
        a, b, line = _table["rows"][i]
        if a <= frame < b:
            return line
    return None


def _stretch(frame):
    """(lo, hi) of the stretch the frame is in (also gaps between rows)."""
    starts, rows = _table["starts"], _table["rows"]
    i = bisect.bisect_right(starts, frame) - 1
    if i >= 0 and frame < rows[i][1]:
        return rows[i][0], rows[i][1]
    lo = rows[i][1] if i >= 0 else -10**9
    hi = starts[i + 1] if i + 1 < len(starts) else 10**9
    return lo, hi


def _script_areas():
    wm = bpy.context.window_manager
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'TEXT_EDITOR' and area.spaces.active.text \
                    and area.spaces.active.text.name == defaults.SCRIPT_TEXT_NAME:
                yield area


def _show(line):
    for area in _script_areas():
        space = area.spaces.active
        if line is not None and cfg.SCRIPT_FOLLOW["scroll"]:
            top, rows = space.top, max(1, space.visible_lines)
            if not top <= line < top + rows - 1:
                space.top = max(0, line - rows // 3)
        area.tag_redraw()


def _script_frame(scene, *_args):
    # Per-frame hook: O(1) unless the playhead left the stretch of its line.
    f = scene.frame_current
    if not _table["dirty"] and scene.name == _now["scene"] and _now["lo"] <= f < _now["hi"]:
        return
    if _table["dirty"] or scene.name != _now["scene"]:
        _rebuild(scene)
    line = line_at(scene, f)
    lo, hi = _stretch(f)
    changed = line != _now["line"]
    _now.update(line=line, lo=lo, hi=hi, scene=scene.name)
    if changed:
        _show(line)


def invalidate(scene, **_info):
    _table["dirty"] = True
    _now["hi"] = -1
    if scene is not None:
        _script_frame(scene)


def draw():
    """A band behind the line at the playhead (all its wrapped rows)."""
    context = bpy.context
    space, region, scene = context.space_data, context.region, context.scene
    text = space.text if space else None
    if text is None or text.name != defaults.SCRIPT_TEXT_NAME or scene is None:
        return
    script_link.match(scene, text)                    # (keeps its cache up to date)
    if script_link._cache["key"] != _table["key"]:     # script or transcripts changed
        _table["dirty"] = True
        _now["hi"] = -1
    line = line_at(scene)
    _now["line"] = line
    if line is None or not 0 <= line < len(text.lines):
        return
    body = text.lines[line].body
    _x0, y_top = space.region_location_from_cursor(line, 0)
    _x1, y_end = space.region_location_from_cursor(line, len(body))
    row_h = space.font_size * context.preferences.system.ui_scale * cfg.SCRIPT_FOLLOW["row"]
    top = y_top + row_h * cfg.SCRIPT_FOLLOW["above"]
    bottom = y_end - row_h * cfg.SCRIPT_FOLLOW["below"]
    if bottom > region.height or top < 0:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.uniform_float("color", (*_color(cfg.SCRIPT_FOLLOW["color"])[:3], cfg.SCRIPT_FOLLOW["alpha"]))
    w = region.width
    tris = [(0, bottom), (w, bottom), (w, top), (0, bottom), (w, top), (0, top)]
    gpu.state.blend_set('ALPHA')
    batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    gpu.state.blend_set('NONE')


def _on_load(_scene):
    _table["dirty"] = True
    _now.update(hi=-1, scene=None, line=None)


def register():
    handlers.add("frame_change_post", _script_frame)
    handlers.on_load(_on_load)
    events.listen("clips_changed", invalidate)
    _handles.append(bpy.types.SpaceTextEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handles:
        bpy.types.SpaceTextEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
