"""Track headers: Plastron's ripple / solo / volume controls, drawn in the
timeline's channel column next to Blender's own name, mute and lock.

Shared component: every mode's timeline uses it. Layout and colours are in
config/timeline.py. Clicks are handled by plastron.track_header_click
(timeline/ops.py), using widgets() below for hit-testing.
"""

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..config import timeline as cfg
from ..core.theme import _color
from . import tracks

_handle = None


def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def row_span(region, ch):
    """(bottom, top) pixel y of a channel row in a channel-column region."""
    v2d = region.view2d
    return v2d.view_to_region(0, ch, clip=False)[1], v2d.view_to_region(0, ch + 1, clip=False)[1]


def widgets(region, scene):
    """[(track index, widget id, (x0, y0, x1, y1))] for every visible widget."""
    out = []
    size = _ui(cfg.HEADER_TOGGLE_PX)
    for i, track in enumerate(tracks.all_tracks(scene)):
        y0, y1 = row_span(region, tracks.channel(i))
        if y1 < 0 or y0 > region.height:
            continue
        h = min(size, (y1 - y0) * 0.8)
        yc = (y0 + y1) / 2
        x = region.width - _ui(cfg.HEADER_NATIVE_BUTTONS_PX)
        for wid, _label, kinds in reversed(cfg.HEADER_WIDGETS):
            if track.kind not in kinds:
                continue
            w = _ui(cfg.HEADER_VOLUME_PX) if wid == "VOLUME" else h
            out.append((i, wid, (x - w, yc - h / 2, x, yc + h / 2)))
            x -= w + _ui(cfg.HEADER_GAP_PX)
    return out


def hit(region, scene, x, y):
    for i, wid, (x0, y0, x1, y1) in widgets(region, scene):
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i, wid, (x0, y0, x1, y1)
    return None


def row_at(region, scene, y):
    """Track index of the row at pixel y, or None."""
    ch = int(region.view2d.region_to_view(0, y)[1])
    return tracks.index_of_channel(scene, ch)


def _rect(shader, x0, y0, x1, y1, colour):
    shader.uniform_float("color", colour)
    batch_for_shader(shader, 'TRI_FAN', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(shader)


def _c(name):
    value = cfg.HEADER_COLORS[name]
    return _color(value)


def draw():
    context = bpy.context
    scene = context.scene
    region = context.region
    if scene is None or not hasattr(scene, "plastron_timeline"):
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    active = tracks.active(scene)
    labels = {wid: label for wid, label, _k in cfg.HEADER_WIDGETS}

    for i, track in enumerate(tracks.all_tracks(scene)):
        y0, y1 = row_span(region, tracks.channel(i))
        marker = "active_track" if active and track.uid == active.uid else (
            "video_track" if track.kind == 'VIDEO' else "audio_track")
        _rect(shader, 0, y0 + 1, _ui(3), y1 - 1, _c(marker))

    font = 0
    blf.size(font, _ui(11))
    for i, wid, (x0, y0, x1, y1) in widgets(region, scene):
        track = scene.plastron_timeline.tracks[i]
        if wid == "VOLUME":
            _rect(shader, x0, y0, x1, y1, _c("volume_back"))
            fill = min(track.volume / 2.0, 1.0)
            _rect(shader, x0, y0, x0 + (x1 - x0) * fill, y1, _c("volume_fill"))
            text = f"{round(track.volume * 100)}%"
        else:
            on = getattr(track, wid.lower())
            _rect(shader, x0, y0, x1, y1, _c("toggle_on" if on else "toggle_off"))
            text = labels[wid]
        tw, th = blf.dimensions(font, text)
        blf.position(font, (x0 + x1 - tw) / 2, (y0 + y1 - th) / 2 + 1, 0)
        blf.color(font, *_c("toggle_text"))
        blf.draw(font, text)
    gpu.state.blend_set('NONE')


def register():
    global _handle
    _handle = bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'CHANNELS', 'POST_PIXEL')


def unregister():
    global _handle
    if _handle:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handle, 'CHANNELS')
        _handle = None
