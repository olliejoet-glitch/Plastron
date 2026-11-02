"""Camera controls: a small box in the corner of the canvas (Ollie: no
camera mode to enter, just controls you drag).

    Start | End    which end of the panel you're setting (clicking one moves
                   the playhead there; until you pick, it's the nearer end)
    pan pad        drag to move the camera (it follows your hand)
    Zoom strip     drag right to zoom in, left to zoom out
    Turn strip     drag to rotate slightly

Double-click the pad / a strip to put that part back. Each drag is one
undo step. The dots show where the camera is at this end (orange) and at
the other end (blue). Sizes and speeds: CAMERA_PAD in config/motion.py.
"""

import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import motion as cfg, theme as theme_cfg
from ...core.theme import _color
from ...timeline import clips
from . import camera, view_follow

P = cfg.CAMERA_PAD
_selected = {"end": None, "strip": ""}   # end picked for that panel (else the nearer end)


def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def pick(strip, end):
    _selected.update(end=end, strip=strip.name)


def current_end(scene, strip):
    if _selected["end"] and _selected["strip"] == strip.name:
        return _selected["end"]
    s, e = clips.start(strip), clips.end(strip) - 1
    return 'START' if scene.frame_current - s <= e - scene.frame_current else 'END'


def layout(region):
    """Rectangles (x0, y0, x1, y1) of each part, in region pixels."""
    m, size, strip_h, gap, btn_h = (_ui(P[k]) for k in ("margin", "size", "strip", "gap", "button"))
    # Clear of the canvas's own bottom-left: stacked upwards from the margin.
    x0, x1 = m, m + size
    y = m
    parts = {}
    parts["TURN"] = (x0, y, x1, y + strip_h)
    y += strip_h + gap
    parts["ZOOM"] = (x0, y, x1, y + strip_h)
    y += strip_h + gap
    parts["PAD"] = (x0, y, x1, y + size)
    y += size + gap
    parts["START"] = (x0, y, (x0 + x1) / 2 - gap / 2, y + btn_h)
    parts["END"] = ((x0 + x1) / 2 + gap / 2, y, x1, y + btn_h)
    y += btn_h
    parts["BOX"] = (x0 - gap, m - gap, x1 + gap, y + gap + _ui(14))
    return parts


def part_at(region, x, y):
    for name, (x0, y0, x1, y1) in layout(region).items():
        if name != "BOX" and x0 <= x <= x1 and y0 <= y <= y1:
            return name
    x0, y0, x1, y1 = layout(region)["BOX"]
    return "BOX" if x0 <= x <= x1 and y0 <= y <= y1 else None


def shown(context):
    from ...core.views import is_scene_view
    if is_scene_view(context.space_data):
        return False
    scene = context.scene
    return scene is not None and hasattr(scene, "plastron_timeline") and camera.shot(scene) is not None


# --- drawing ----------------------------------------------------------------------------

def _rect(shader, r, color):
    x0, y0, x1, y1 = r
    shader.uniform_float("color", color)
    batch_for_shader(shader, 'TRIS', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]},
                     indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)


def _dot(shader, x, y, r, color):
    pts = [(x + r * math.cos(a * math.tau / 12), y + r * math.sin(a * math.tau / 12)) for a in range(12)]
    shader.uniform_float("color", color)
    batch_for_shader(shader, 'TRI_FAN', {"pos": [(x, y)] + pts + [pts[0]]}).draw(shader)


def _text(text, r, color, size=10):
    x0, y0, x1, y1 = r
    blf.size(0, _ui(size))
    w, h = blf.dimensions(0, text)
    blf.position(0, (x0 + x1 - w) / 2, (y0 + y1 - h) / 2 + 1, 0)
    blf.color(0, *color)
    blf.draw(0, text)


def _pad_point(r, state):
    x0, y0, x1, y1 = r
    reach = P["pad_reach"]            # % of the frame width from the middle to the pad's edge
    fx = max(-1.0, min(1.0, state[0] / reach))
    fy = max(-1.0, min(1.0, state[1] / reach))
    return (x0 + x1) / 2 + fx * (x1 - x0) / 2, (y0 + y1) / 2 + fy * (y1 - y0) / 2


