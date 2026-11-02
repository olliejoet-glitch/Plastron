"""The 3D scene (Ollie: "a small 3d scene under my script that I can
maximise, with standard Blender gizmo controls, and a 3D camera").

- The scene view (under the script) is Blender's own 3D view: header menus
  (View / Select / Add / Object), toolbar (select, move, rotate, scale...),
  transform and navigation gizmos. Ctrl+Space maximises it (any area).
- Its objects sit around config/scene3d.ORIGIN, far from the canvas, in the
  "3D Scene" collection; its camera is "3D Camera" (the view's own camera:
  View > Cameras > Active Camera looks through it).
- Painting and the scene need different modes: when the pen moves over the
  scene view Blender goes to Object mode, and back to painting the canvas
  when it moves over the canvas (no undo steps for the switch).
- The canvas's keys (B, E, Ctrl+T...) do nothing in the scene view.
"""


import bpy
from mathutils import Vector

from ...config import scene3d as cfg
from ...core import handlers
from ...core.views import is_canvas, is_scene_view


def collection(scene):
    coll = bpy.data.collections.get(cfg.COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(cfg.COLLECTION)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def camera(scene):
    """The 3D scene's camera (made if missing)."""
    obj = bpy.data.objects.get(cfg.CAMERA_NAME)
    if obj is None:
        data = bpy.data.cameras.new(cfg.CAMERA_NAME)
        data.lens = cfg.CAMERA_LENS
        data.clip_end = cfg.CLIP_END
        obj = bpy.data.objects.new(cfg.CAMERA_NAME, data)
        origin = Vector(cfg.ORIGIN)
        obj.location = origin + Vector(cfg.CAMERA_OFFSET)
        direction = origin - obj.location
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        collection(scene).objects.link(obj)
    return obj


def scene_views():
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D' and is_scene_view(area.spaces.active):
                yield area, area.spaces.active


def hide_shelves():
    """No brush shelf strip under the scene view (Blender adds one while
    painting; folded away once, it stays away)."""
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type != 'VIEW_3D' or not is_scene_view(area.spaces.active):
                continue
            shelf = next((r for r in area.regions if r.type == 'ASSET_SHELF'), None)
            if shelf is not None and shelf.height > 1:
                try:
                    with bpy.context.temp_override(window=window, area=area, region=shelf):
                        bpy.ops.screen.region_toggle(region_type='ASSET_SHELF')
                except RuntimeError as err:
                    print("Plastron: couldn't fold the 3D scene's shelf:", err)


def ensure(scene):
    """The 3D scene's collection and camera exist; scene views look at them."""
    if scene is None or not hasattr(scene, "plastron_timeline"):
        return
    cam = camera(scene)
    for _area, space in scene_views():
        if space.camera != cam:
            space.camera = cam
        if space.clip_end != cfg.CLIP_END:
            space.clip_end = cfg.CLIP_END
    if (scene.cursor.location - Vector(cfg.ORIGIN)).length > 1e-3:
        scene.cursor.location = cfg.ORIGIN          # new objects (Add menu) land in the scene
    bpy.app.timers.register(lambda: hide_shelves() and None, first_interval=0.3)


# --- painting <-> object mode as the pen moves between views --------------------------------

def _canvas_object(scene):
    from ..storyboard import canvas_sync
    return canvas_sync.canvas_object(scene)


def focus(context):
    """Right mode for the 3D view under the pen. True if it changed."""
    space = context.space_data
    scene = context.scene
    if is_scene_view(space):
        if context.mode != 'OBJECT' and context.view_layer.objects.active is not None:
            bpy.ops.object.mode_set(mode='OBJECT')
            return True
        return False
    if is_canvas(space) and context.mode != 'PAINT_TEXTURE':
        canvas = _canvas_object(scene)
        view_layer = context.view_layer
        if context.mode != 'OBJECT' and view_layer.objects.active is not None:
            bpy.ops.object.mode_set(mode='OBJECT')
        if view_layer.objects.active != canvas:
            view_layer.objects.active = canvas
        bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        from ...layers import paint_target
        paint_target.sync(scene=scene)
        return True
    return False


class PLASTRON_OT_view_focus(bpy.types.Operator):
    """Painting on the canvas, Object mode in the 3D scene (follows the pen)"""
    bl_idname = "plastron.view_focus"
    bl_label = "View Focus"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        try:
            focus(context)
        except RuntimeError as err:          # e.g. mid-operation: try at the next move
            print("Plastron: couldn't switch mode:", err)
        return {'PASS_THROUGH'}


classes = (PLASTRON_OT_view_focus,)


def _on_load(scene):
    ensure(scene)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    handlers.on_load(_on_load)
    from ...timeline import events
    events.listen("project_created", ensure)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
