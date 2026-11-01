"""Setting where the camera or a layer is at the start / end of a panel
(Motion panel: Start / End). The playhead jumps there and you drag on the
canvas:

  Camera: inside the frame = move it · near a corner = zoom · outside = rotate
          (Shift: 5° steps). The other end's frame shows in blue.
  Layer:  drag anywhere = move the active layer (or group).

Enter, double-click or Done keeps it; Esc, right-click or Cancel puts it back.
Canvas navigation keeps working.
"""

import math

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d

from ...config import motion as cfg, theme as theme_cfg
from ..canvas_edit import selection
from ..storyboard import canvas_frame, canvas_sync, canvas_view, panel_cache, tools as storyboard_tools
from . import camera, layer_motion

EDITING = "plastron_motion_editing"     # window manager key: "CAMERA START" etc. while setting


def editing(context=None):
    return (context or bpy.context).window_manager.get(EDITING, "")


def _canvas_under(context, event):
    """(region, region_3d, x, y) of the canvas under the mouse, or None."""
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW' and region.x <= event.mouse_x < region.x + region.width \
                    and region.y <= event.mouse_y < region.y + region.height:
                return region, area.spaces.active.region_3d, event.mouse_x - region.x, \
                    event.mouse_y - region.y
    return None


def _world(region, r3d, x, y):
    return region_2d_to_location_3d(region, r3d, (x, y), (0.0, 0.0, 0.0))


def _inside(pt, quad):
    sign = None
    for k in range(4):
        (ax, ay), (bx, by) = quad[k], quad[(k + 1) % 4]
        cross = (bx - ax) * (pt[1] - ay) - (by - ay) * (pt[0] - ax)
        if abs(cross) < 1e-9:
            continue
        if sign is None:
            sign = cross > 0
        elif sign != (cross > 0):
            return False
    return True