def _zoom_x(r, zoom):
    lo, hi = (math.log(z) for z in cfg.ZOOM_RANGE)
    f = (math.log(max(zoom, 1e-3)) - lo) / (hi - lo)
    return r[0] + max(0.0, min(1.0, f)) * (r[2] - r[0])


def _turn_x(r, rot):
    f = 0.5 + math.degrees(rot) / (2 * cfg.ROTATION_LIMIT)
    return r[0] + max(0.0, min(1.0, f)) * (r[2] - r[0])


def draw():
    context = bpy.context
    if not shown(context):
        return
    scene = context.scene
    strip = camera.shot(scene)
    m = strip.plastron_motion
    end = current_end(scene, strip)
    mine, other = (m.start, m.end) if end == 'START' else (m.end, m.start)
    mine, other = camera.as_tuple(mine), camera.as_tuple(other)
    parts = layout(context.region)
    c = theme_cfg.CANVAS
    orange, blue = _color(c["frame_edit"]), _color("blue")
    text, dim = _color("text"), _color("text_dim")
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    _rect(shader, parts["BOX"], _color(c["camera_pad_back"]))
    for name in ("PAD", "ZOOM", "TURN"):
        _rect(shader, parts[name], _color(c["camera_pad_well"]))
    for name in ("START", "END"):
        _rect(shader, parts[name], orange if name == end else _color("button"))
    # Pad: cross hairs, the other end (blue), this end (orange).
    x0, y0, x1, y1 = parts["PAD"]
    _rect(shader, ((x0 + x1) / 2 - 0.5, y0, (x0 + x1) / 2 + 0.5, y1), (*dim[:3], 0.4))
    _rect(shader, (x0, (y0 + y1) / 2 - 0.5, x1, (y0 + y1) / 2 + 0.5), (*dim[:3], 0.4))
    _dot(shader, *_pad_point(parts["PAD"], other), _ui(4), (*blue[:3], 0.9))
    _dot(shader, *_pad_point(parts["PAD"], mine), _ui(5), orange)
    for name, fx, value in (("ZOOM", _zoom_x, 2), ("TURN", _turn_x, 3)):
        r = parts[name]
        mid = fx(r, 1.0 if name == "ZOOM" else 0.0)
        _rect(shader, (mid - 0.5, r[1], mid + 0.5, r[3]), (*dim[:3], 0.5))
        for state, col, w in ((other, (*blue[:3], 0.9), 2), (mine, orange, 3)):
            x = fx(r, state[value])
            _rect(shader, (x - _ui(w) / 2, r[1], x + _ui(w) / 2, r[3]), col)
    _text("Start", parts["START"], text)
    _text("End", parts["END"], text)
    _text(f"Zoom {mine[2]:.2f}×", parts["ZOOM"], (*text[:3], 0.8), 9)
    _text(f"Turn {math.degrees(mine[3]):+.0f}°", parts["TURN"], (*text[:3], 0.8), 9)
    bx0, _by0, bx1, by1 = parts["BOX"]
    _text("Camera", (bx0, by1 - _ui(15), bx1, by1 - _ui(2)), dim, 10)
    gpu.state.blend_set('NONE')


# --- dragging ---------------------------------------------------------------------------

def reset_part(state, part):
    """Double-click: the pad centres the camera, the strips go back to 1× / 0°."""
    x, y, z, r = camera.as_tuple(state)
    camera.set_state(state, {"PAD": (0.0, 0.0, z, r), "ZOOM": (x, y, 1.0, r), "TURN": (x, y, z, 0.0)}[part])


