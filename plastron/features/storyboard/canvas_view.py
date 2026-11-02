"""Canvas navigation: zoom, fit, 100 %, spring-loaded rotate, flip view.

All of these only move the view. The drawing itself is never changed.
"""

import math

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Quaternion, Vector

from ...core.views import is_canvas
from ...timeline import view as timeline_view

FIT_MARGIN = 0.9      # fit leaves 10 % breathing room
ZOOM_STEP = 1.25      # one zoom step = 25 %


def _canvas_poll(context):
    from ...core.views import is_canvas
    return (context.area is not None and is_canvas(context.space_data)
            and context.region_data is not None)


def _flat(context):
    """The canvas looks at the drawing flat (not through the 3D camera)."""
    return context.region_data is not None and context.region_data.view_perspective != 'CAMERA'


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


# Blender's orthographic view shows (view_distance * 36 / lens * 2) units across
# the region's longer side (36 = default sensor width, 2 = ortho view zoom).
# Computing it directly avoids the view matrix, which is stale until a redraw.
def _units_across(space, r3d):
    return r3d.view_distance * 36.0 / space.lens * 2.0


def pixels_per_unit(region, space, r3d):
    return max(region.width, region.height) / _units_across(space, r3d)


def set_pixels_per_unit(region, space, r3d, ppu):
    r3d.view_distance = max(region.width, region.height) / ppu * space.lens / (36.0 * 2.0)


def frame_size_units(scene):
    """Camera frame (width, height) in scene units."""
    corners = camera_frame(scene)
    if not corners:
        return None
    return (corners[0] - corners[3]).length, (corners[0] - corners[1]).length


class PLASTRON_OT_canvas_zoom(bpy.types.Operator):
    """Zoom the canvas view in or out"""
    bl_idname = "plastron.canvas_zoom"
    bl_label = "Zoom Canvas"
    step: bpy.props.IntProperty(default=1)

    # (zooms the 3D scene view too)
    poll = classmethod(lambda cls, context: context.area is not None and context.area.type == 'VIEW_3D'
                       and context.region_data is not None)

    def execute(self, context):
        r3d = context.region_data
        if r3d.view_perspective == 'CAMERA':          # looking through the 3D camera
            scale_camera_zoom(r3d, ZOOM_STEP ** self.step)
        else:
            _scale_distance(r3d, ZOOM_STEP ** -self.step)
        context.area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_canvas_fit(bpy.types.Operator):
    """Fit the camera frame to the canvas"""
    bl_idname = "plastron.canvas_fit"
    bl_label = "Fit to Screen"

    poll = classmethod(lambda cls, context: _canvas_poll(context))

    def execute(self, context):
        fit(context.scene, context.region, context.space_data, context.region_data)
        context.area.tag_redraw()
        return {'FINISHED'}


AFTER_FIT = []   # func(region_3d) after a view is fitted (motion: camera view)


# Looking through a camera, Blender's zoom is a number whose scale factor is
# ((sqrt(2) + zoom / 50) ** 2) / 4 (BKE_screen_view3d_zoom_to_fac).
def _cam_fac(zoom):
    return ((math.sqrt(2.0) + zoom / 50.0) ** 2) / 4.0


def _cam_zoom(fac):
    return (2.0 * math.sqrt(max(fac, 1e-6)) - math.sqrt(2.0)) * 50.0


def scale_camera_zoom(r3d, factor):
    r3d.view_camera_zoom = max(-30.0, min(600.0, _cam_zoom(_cam_fac(r3d.view_camera_zoom) * factor)))


def fit_camera_view(region, r3d, aspect):
    """Through a camera: the frame centred, filling FIT_MARGIN of the canvas.
    (Measured: the frame's width on screen = zoom factor x the region's
    longer side.) aspect: frame width / height."""
    longest = max(region.width, region.height)
    fac = min(region.width * FIT_MARGIN, region.height * FIT_MARGIN * aspect) / longest
    r3d.view_camera_offset = (0.0, 0.0)
    r3d.view_camera_zoom = max(-30.0, min(600.0, _cam_zoom(fac)))