class PLASTRON_OT_motion_set(bpy.types.Operator):
    """Set where it is here: the playhead jumps there, then drag on the canvas"""
    bl_idname = "plastron.motion_set"
    bl_label = "Set Motion"
    bl_options = {'REGISTER'}

    target: bpy.props.EnumProperty(items=[('CAMERA', "Camera", ""), ('LAYER', "Layer", "")])
    end: bpy.props.EnumProperty(items=[('START', "Start", ""), ('END', "End", "")])

    @classmethod
    def description(cls, context, properties):
        what = "the camera frame" if properties.target == 'CAMERA' else "the active layer"
        return f"Set where {what} is at the panel's {properties.end.lower()}: drag on the canvas"

    @classmethod
    def poll(cls, context):
        return camera.shot(context.scene) is not None and not editing(context)

    def _strip(self, context):
        from ..storyboard.panels import all_panels
        return next((s for s in all_panels(context.scene) if s.name == self.strip_name), None)

    def _value(self, strip):
        if self.target == 'CAMERA':
            m = strip.plastron_motion
            return camera.as_tuple(m.start if self.end == 'START' else m.end)
        layer = strip.plastron_panel.material.plastron_stack.by_uid(self.uid)
        return tuple(layer.move_start if self.end == 'START' else layer.move_end)

    def _put(self, context, value):
        strip = self._strip(context)
        if strip is None:
            return
        if self.target == 'CAMERA':
            m = strip.plastron_motion
            camera.set_state(m.start if self.end == 'START' else m.end, value)
        else:
            layer = strip.plastron_panel.material.plastron_stack.by_uid(self.uid)
            if layer is not None:
                setattr(layer, "move_start" if self.end == 'START' else "move_end", value)
            layer_motion.refresh(context.scene)
        self._redraw(context)

    def _redraw(self, context):
        for area in context.window.screen.areas:
            if area.type in {'VIEW_3D', 'PROPERTIES'}:
                area.tag_redraw()

    def invoke(self, context, event):
        scene = context.scene
        strip = camera.shot(scene)
        self.strip_name = strip.name
        self.uid = ""
        if self.target == 'LAYER':
            layer = strip.plastron_panel.material.plastron_stack.active
            if layer is None:
                self.report({'INFO'}, "Pick a layer first")
                return {'CANCELLED'}
            self.uid = layer.uid
        scene.frame_current = clips_frame(strip, self.end)
        layer_motion.refresh(scene)
        self.original = self._value(strip)
        self.grab = None
        self.done = None
        context.window_manager[EDITING] = f"{self.target} {self.end}"
        what = "Camera" if self.target == 'CAMERA' else "Layer"
        hint = ("drag inside: move · corner: zoom · outside: rotate" if self.target == 'CAMERA'
                else "drag to move it")
        storyboard_tools.override_label[0] = f"{what} {self.end.lower()}: {hint} · Enter keeps, Esc cancels"
        canvas_frame.EXTRA_DRAW.append(self._draw)
        context.window_manager.modal_handler_add(self)
        self._redraw(context)
        return {'RUNNING_MODAL'}

    # --- drawing ------------------------------------------------------------------------
    def _frames(self, context):
        """(edited end's frame, other end's frame) in world corners."""
        strip = self._strip(context)
        base = canvas_view.camera_frame(context.scene)
        if strip is None or not base:
            return None, None
        m = strip.plastron_motion
        mine, other = (m.start, m.end) if self.end == 'START' else (m.end, m.start)
        return camera.corners(base, camera.as_tuple(mine)), camera.corners(base, camera.as_tuple(other))

    def _draw(self, context):
        try:
            strip = self._strip(context)
        except ReferenceError:
            return
        if strip is None:
            return
        if self.target == 'CAMERA':
            mine, other = self._frames(context)
            if mine:
                canvas_frame.draw_quad(context, other, theme_cfg.CANVAS["frame_other"], 1.5)
                canvas_frame.draw_quad(context, mine, theme_cfg.CANVAS["frame_edit"], 2.5)
            return
        layer = strip.plastron_panel.material.plastron_stack.by_uid(self.uid)
        if layer is None:
            return
        # The layer's path: start -> end, from the middle of the canvas.
        st = strip.plastron_panel.material.plastron_stack
        sw, sh = canvas_sync.sheet_size()
        a, b = [((v[0] / st.width) * sw, -0.03, (v[1] / st.height) * sh)
                for v in (layer.move_start, layer.move_end)]
        from mathutils import Vector
        pts = [location_3d_to_region_2d(context.region, context.region_data, Vector(p)) for p in (a, b)]
        if None in pts:
            return
        d = 6
        for p in pts:
            _draw_screen_line(context, [(p.x - d, p.y - d), (p.x + d, p.y - d), (p.x + d, p.y + d),
                                        (p.x - d, p.y + d), (p.x - d, p.y - d)],
                              theme_cfg.CANVAS["motion_path"])
        _draw_screen_line(context, [(pts[0].x, pts[0].y), (pts[1].x, pts[1].y)], theme_cfg.CANVAS["motion_path"])

    # --- dragging -----------------------------------------------------------------------
    def _press(self, context, event, hit):
        region, r3d, x, y = hit
        self.drag_view = (region, r3d)
        self.start_value = self._value(self._strip(context))
        self.start_world = _world(region, r3d, x, y)
        if self.target == 'LAYER':
            self.grab = 'MOVE'
            return
        mine, _other = self._frames(context)
        screen = [location_3d_to_region_2d(region, r3d, c) for c in mine]
        self.centre = sum(mine, mine[0] * 0) / 4
        self.width = (canvas_view.camera_frame(context.scene)[0] - canvas_view.camera_frame(context.scene)[3]).length
        if any(p is not None and (p.x - x) ** 2 + (p.y - y) ** 2 <= cfg.CORNER_GRAB_PX ** 2 for p in screen):
            self.grab = 'ZOOM'
        elif None not in screen and _inside((x, y), [(p.x, p.y) for p in screen]):
            self.grab = 'MOVE'
        else:
            self.grab = 'ROTATE'

    def _drag(self, context, event):
        region, r3d = self.drag_view
        p = _world(region, r3d, event.mouse_x - region.x, event.mouse_y - region.y)
        p0, v0 = self.start_world, self.start_value
        if self.target == 'LAYER':
            st = self._strip(context).plastron_panel.material.plastron_stack
            sw, sh = canvas_sync.sheet_size()
            self._put(context, (v0[0] + (p.x - p0.x) / sw * st.width, v0[1] + (p.z - p0.z) / sh * st.height))
            return
        x, y, zoom, rot = v0
        c = self.centre
        if self.grab == 'MOVE':
            x += (p.x - p0.x) / self.width * 100
            y += (p.z - p0.z) / self.width * 100
        elif self.grab == 'ZOOM':
            d0 = math.hypot(p0.x - c.x, p0.z - c.z)
            d1 = math.hypot(p.x - c.x, p.z - c.z)
            zoom = min(cfg.ZOOM_RANGE[1], max(cfg.ZOOM_RANGE[0], zoom * d0 / max(d1, 1e-6)))
        else:
            turn = math.atan2(p.z - c.z, p.x - c.x) - math.atan2(p0.z - c.z, p0.x - c.x)
            turn = (turn + math.pi) % math.tau - math.pi
            rot += turn
            if event.shift:
                step = math.radians(cfg.ROTATE_STEP)
                rot = round(rot / step) * step
            limit = math.radians(cfg.ROTATION_LIMIT)
            rot = min(limit, max(-limit, rot))
        self._put(context, (x, y, zoom, rot))

    # --- finishing ----------------------------------------------------------------------
    def _end(self, context, keep):
        if self._draw in canvas_frame.EXTRA_DRAW:
            canvas_frame.EXTRA_DRAW.remove(self._draw)
        storyboard_tools.override_label[0] = None
        context.window_manager[EDITING] = ""
        strip = self._strip(context)
        if not keep:
            self._put(context, self.original)
        elif strip is not None and self._value(strip) != self.original:
            panel_cache.request(strip.plastron_panel.material)
            what = "Camera" if self.target == 'CAMERA' else "Layer"
            try:
                bpy.ops.ed.undo_push(message=f"{what} {self.end.lower()} position")
            except RuntimeError:
                pass
        self._redraw(context)

    def modal(self, context, event):
        t, v = event.type, event.value
        if self.done is None and context.window_manager.get(EDITING) in ("DONE", "CANCEL"):
            self.done = context.window_manager[EDITING] == "DONE"
        if self.done is not None:
            self._end(context, self.done)
            return {'FINISHED'} if self.done else {'CANCELLED'}
        if v == 'PRESS' and t in {'RET', 'NUMPAD_ENTER'}:
            self._end(context, True)
            return {'FINISHED'}
        if v == 'PRESS' and t == 'ESC':
            self._end(context, False)
            return {'CANCELLED'}
        hit = _canvas_under(context, event)
        if self.grab is None and (hit is None or selection.is_navigation(event)):
            return {'PASS_THROUGH'}
        if t == 'MOUSEMOVE':
            if self.grab is not None:
                self._drag(context, event)
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'DOUBLE_CLICK':
            self._end(context, True)
            return {'FINISHED'}
        if t == 'LEFTMOUSE' and v == 'PRESS':
            self._press(context, event, hit)
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'RELEASE':
            self.grab = None
            return {'RUNNING_MODAL'}
        if v == 'PRESS' and t == 'RIGHTMOUSE':
            self._end(context, False)
            return {'CANCELLED'}
        return {'PASS_THROUGH'} if t not in {'LEFTMOUSE', 'RIGHTMOUSE'} else {'RUNNING_MODAL'}


def _draw_screen_line(context, pts, color):
    import gpu
    from gpu_extras.batch import batch_for_shader
    from ...core.theme import _color
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.uniform_float("viewportSize", (context.region.width, context.region.height))
    shader.uniform_float("lineWidth", 2.0)
    shader.uniform_float("color", _color(color))
    gpu.state.blend_set('ALPHA')
    batch_for_shader(shader, 'LINE_STRIP', {"pos": [(x, y, 0) for x, y in pts]}).draw(shader)


def clips_frame(strip, end):
    from ...timeline import clips
    return clips.start(strip) if end == 'START' else clips.end(strip) - 1


class PLASTRON_OT_motion_done(bpy.types.Operator):
    """Finish setting the position"""
    bl_idname = "plastron.motion_done"
    bl_label = "Done"
    bl_options = {'INTERNAL'}
    keep: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        if editing(context) and editing(context) not in ("DONE", "CANCEL"):
            context.window_manager[EDITING] = "DONE" if self.keep else "CANCEL"
        return {'FINISHED'}


classes = (PLASTRON_OT_motion_set, PLASTRON_OT_motion_done)
