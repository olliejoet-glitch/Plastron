"""Draws the camera frame on the canvas and dims everything outside it
(Clean View, F: hides it instead).

A screen overlay only: it runs when the canvas redraws, never touches scene
data, and costs a few triangles. Colours: CANVAS in config/theme.py.

Hooks: FRAME_PROVIDERS - func(context) -> 4 world-space corners (or None)
of the frame at the playhead (camera moves, features/motion); the first
answer wins, else the scene camera's frame. EXTRA_DRAW - func(context)
drawn on top (e.g. the frame being edited).
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
FRAME_PROVIDERS = []
EXTRA_DRAW = []


def shown_frame(context):
    """World-space corners of the frame shown at the playhead."""
    for provider in FRAME_PROVIDERS:
        corners = provider(context)
        if corners:
            return corners
    return camera_frame(context.scene)


def clean_view(context=None):
    return bool(getattr((context or bpy.context).window_manager, "plastron_clean_view", False))


def _frame_on_screen(context):
    corners = shown_frame(context)
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
    outside = "clean_view" if clean_view(context) else "outside_frame"
    shader.uniform_float("color", _color(theme_cfg.CANVAS[outside]))
    batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=tris).draw(shader)

    shader.uniform_float("color", _color(theme_cfg.CANVAS["frame_line"]))
    line = [(p.x, p.y) for p in pts] + [(pts[0].x, pts[0].y)]
    batch_for_shader(shader, 'LINE_STRIP', {"pos": line}).draw(shader)
    for func in EXTRA_DRAW:
        func(context)
    gpu.state.blend_set('NONE')


def draw_quad(context, corners, color, width=1.0):
    """Outline of world-space corners on the canvas (for EXTRA_DRAW)."""
    pts = [location_3d_to_region_2d(context.region, context.region_data, c) for c in corners]
    if any(p is None for p in pts):
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.uniform_float("viewportSize", (context.region.width, context.region.height))
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", _color(color) if isinstance(color, str) else color)
    gpu.state.blend_set('ALPHA')
    line = [(p.x, p.y, 0) for p in pts] + [(pts[0].x, pts[0].y, 0)]
    batch_for_shader(shader, 'LINE_STRIP', {"pos": line}).draw(shader)


class PLASTRON_OT_clean_view(bpy.types.Operator):
    """Clean view: hide everything outside the camera frame (F)"""
    bl_idname = "plastron.clean_view"
    bl_label = "Clean View"

    def execute(self, context):
        wm = context.window_manager
        wm.plastron_clean_view = not wm.plastron_clean_view
        return {'FINISHED'}


def _redraw(_self, context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def register():
    global _handle
    bpy.types.WindowManager.plastron_clean_view = bpy.props.BoolProperty(
        name="Clean View", description="Hide everything outside the camera frame (F)",
        update=_redraw)
    bpy.utils.register_class(PLASTRON_OT_clean_view)
    _handle = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle
    if _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    bpy.utils.unregister_class(PLASTRON_OT_clean_view)
    del bpy.types.WindowManager.plastron_clean_view
    FRAME_PROVIDERS.clear()
    EXTRA_DRAW.clear()
