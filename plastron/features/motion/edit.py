"""Setting where the camera or a layer is at the start / end of a panel:
a transform box on the canvas (C for the camera, or Start / End in the
Motion panel). The playhead jumps to that end of the panel.

  Camera: a box on the frame. Drag inside = move the camera · a corner or
          side handle = zoom (out = see more) · outside = rotate (Shift: 5°
          steps). In Camera View the frame stays still and the drawing moves
          behind it, as if you were moving the camera. The other end's frame
          shows in blue.
  Layer:  a box around the active layer's (or group's) drawing: drag to
          move it. The other end's position shows in blue.

Tab swaps between Start and End. Enter, double-click, C or Done keeps it;
Esc, right-click or Cancel puts it back. Canvas navigation keeps working.
"""

import math

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from ...config import motion as cfg, theme as theme_cfg
from ...layers import layer_trees
from ..canvas_edit import selection
from ..storyboard import canvas_frame, canvas_sync, canvas_view, panel_cache, tools as storyboard_tools
from . import camera, layer_motion, view_follow

BOX_MARGIN = 24        # canvas pixels around a layer's drawing (room for the handles)
EDITING = "plastron_motion_editing"     # window manager key: "CAMERA START" etc. while setting


def editing(context=None):
    return (context or bpy.context).window_manager.get(EDITING, "")


def _canvas_under(context, event):
    """(region, space, region_3d, x, y) of the canvas under the mouse, or None."""
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW' and region.x <= event.mouse_x < region.x + region.width \
                    and region.y <= event.mouse_y < region.y + region.height:
                space = area.spaces.active
                return region, space, space.region_3d, event.mouse_x - region.x, event.mouse_y - region.y
    return None


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


def _handles(corners):
    """Corners, then side middles."""
    return list(corners) + [(corners[k] + corners[(k + 1) % 4]) / 2 for k in range(4)]


