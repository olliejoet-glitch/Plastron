"""Draws the camera frame on the canvas and dims everything outside it.

A screen overlay only: it runs when the canvas redraws, never touches scene
data, and costs a few triangles. Colours: CANVAS in config/theme.py.
"""

import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from ...config import theme as theme_cfg
from ...core.theme import _color
from .canvas_view import camera_frame

_handle = None


def _frame_on_screen(context):
    corners = camera_frame(context.scene)
    if not corners:
        return None
    pts = [location_3d_to_region_2d(context.region, context.region_data, c) for c in corners]
    return None if any(p is None for p in pts) else pts


def draw():
    context = bpy.context
    pts = _frame_on_screen(context)
    if pts is None:
        return
    w, h = context.region.width, context.region.height
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')

    # Dim outside: a rectangle bigger than screen and frame, with the frame as a hole.
    xs, ys = [0, w] + [p.x for p in pts], [0, h] + [p.y for p in pts]
    x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    outer = [Vector((x0, y0, 0)), Vector((x1, y0, 0)), Vector((x1, y1, 0)), Vector((x0, y1, 0))]
    inner = [Vector((p.x, p.y, 0)) for p in pts]
    verts = [(v.x, v.y) for v in outer + inner]
    tris = tessellate_polygon([outer, inner])
    shader.uniform_float("color", _color(theme_cfg.CANVAS["outside_frame"]))
    batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=tris).draw(shader)

    shader.uniform_float("color", _color(theme_cfg.CANVAS["frame_line"]))
    line = [(p.x, p.y) for p in pts] + [(pts[0].x, pts[0].y)]
    batch_for_shader(shader, 'LINE_STRIP', {"pos": line}).draw(shader)
    gpu.state.blend_set('NONE')


def register():
    global _handle
    _handle = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle
    if _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
