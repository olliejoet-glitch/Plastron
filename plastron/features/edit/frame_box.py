"""Edit mode: move / size / turn the selected clip in the preview by hand
(like the canvas's Ctrl+T box). A box around the clip's picture: drag inside
to move it, a corner to size it (keeps its shape), just outside to turn it
(Shift: 15° steps). Esc / right-click puts it back. Sizes: config/edit.py.

The preview's view is in project pixels, (0, 0) at the middle of the frame;
a clip's picture is its media size × its scale, around its offset.
"""

import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ...config import edit as cfg
from ...config import theme as theme_cfg
from ...core.theme import _color
from ...core.views import is_preview
from ...timeline import clips

B = cfg.FRAME_BOX


def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def boxed_clip(context):
    """The selected clip the box is for (shown in the picture now), or None."""
    scene = context.scene
    sed = scene.sequence_editor if scene else None
    strip = sed.active_strip if sed else None
    if strip is None or not strip.select or strip.type == 'SOUND' or not hasattr(strip, "transform"):
        return None
    if strip.mute or not (clips.start(strip) <= scene.frame_current < clips.end(strip)):
        return None
    if not getattr(strip, "elements", None) and strip.type != 'SCENE':
        return None
    return strip


def media_size(strip):
    if strip.type == 'SCENE' and strip.scene is not None:         # (an info window: its own frame)
        from .windows import window_size
        return window_size(strip.scene)
    e = strip.elements[0]
    w, h = e.orig_width, e.orig_height
    if not w or not h:
        r = bpy.context.scene.render
        w, h = r.resolution_x, r.resolution_y
    return w, h


def corners_view(strip):
    """The picture's four corners in view (project pixel) coordinates."""
    t = strip.transform
    w, h = media_size(strip)
    cr = getattr(strip, "crop", None)
    l, r, b, tp = (cr.min_x, cr.max_x, cr.min_y, cr.max_y) if cr is not None and strip.type != 'SCENE' else (0, 0, 0, 0)
    hw, hh = (w - l - r) * t.scale_x / 2, (h - b - tp) * t.scale_y / 2       # (what the crop leaves)
    c, s = math.cos(t.rotation), math.sin(t.rotation)
    sx, sy = (l - r) / 2 * t.scale_x, (b - tp) / 2 * t.scale_y               # (an uneven crop moves the middle)
    centre = Vector((t.offset_x + sx * c - sy * s, t.offset_y + sx * s + sy * c))
    return [centre + Vector((x * c - y * s, x * s + y * c)) for x, y in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]


def to_region(region, p):
    return Vector(region.view2d.view_to_region(p.x, p.y, clip=False))


def to_view(region, x, y):
    return Vector(region.view2d.region_to_view(x, y))


def _inside(pt, poly):
    sign = None
    for a, b in zip(poly, poly[1:] + poly[:1]):
        cross = (b.x - a.x) * (pt.y - a.y) - (b.y - a.y) * (pt.x - a.x)
        if abs(cross) < 1e-9:
            continue
        if sign is None:
            sign = cross > 0
        elif (cross > 0) != sign:
            return False
    return True


def hit(region, strip, x, y):
    """'SCALE' (a corner), 'MOVE' (inside), 'ROTATE' (just outside) or None."""
    pts = [to_region(region, p) for p in corners_view(strip)]
    m = Vector((x, y))
    if any((p - m).length <= _ui(B["handle_px"]) for p in pts):
        return 'SCALE'
    if _inside(m, pts):
        return 'MOVE'
    edges = zip(pts, pts[1:] + pts[:1])
    near = min(_seg_dist(m, a, b) for a, b in edges)
    return 'ROTATE' if near <= _ui(B["rotate_px"]) else None


def _seg_dist(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared == 0 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (a + ab * t - p).length


def draw():
    context = bpy.context
    if not is_preview(context.space_data) or context.region is None or context.region.type != 'PREVIEW':
        return
    strip = boxed_clip(context)
    if strip is None:
        return
    region = context.region
    pts = [to_region(region, p) for p in corners_view(strip)]
    colour = _color(theme_cfg.CANVAS["frame_edit"])
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 2.0)
    shader.uniform_float("color", colour)
    gpu.state.blend_set('ALPHA')
    batch_for_shader(shader, 'LINE_STRIP', {"pos": [(p.x, p.y) for p in pts + pts[:1]]}).draw(shader)
    fill = gpu.shader.from_builtin('UNIFORM_COLOR')
    fill.uniform_float("color", colour)
    r = _ui(B["handle_px"]) * 0.6
    for p in pts:
        batch_for_shader(fill, 'TRIS', {"pos": [(p.x - r, p.y - r), (p.x + r, p.y - r), (p.x + r, p.y + r),
                                                (p.x - r, p.y + r)]},
                         indices=[(0, 1, 2), (0, 2, 3)]).draw(fill)
    gpu.state.blend_set('NONE')


class PLASTRON_OT_preview_transform(bpy.types.Operator):
    """Drag the clip in the picture: inside moves it, a corner sizes it, just outside turns it"""
    bl_idname = "plastron.preview_transform"
    bl_label = "Move / Size / Turn Clip"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_preview(context.space_data) and context.region is not None

    def invoke(self, context, event):
        strip = boxed_clip(context)
        region = context.region
        if strip is None:
            return {'PASS_THROUGH'}
        self.mode = hit(region, strip, event.mouse_region_x, event.mouse_region_y)
        if self.mode is None:
            return {'PASS_THROUGH'}               # (Blender's click: select another clip)
        t = strip.transform
        self.strip_name = strip.name
        self.orig = (t.offset_x, t.offset_y, t.scale_x, t.scale_y, t.rotation)
        self.start = to_view(region, event.mouse_region_x, event.mouse_region_y)
        self.centre = Vector((t.offset_x, t.offset_y))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _strip(self, context):
        return context.scene.sequence_editor.strips_all.get(self.strip_name)

    def _apply(self, context, event):
        strip = self._strip(context)
        if strip is None:
            return
        t = strip.transform
        ox, oy, sx, sy, rot = self.orig
        now = to_view(context.region, event.mouse_region_x, event.mouse_region_y)
        if self.mode == 'MOVE':
            d = now - self.start
            t.offset_x, t.offset_y = ox + d.x, oy + d.y
        elif self.mode == 'SCALE':
            a, b = (self.start - self.centre).length, (now - self.centre).length
            k = max(0.01, b / a) if a > 1e-6 else 1.0
            t.scale_x, t.scale_y = sx * k, sy * k
        else:
            a0 = math.atan2(*(self.start - self.centre).yx)
            a1 = math.atan2(*(now - self.centre).yx)
            angle = rot + (a1 - a0)
            if event.shift:
                step = math.radians(B["rotate_snap_deg"])
                angle = round(angle / step) * step
            t.rotation = angle
        context.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._apply(context, event)
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            strip = self._strip(context)
            if strip is not None:
                t = strip.transform
                t.offset_x, t.offset_y, t.scale_x, t.scale_y, t.rotation = self.orig
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


classes = (PLASTRON_OT_preview_transform,)
_handle = [None]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle[0] = bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'PREVIEW', 'POST_PIXEL')


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handle[0], 'PREVIEW')
        _handle[0] = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