def layer_bounds(stack, layer):
    """Pixel box (x0, y0, x1, y1) of what a layer (or group) has drawn."""
    uids = [layer.uid]
    if layer.layer_type == "GROUP":
        from ...layers.stack import subtree_uids
        uids = subtree_uids(stack, layer)
    box = None
    for uid in uids:
        l = stack.by_uid(uid)
        if l is None or l.layer_type != "PAINT" or l.paint_image is None:
            if l is not None and l.layer_type in {"FILL"}:
                return (0, 0, stack.width, stack.height)
            continue
        img = l.paint_image
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        alpha = px[3::4].reshape(h, w) > 0.02
        rows, cols = np.nonzero(alpha.any(1))[0], np.nonzero(alpha.any(0))[0]
        if len(rows) == 0:
            continue
        b = (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        return (0, 0, stack.width, stack.height)
    m = BOX_MARGIN
    return (box[0] - m, box[1] - m, box[2] + m, box[3] + m)


class PLASTRON_OT_motion_set(bpy.types.Operator):
    """Set where it is at the panel's start / end with a transform box on the canvas"""
    bl_idname = "plastron.motion_set"
    bl_label = "Set Motion"
    bl_options = {'REGISTER'}

    target: bpy.props.EnumProperty(items=[('CAMERA', "Camera", ""), ('LAYER', "Layer", "")])
    end: bpy.props.EnumProperty(items=[('START', "Start", ""), ('END', "End", ""),
                                       ('NEAREST', "Nearest", "The end nearer the playhead")])

    @classmethod
    def description(cls, context, properties):
        what = "the camera" if properties.target == 'CAMERA' else "the active layer"
        when = "the end nearer the playhead" if properties.end == 'NEAREST' else \
            f"the panel's {properties.end.lower()}"
        return f"Set where {what} is at {when}: a transform box on the canvas"

    @classmethod
    def poll(cls, context):
        return camera.shot(context.scene) is not None and not editing(context)

    # --- the thing being set --------------------------------------------------------------
    def _strip(self, context):
        sed = context.scene.sequence_editor
        return sed.strips_all.get(self.strip_name) if sed else None

    def _layer(self, strip):
        return strip.plastron_panel.material.plastron_stack.by_uid(self.uid)

    def _value(self, strip, end=None):
        end = end or self.end
        if self.target == 'CAMERA':
            m = strip.plastron_motion
            return camera.as_tuple(m.start if end == 'START' else m.end)
        layer = self._layer(strip)
        return tuple(layer.move_start if end == 'START' else layer.move_end)

    def _put(self, context, value, end=None):
        end = end or self.end
        strip = self._strip(context)
        if strip is None:
            return
        if self.target == 'CAMERA':
            m = strip.plastron_motion
            camera.set_state(m.start if end == 'START' else m.end, value)
        else:
            layer = self._layer(strip)
            if layer is not None:
                setattr(layer, "move_start" if end == 'START' else "move_end", value)
            layer_motion.refresh(context.scene)
        view_follow.follow(context.scene)
        self._redraw(context)

    def _redraw(self, context):
        for area in context.window.screen.areas:
            if area.type in {'VIEW_3D', 'PROPERTIES'}:
                area.tag_redraw()

    def _go_to_end(self, context):
        from ...timeline import clips
        strip = self._strip(context)
        scene = context.scene
        scene.frame_current = clips.start(strip) if self.end == 'START' else clips.end(strip) - 1
        layer_motion.refresh(scene)
        view_follow.follow(scene)
        context.window_manager[EDITING] = f"{self.target} {self.end}"
        what = "Camera" if self.target == 'CAMERA' else "Layer"
        hint = ("drag inside: move · handles: zoom · outside: rotate" if self.target == 'CAMERA'
                else "drag to move it")
        storyboard_tools.override_label[0] = \
            f"{what} {self.end.lower()}: {hint} · Tab: {'end' if self.end == 'START' else 'start'} · Enter keeps"

    def invoke(self, context, event):
        from ...timeline import clips
        scene = context.scene
        strip = camera.shot(scene)
        self.strip_name = strip.name
        self.uid = ""
        if self.target == 'LAYER':
            st = strip.plastron_panel.material.plastron_stack
            layer = st.active
            if layer is None:
                self.report({'INFO'}, "Pick a layer first")
                return {'CANCELLED'}
            self.uid = layer.uid
            self.bounds = layer_bounds(st, layer)
        if self.end == 'NEAREST':
            s, e = clips.start(strip), clips.end(strip) - 1
            self.end = 'START' if scene.frame_current - s <= e - scene.frame_current else 'END'
        self.original = {end: self._value(strip, end) for end in ('START', 'END')}
        self.grab = None
        self.done = None
        self._go_to_end(context)
        canvas_frame.EXTRA_DRAW.append(self._draw)
        context.window_manager.modal_handler_add(self)
        self._redraw(context)
        return {'RUNNING_MODAL'}

    # --- where things are -------------------------------------------------------------------
    def _camera_frames(self, context):
        """(edited end's frame, other end's frame), world corners."""
        strip = self._strip(context)
        base = canvas_view.camera_frame(context.scene)
        if strip is None or not base:
            return None, None
        m = strip.plastron_motion
        mine, other = (m.start, m.end) if self.end == 'START' else (m.end, m.start)
        return camera.corners(base, camera.as_tuple(mine)), camera.corners(base, camera.as_tuple(other))

    def _layer_boxes(self, context):
        """(box now, box at the other end), world corners."""
        strip = self._strip(context)
        layer = self._layer(strip) if strip else None
        if layer is None:
            return None, None
        st = strip.plastron_panel.material.plastron_stack
        sw, sh = canvas_sync.sheet_size()
        shown = layer_trees.shown_offset(layer, st)
        other = layer.move_end if self.end == 'START' else layer.move_start
        x0, y0, x1, y1 = self.bounds
        boxes = []
        for dx, dy in (shown, (shown[0] - layer.move_now[0] + other[0], shown[1] - layer.move_now[1] + other[1])):
            boxes.append([Vector((((px + dx) / st.width - 0.5) * sw, -0.03, ((py + dy) / st.height - 0.5) * sh))
                          for px, py in ((x1, y1), (x1, y0), (x0, y0), (x0, y1))])
        return boxes

    def _boxes(self, context):
        return self._camera_frames(context) if self.target == 'CAMERA' else self._layer_boxes(context)

    # --- drawing ------------------------------------------------------------------------------
    def _draw(self, context):
        try:
            mine, other = self._boxes(context)
        except ReferenceError:
            return
        if not mine:
            return
        canvas_frame.draw_quad(context, other, theme_cfg.CANVAS["frame_other"], 1.5)
        canvas_frame.draw_quad(context, mine, theme_cfg.CANVAS["frame_edit"], 2.0)
        pts = [location_3d_to_region_2d(context.region, context.region_data, p)
               for p in (_handles(mine) if self.target == 'CAMERA' else mine)]
        d = cfg.HANDLE_PX
        for p in pts:
            if p is not None:
                _fill_square(context, p.x, p.y, d, theme_cfg.CANVAS["frame_edit"])
        if self.target == 'LAYER':
            a, b = (sum(box, Vector()) / 4 for box in (mine, other))
            canvas_frame.draw_quad(context, [a, b, b, a], theme_cfg.CANVAS["motion_path"], 1.5)

    # --- dragging -------------------------------------------------------------------------
    def _home(self, hit_view, x, y):
        """Mouse -> the canvas as it is with no camera view (stays the same
        while the view follows the camera, so drags stay steady)."""
        region, space, r3d = hit_view
        world = canvas_view.screen_to_world(region, space, r3d, x, y)
        frame = view_follow.base()
        return view_follow.backward(world, view_follow.applied(r3d), *frame) if frame else world

    def _press(self, context, hit):
        region, space, r3d, x, y = hit
        self.view = (region, space, r3d)
        self.start_value = self._value(self._strip(context))
        self.start_home = self._home(self.view, x, y)
        self.press_state = view_follow.applied(r3d)
        if self.target == 'LAYER':
            self.grab = 'MOVE'
            return
        mine, _other = self._camera_frames(context)
        frame = view_follow.base()
        self.centre_home = view_follow.backward(sum(mine, Vector()) / 4, self.press_state, *frame)
        screen = [location_3d_to_region_2d(region, r3d, c) for c in mine]
        near = [p for p in (location_3d_to_region_2d(region, r3d, c) for c in _handles(mine))
                if p is not None and (p.x - x) ** 2 + (p.y - y) ** 2 <= cfg.CORNER_GRAB_PX ** 2]
        if near:
            self.grab = 'ZOOM'
        elif None not in screen and _inside((x, y), [(p.x, p.y) for p in screen]):
            self.grab = 'MOVE'
        else:
            self.grab = 'ROTATE'

    def _drag(self, context, event):
        region, space, r3d = self.view
        p = self._home(self.view, event.mouse_x - region.x, event.mouse_y - region.y)
        p0, v0 = self.start_home, self.start_value
        delta = view_follow.linear(p - p0, self.press_state)     # as the hand moved on screen
        if self.target == 'LAYER':
            st = self._strip(context).plastron_panel.material.plastron_stack
            sw, sh = canvas_sync.sheet_size()
            self._put(context, (v0[0] + delta.x / sw * st.width, v0[1] + delta.z / sh * st.height))
            return
        # In Camera View with the drawing following the hand, the camera goes the other way.
        sign = -1.0 if (view_follow.enabled() and not cfg.CAMERA_FOLLOWS_HAND) else 1.0
        width = view_follow.base()[1]
        x, y, zoom, rot = v0
        c = self.centre_home
        if self.grab == 'MOVE':
            x += sign * delta.x / width * 100
            y += sign * delta.z / width * 100
        elif self.grab == 'ZOOM':
            d0 = math.hypot(p0.x - c.x, p0.z - c.z)
            d1 = math.hypot(p.x - c.x, p.z - c.z)
            zoom = min(cfg.ZOOM_RANGE[1], max(cfg.ZOOM_RANGE[0], zoom * d0 / max(d1, 1e-6)))
        else:
            turn = math.atan2(p.z - c.z, p.x - c.x) - math.atan2(p0.z - c.z, p0.x - c.x)
            turn = (turn + math.pi) % math.tau - math.pi
            rot += sign * turn
            if event.shift:
                step = math.radians(cfg.ROTATE_STEP)
                rot = round(rot / step) * step
            limit = math.radians(cfg.ROTATION_LIMIT)
            rot = min(limit, max(-limit, rot))
        self._put(context, (x, y, zoom, rot))

    # --- finishing ------------------------------------------------------------------------
    def _end(self, context, keep):
        if self._draw in canvas_frame.EXTRA_DRAW:
            canvas_frame.EXTRA_DRAW.remove(self._draw)
        storyboard_tools.override_label[0] = None
        context.window_manager[EDITING] = ""
        strip = self._strip(context)
        if strip is None:
            return
        if not keep:
            for end, value in self.original.items():
                self._put(context, value, end)
        elif any(self._value(strip, end) != value for end, value in self.original.items()):
            panel_cache.request(strip.plastron_panel.material)
            what = "Camera" if self.target == 'CAMERA' else "Layer"
            try:
                bpy.ops.ed.undo_push(message=f"{what} move")
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
        if v == 'PRESS' and (t in {'RET', 'NUMPAD_ENTER'} or (t == 'C' and self.target == 'CAMERA')):
            self._end(context, True)
            return {'FINISHED'}
        if v == 'PRESS' and t == 'ESC':
            self._end(context, False)
            return {'CANCELLED'}
        if v == 'PRESS' and t == 'TAB' and self.grab is None:
            self.end = 'END' if self.end == 'START' else 'START'
            self._go_to_end(context)
            self._redraw(context)
            return {'RUNNING_MODAL'}
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
            self._press(context, hit)
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and v == 'RELEASE':
            self.grab = None
            return {'RUNNING_MODAL'}
        if v == 'PRESS' and t == 'RIGHTMOUSE':
            self._end(context, False)
            return {'CANCELLED'}
        return {'PASS_THROUGH'} if t not in {'LEFTMOUSE', 'RIGHTMOUSE'} else {'RUNNING_MODAL'}


def _fill_square(context, x, y, d, color):
    import gpu
    from gpu_extras.batch import batch_for_shader
    from ...core.theme import _color
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.uniform_float("color", _color(color))
    verts = [(x - d, y - d), (x + d, y - d), (x + d, y + d), (x - d, y + d)]
    batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)


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