def fit(scene, region, space, r3d):
    if r3d.view_perspective == 'CAMERA':          # through the 3D camera
        size = frame_size_units(scene)
        fit_camera_view(region, r3d, size[0] / size[1] if size else 16 / 9)
        return
    corners = camera_frame(scene)
    if not corners:
        return
    r3d.view_location = sum(corners, Vector()) / 4
    fw, fh = frame_size_units(scene)
    ppu = min(region.width * FIT_MARGIN / fw, region.height * FIT_MARGIN / fh)
    set_pixels_per_unit(region, space, r3d, ppu)
    for func in AFTER_FIT:
        func(r3d)


def screen_to_world(region, space, r3d, x, y):
    """Region pixel -> point on the canvas plane, from the view's own numbers
    (never stale, unlike the view matrices before a redraw)."""
    ppu = pixels_per_unit(region, space, r3d)
    v = Vector(((x - region.width / 2) / ppu, (y - region.height / 2) / ppu, 0.0))
    p = r3d.view_location + r3d.view_rotation @ v
    p.y = 0.0
    return p


class PLASTRON_OT_canvas_zoom_actual(bpy.types.Operator):
    """Zoom so one pixel of the preview resolution is one screen pixel"""
    bl_idname = "plastron.canvas_zoom_actual"
    bl_label = "100 % Zoom"

    poll = classmethod(lambda cls, context: _canvas_poll(context) and _flat(context))

    def execute(self, context):
        scene = context.scene
        size = frame_size_units(scene)
        if not size:
            return {'CANCELLED'}
        preview_width = scene.render.resolution_x * scene.render.resolution_percentage / 100
        set_pixels_per_unit(context.region, context.space_data, context.region_data,
                            preview_width / size[0])
        context.area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_canvas_rotate(bpy.types.Operator):
    """Hold and drag to rotate the canvas view; it snaps back on release"""
    bl_idname = "plastron.canvas_rotate"
    bl_label = "Rotate Canvas View"

    # Through the 3D camera the camera itself is rolled while R is held (its
    # auto-keying held off), then put back exactly.
    HOLD_KEYS = []      # (hold, release) from features/scene3d

    poll = classmethod(lambda cls, context: _canvas_poll(context))

    def invoke(self, context, event):
        self.key = event.type
        self.r3d = context.region_data
        self.start_rotation = self.r3d.view_rotation.copy()
        self.cam = context.space_data.camera if self.r3d.view_perspective == 'CAMERA' else None
        if self.cam is not None:
            self.cam_matrix = self.cam.matrix_world.copy()
            for hold, _release in self.HOLD_KEYS:
                hold()
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
                if self.cam is not None:            # roll the camera the other way
                    roll = Matrix.Rotation(-(angle - self.start_angle), 4, 'Z')
                    self.cam.matrix_world = self.cam_matrix @ roll
                else:
                    turn = Quaternion((0.0, 0.0, 1.0), angle - self.start_angle)
                    self.r3d.view_rotation = self.start_rotation @ turn
                context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        if self.cam is not None:
            self.cam.matrix_world = self.cam_matrix
            for _hold, release in self.HOLD_KEYS:
                release()
        else:
            self.r3d.view_rotation = self.start_rotation
        context.window.cursor_modal_restore()
        context.area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_canvas_flip_view(bpy.types.Operator):
    """Mirror the canvas view left-right. The drawing is unchanged"""
    bl_idname = "plastron.canvas_flip_view"
    bl_label = "Flip Canvas View"

    poll = classmethod(lambda cls, context: _canvas_poll(context) and _flat(context))

    def execute(self, context):
        r3d = context.region_data
        # Look at the drawing plane from behind: a pure left-right mirror.
        r3d.view_rotation = r3d.view_rotation @ Quaternion((0.0, 1.0, 0.0), math.pi)
        context.area.tag_redraw()
        return {'FINISHED'}


def fit_all_canvases():
    """Fit every canvas (and timeline) view; used once after a project opens."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region is None or region.width <= 1:
                continue
            if area.type == 'VIEW_3D' and is_canvas(area.spaces.active):
                space = area.spaces.active
                fit(window.scene, region, space, space.region_3d)
                area.tag_redraw()
            elif area.type == 'SEQUENCE_EDITOR':
                timeline_view.frame(window, area, region, window.scene)


classes = (
    PLASTRON_OT_canvas_zoom,
    PLASTRON_OT_canvas_fit,
    PLASTRON_OT_canvas_zoom_actual,
    PLASTRON_OT_canvas_rotate,
    PLASTRON_OT_canvas_flip_view,
)
