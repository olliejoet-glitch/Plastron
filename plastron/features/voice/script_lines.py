"""Script lines told apart at a glance (Ollie: "something that visually
separates the lines in the script a bit more, both a small space and an
alternating colour shift"). Every other script line (all its wrapped rows)
gets a faint band. The space itself is a real blank line kept between lines
(storyboard/script_panels.space_out: Blender's text view has no line
spacing); a thin strip where two lines touch is optional (gap_px).
Look and sizes: SCRIPT_LINES in config/voice.py.
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import project_defaults as defaults, voice as cfg
from ...core.theme import _color
from . import script_link

_handles = []


def bands(space, region, text, row_h):
    """[(line index, top, bottom, stripe)] for the script lines on screen,
    top to bottom; stripe: every other non-blank line. Pure screen maths
    from Blender's own line positions."""
    out = []
    n = 0
    lines = text.lines
    for i, line in enumerate(lines):
        if not line.body.strip():
            continue
        n += 1
        _x, y_top = space.region_location_from_cursor(i, 0)
        _x, y_end = space.region_location_from_cursor(i, len(line.body))
        top = y_top + row_h * cfg.SCRIPT_FOLLOW["above"]
        bottom = y_end - row_h * cfg.SCRIPT_FOLLOW["below"]
        if bottom > region.height:
            continue                                  # (above the view)
        if top < 0:
            break                                     # (below it: the rest are too)
        out.append([i, top, bottom, n % 2 == 0])
    for a, b in zip(out, out[1:]):                    # touching lines meet halfway (blank lines between stay clear)
        if a[0] + 1 == b[0]:
            mid = (a[2] + b[1]) / 2
            a[2], b[1] = mid, mid
    return [tuple(b) for b in out]


def draw():
    context = bpy.context
    space, region = context.space_data, context.region
    text = space.text if space else None
    if text is None or text.name != defaults.SCRIPT_TEXT_NAME or region is None:
        return
    if script_link.scrolling(context):               # (part-line offsets: marks would sit off)
        return
    look = cfg.SCRIPT_LINES
    row_h = space.font_size * context.preferences.system.ui_scale * cfg.SCRIPT_FOLLOW["row"]
    rows = bands(space, region, text, row_h)
    if not rows:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    w = region.width
    stripe = (*_color(look["stripe"])[:3], look["stripe_alpha"])
    gap = (*_color(look["gap_color"])[:3], look["gap_alpha"])
    half = look["gap_px"] * context.preferences.system.ui_scale / 2
    tris, gaps = [], []
    for k, (_i, top, bottom, striped) in enumerate(rows):
        if striped:
            tris += [(0, bottom), (w, bottom), (w, top), (0, bottom), (w, top), (0, top)]
        if k and half > 0:
            gaps += [(0, top - half), (w, top - half), (w, top + half),
                     (0, top - half), (w, top + half), (0, top + half)]
    if tris:
        shader.uniform_float("color", stripe)
        batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    if gaps:
        shader.uniform_float("color", gap)
        batch_for_shader(shader, 'TRIS', {"pos": gaps}).draw(shader)
    gpu.state.blend_set('NONE')


def register():
    _handles.append(bpy.types.SpaceTextEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handles:
        bpy.types.SpaceTextEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