class PLASTRON_OT_camera_pad(bpy.types.Operator):
    """Camera controls (corner of the canvas): drag the pad to move the camera,
    the strips to zoom / turn; Start / End picks which end of the panel"""
    bl_idname = "plastron.camera_pad"
    bl_label = "Camera Controls"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and \
            context.region is not None and context.region.type == 'WINDOW' and shown(context)

    def _state(self, strip):
        m = strip.plastron_motion
        return m.start if self.end == 'START' else m.end

    def _go_to_end(self, scene, strip):
        frame = clips.start(strip) if self.end == 'START' else clips.end(strip) - 1
        if scene.frame_current != frame:
            scene.frame_current = frame

    def invoke(self, context, event):
        region = context.region
        part = part_at(region, event.mouse_region_x, event.mouse_region_y)
        if part is None:
            from ..storyboard import stroke_guard
            stroke_guard.began()             # not on the box: a brush stroke starts
            return {'PASS_THROUGH'}
        scene = context.scene
        strip = camera.shot(scene)
        if part in {"START", "END"}:
            pick(strip, part)
            self.end = part
            self._go_to_end(scene, strip)
            context.area.tag_redraw()
            return {'FINISHED'}
        if part == "BOX":
            return {'FINISHED'}              # the box's edge: don't paint under it
        self.end = current_end(scene, strip)
        self._go_to_end(scene, strip)
        self.strip_name = strip.name
        self.part = part
        state = self._state(strip)
        self.start_value = camera.as_tuple(state)
        if event.value == 'DOUBLE_CLICK':     # put that part back
            reset_part(state, part)
            self.strip_name = strip.name
            self._grow(context)
            self._push(context)
            return {'FINISHED'}
        self.mouse = (event.mouse_x, event.mouse_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _strip(self, context):
        sed = context.scene.sequence_editor
        return sed.strips_all.get(self.strip_name) if sed else None

    def _apply(self, context, event):
        strip = self._strip(context)
        if strip is None:
            return
        dx, dy = event.mouse_x - self.mouse[0], event.mouse_y - self.mouse[1]
        slow = 0.25 if event.shift else 1.0          # Shift: fine control
        x, y, zoom, rot = self.start_value
        if self.part == "PAD":
            x += dx * P["pan_per_px"] * slow
            y += dy * P["pan_per_px"] * slow
        elif self.part == "ZOOM":
            zoom = min(cfg.ZOOM_RANGE[1], max(cfg.ZOOM_RANGE[0], zoom * math.exp(dx * P["zoom_per_px"] * slow)))
        else:
            limit = math.radians(cfg.ROTATION_LIMIT)
            rot = min(limit, max(-limit, rot + math.radians(dx * P["turn_per_px"] * slow)))
        camera.set_state(self._state(strip), (x, y, zoom, rot))
        view_follow.follow(context.scene)
        context.area.tag_redraw()

    def _grow(self, context):
        """The painting grows to fit the move now, while nothing is painting
        (the pen was on this box)."""
        strip = self._strip(context)
        if strip is not None:
            from . import canvas_fit
            canvas_fit.fit(strip)

    def _push(self, context):
        try:
            bpy.ops.ed.undo_push(message="Camera move")
        except RuntimeError:
            pass
        context.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._apply(context, event)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._grow(context)
            self._push(context)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            strip = self._strip(context)
            if strip is not None:
                camera.set_state(self._state(strip), self.start_value)
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class PLASTRON_OT_camera_end(bpy.types.Operator):
    """Set the camera at this end of the panel (moves the playhead there)"""
    bl_idname = "plastron.camera_end"
    bl_label = "Camera End"
    bl_options = {'INTERNAL'}
    end: bpy.props.EnumProperty(items=[('START', "Start", ""), ('END', "End", "")])

    @classmethod
    def poll(cls, context):
        return camera.shot(context.scene) is not None

    def execute(self, context):
        scene = context.scene
        strip = camera.shot(scene)
        pick(strip, self.end)
        frame = clips.start(strip) if self.end == 'START' else clips.end(strip) - 1
        scene.frame_current = frame
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


classes = (PLASTRON_OT_camera_pad, PLASTRON_OT_camera_end)
_handle = None


def register():
    global _handle
    _handle = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle
    if _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
