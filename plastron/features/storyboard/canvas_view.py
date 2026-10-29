"""Canvas navigation: zoom, fit, 100 %, spring-loaded rotate, flip view.

All of these only move the view. The drawing itself is never changed.
"""

import math

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector

FIT_MARGIN = 0.9      # fit leaves 10 % breathing room
ZOOM_STEP = 1.25      # one zoom step = 25 %


def _canvas_poll(context):
    return (context.area is not None and context.area.type == 'VIEW_3D'
            and context.region_data is not None)


def camera_frame(scene):
    """World-space corners of the camera frame, or None."""
    cam = scene.camera
    if cam is None:
        return None
    return [cam.matrix_world @ v for v in cam.data.view_frame(scene=scene)]


def frame_size_px(region, r3d, corners):
    pts = [location_3d_to_region_2d(region, r3d, c) for c in corners]
    if any(p is None for p in pts):
        return None
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def _scale_distance(r3d, factor):
    # Orthographic: on-screen size is inversely proportional to view_distance.
    r3d.view_distance = max(1e-4, r3d.view_distance * factor)


class PLASTRON_OT_canvas_zoom(bpy.types.Operator):
    """Zoom the canvas view in or out"""
    bl_idname = "plastron.canvas_zoom"
    bl_label = "Zoom Canvas"
    step: bpy.props.IntProperty(default=1)

    poll = classmethod(lambda cls, context: _canvas_poll(context))

    def execute(self, context):
        _scale_distance(context.region_data, ZOOM_STEP ** -self.step)
        return {'FINISHED'}


class PLASTRON_OT_canvas_fit(bpy.types.Operator):
    """Fit the camera frame to the canvas"""
    bl_idname = "plastron.canvas_fit"
    bl_label = "Fit to Screen"

    poll = classmethod(lambda cls, context: _canvas_poll(context))

    def execute(self, context):
        fit(context.scene, context.region, context.region_data)
        return {'FINISHED'}


def fit(scene, region, r3d):
    corners = camera_frame(scene)
    if not corners:
        return
    r3d.view_location = sum(corners, Vector()) / 4
    size = frame_size_px(region, r3d, corners)
    if size and size[0] > 0 and size[1] > 0:
        factor = max(size[0] / (region.width * FIT_MARGIN), size[1] / (region.height * FIT_MARGIN))
        _scale_distance(r3d, factor)


class PLASTRON_OT_canvas_zoom_actual(bpy.types.Operator):
    """Zoom so one pixel of the preview resolution is one screen pixel"""
    bl_idname = "plastron.canvas_zoom_actual"
    bl_label = "100 % Zoom"

    poll = classmethod(lambda cls, context: _canvas_poll(context))

    def execute(self, context):
        scene, region, r3d = context.scene, context.region, context.region_data
        corners = camera_frame(scene)
        size = corners and frame_size_px(region, r3d, corners)
        if not size:
            return {'CANCELLED'}
        target = scene.render.resolution_x * scene.render.resolution_percentage / 100
        _scale_distance(r3d, size[0] / target)
        return {'FINISHED'}


class PLASTRON_OT_canvas_rotate(bpy.types.Operator):
    """Hold and drag to rotate the canvas view; it snaps back on release"""
    bl_idname = "plastron.canvas_rotate"
    bl_label = "Rotate Canvas View"

    poll = classmethod(lambda cls, context: _canvas_poll(context))

    def invoke(self, context, event):
        self.key = event.type
        self.r3d = context.region_data
        self.start_rotation = self.r3d.view_rotation.copy()
        region = context.region
        self.center = Vector((region.x + region.width / 2, region.y + region.height / 2))
        self.start_angle = self._angle(event)
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set('SCROLL_XY')
        return {'RUNNING_MODAL'}

    def _angle(self, event):
        d = Vector((event.mouse_x, event.mouse_y)) - self.center
        return math.atan2(d.y, d.x) if d.length > 1 else None

    def modal(self, context, event):
        if event.type == self.key and event.value == 'RELEASE':
            return self._finish(context)
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return self._finish(context)
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            angle = self._angle(event)
            if angle is not None and self.start_angle is None:
                self.start_angle = angle
            elif angle is not None:
                turn = Quaternion((0.0, 0.0, 1.0), angle - self.start_angle)
                self.r3d.view_rotation = self.start_rotation @ turn
                context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        self.r3d.view_rotation = self.start_rotation
        context.window.cursor_modal_restore()
        context.area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_canvas_flip_view(bpy.types.Operator):
    """Mirror the canvas view left-right. The drawing is unchanged"""
    bl_idname = "plastron.canvas_flip_view"
    bl_label = "Flip Canvas View"

    poll = classmethod(lambda cls, context: _canvas_poll(context))

    def execute(self, context):
        r3d = context.region_data
        # Look at the drawing plane from behind: a pure left-right mirror.
        r3d.view_rotation = r3d.view_rotation @ Quaternion((0.0, 1.0, 0.0), math.pi)
        return {'FINISHED'}


def fit_all_canvases():
    """Fit every canvas (and timeline) view; used once after a project opens."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region is None or region.width <= 1:
                continue
            if area.type == 'VIEW_3D':
                fit(window.scene, region, area.spaces.active.region_3d)
            elif area.type == 'SEQUENCE_EDITOR':
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.sequencer.view_all()


classes = (
    PLASTRON_OT_canvas_zoom,
    PLASTRON_OT_canvas_fit,
    PLASTRON_OT_canvas_zoom_actual,
    PLASTRON_OT_canvas_rotate,
    PLASTRON_OT_canvas_flip_view,
)
