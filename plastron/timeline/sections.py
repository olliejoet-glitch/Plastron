"""Video above, the Script lane, audio below, nothing else (Ollie: "I don't want tracks there,
other than the default ones, unless I add those myself. A clear line, and
ideally colour separation, between audio tracks on the bottom and video
tracks on the top").

Blender's timeline always has 128 channels; the ones that aren't tracks
are covered over (the timeline and its channel column), so only tracks show.
The video tracks' rows and headers get one tint, the audio tracks' another,
with a line between them. Tracks are always kept in order (tracks.add:
video on top, audio below). Look: SECTIONS in config/timeline.py.
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..config import timeline as cfg
from ..core.theme import _color
from . import tracks

_handles = []


def _rgba(spec):
    """'#rrggbb' / palette name, or (that, alpha)."""
    if isinstance(spec, (tuple, list)):
        c = list(_color(spec[0]))
        c[3] = spec[1]
        return c
    return list(_color(spec))


def spans(scene):
    """{'VIDEO': (first channel, last channel), 'AUDIO': ...} and the top channel."""
    out, top = {}, 0
    for i, track in tracks.visible_tracks(scene):       # (hidden ones are parked on top: covered)
        ch = tracks.channel(i)
        lo, hi = out.get(track.kind, (ch, ch))
        out[track.kind] = (min(lo, ch), max(hi, ch))
        top = max(top, ch)
    return out, top


def _rect(shader, x0, y0, x1, y1, colour):
    shader.uniform_float("color", colour)
    batch_for_shader(shader, 'TRI_FAN', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(shader)


def _ok(context):
    scene = context.scene
    if scene is None or not hasattr(scene, "plastron_timeline") or not tracks.all_tracks(scene):
        return None
    from ..core.views import is_timeline
    if not is_timeline(context.space_data):
        return None
    return scene


def draw_rows():
    """Under the clips (view space: x = frames, y = channels)."""
    context = bpy.context
    scene = _ok(context)
    if scene is None:
        return
    region = context.region
    v2d = region.view2d
    x0 = v2d.region_to_view(0, 0)[0]
    x1 = v2d.region_to_view(region.width, 0)[0]
    _y0, ytop = v2d.region_to_view(0, region.height)
    found, top = spans(scene)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    for kind, key in KIND_TINTS:
        if kind in found:
            lo, hi = found[kind]
            _rect(shader, x0, lo, x1, hi + 1, _rgba(cfg.SECTIONS[key]))
    if cfg.SECTIONS["hide_empty_channels"] and ytop > top + 1:
        _rect(shader, x0, top + 1, x1, ytop + 1, _rgba(cfg.SECTIONS["empty_timeline"]))
    gpu.state.blend_set('NONE')


KIND_TINTS = (('VIDEO', "video_tint"), ('SCRIPT', "script_tint"), ('AUDIO', "audio_tint"))


def _line_ys(scene, to_region):
    """Pixel y of the lines between sections (audio | script | video)."""
    found, _top = spans(scene)
    out = []
    for lower in ('AUDIO', 'SCRIPT'):
        if lower in found and any(k in found for k in ('SCRIPT', 'VIDEO') if k != lower):
            out.append(to_region(found[lower][1] + 1))
    return out


def draw_line():
    """Over the clips: the line between the audio and video tracks."""
    context = bpy.context
    scene = _ok(context)
    if scene is None:
        return
    region = context.region
    w = cfg.SECTIONS["line_px"] * context.preferences.system.ui_scale
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    for y in _line_ys(scene, lambda ch: region.view2d.view_to_region(0, ch, clip=False)[1]):
        if 0 <= y <= region.height:
            _rect(shader, 0, y - w / 2, region.width, y + w / 2, _rgba(cfg.SECTIONS["line"]))
    gpu.state.blend_set('NONE')


def draw_headers():
    """The channel column: empty channels covered, sections tinted, the line."""
    context = bpy.context
    scene = _ok(context)
    if scene is None:
        return
    from .track_headers import row_span
    area, region = context.area, context.region
    found, top = spans(scene)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    if cfg.SECTIONS["hide_empty_channels"]:
        y = row_span(area, region, top + 1)[0]
        if y < region.height:
            _rect(shader, 0, max(0, y), region.width, region.height, _rgba(cfg.SECTIONS["empty_headers"]))
    for kind, key in KIND_TINTS:
        if kind in found:
            lo, hi = found[kind]
            y0, _y = row_span(area, region, lo)
            _y, y1 = row_span(area, region, hi)
            _rect(shader, 0, y0, region.width, y1, _rgba(cfg.SECTIONS[key]))
    w = cfg.SECTIONS["line_px"] * context.preferences.system.ui_scale
    for y in _line_ys(scene, lambda ch: row_span(area, region, ch)[0]):
        if 0 <= y <= region.height:
            _rect(shader, 0, y - w / 2, region.width, y + w / 2, _rgba(cfg.SECTIONS["line"]))
    gpu.state.blend_set('NONE')


def register():
    st = bpy.types.SpaceSequenceEditor
    _handles.append(('WINDOW', st.draw_handler_add(draw_rows, (), 'WINDOW', 'POST_VIEW')))
    _handles.append(('WINDOW', st.draw_handler_add(draw_line, (), 'WINDOW', 'POST_PIXEL')))
    _handles.append(('CHANNELS', st.draw_handler_add(draw_headers, (), 'CHANNELS', 'POST_PIXEL')))


def unregister():
    for region_type, handle in _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(handle, region_type)
    _handles.clear()
