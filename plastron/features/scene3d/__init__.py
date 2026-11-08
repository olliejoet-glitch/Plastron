"""The 3D scene (Ollie: "this 3d view [should] move around the frames
I'm adding": add a frame on a new layer, drag it forwards or backwards,
then move the camera to add parallax; the camera move keyframes itself).

- The scene view (under the script) is Blender's own 3D view: header menus,
  toolbar (select, move, rotate, scale...), transform and navigation gizmos.
  Ctrl+Space maximises it (any area).
- It shows the panels as cards, one per video track, where the canvas has
  them. Moving / turning / scaling a card there moves that whole TRACK (it's
  kept on the track: place_offset / place_rotation / place_scale, and the
  canvas sheets follow it).
- "3D Camera" is the view's own camera (View > Cameras > Active Camera looks
  through it). It starts square-on, exactly framing the picture. Moving it
  keys it at the playhead (location, rotation, lens) under the hood, so a
  move is: playhead to the start, place the camera, playhead to the end,
  place it again.
- Painting and the scene need different modes: Object mode over the scene
  view, painting over the canvas (follows the pen, no undo steps). The
  canvas's keys (B, E, Ctrl+T...) do nothing in the scene view.
"""

import math

import bpy
from mathutils import Euler, Vector

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


def rest_pose():
    """Square-on to the picture plane, at the distance that frames it exactly."""
    from ...config import project_defaults as defaults
    distance = defaults.CANVAS_WIDTH * cfg.CAMERA_LENS / 36.0       # 36 mm sensor across
    return (Vector(cfg.ORIGIN) + Vector((0.0, -distance, 0.0)),
            Euler((math.radians(90.0), 0.0, 0.0)))


def camera(scene):
    """The 3D scene's camera (made if missing)."""
    obj = bpy.data.objects.get(cfg.CAMERA_NAME)
    if obj is None:
        data = bpy.data.cameras.new(cfg.CAMERA_NAME)
        data.lens = cfg.CAMERA_LENS
        data.sensor_fit = 'HORIZONTAL'
        data.sensor_width = 36.0
        data.clip_end = cfg.CLIP_END
        obj = bpy.data.objects.new(cfg.CAMERA_NAME, data)
        obj.location, obj.rotation_euler = rest_pose()
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
    remember_pose(cam)
    for _area, space in scene_views():
        if space.camera != cam:
            space.camera = cam
        # Select something (the camera, a card): move + rotate gizmos straight away.
        if not space.show_gizmo_object_translate:
            space.show_gizmo_object_translate = True
        if not space.show_gizmo_object_rotate:
            space.show_gizmo_object_rotate = True
        if space.clip_end != cfg.CLIP_END:
            space.clip_end = cfg.CLIP_END
    if (scene.cursor.location - Vector(cfg.ORIGIN)).length > 1e-3:
        scene.cursor.location = cfg.ORIGIN
    # The canvas's flat camera isn't a 3D thing: drawn tiny there. (Hiding it
    # upset the canvas's view maths: Ctrl+0 fit came out wrong.)
    flat = bpy.data.objects.get(FLAT_CAMERA) or scene.camera
    if flat is not None and flat != cam and scene.camera != flat:
        scene.camera = flat                        # (the canvas's frame maths use it)
    if flat is not None and flat != cam:
        if flat.hide_viewport:
            flat.hide_viewport = False
        if flat.type == 'CAMERA' and flat.data.display_size > 0.051:
            flat.data.display_size = 0.05
    bpy.app.timers.register(lambda: hide_shelves() and None, first_interval=0.3)


# --- the canvas looks through the 3D camera (Ollie: "moving the camera needs to
# actually change what I see on the canvas") --------------------------------------------------

SETTING = "canvas_3d_camera"
FLAT_CAMERA = "Canvas Camera"     # core/project's flat ortho camera (the scene camera)


def linked():
    from ...core import user_settings
    return bool(user_settings.get(SETTING, True))


def canvas_areas():
    from ...core.views import is_canvas_area
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if is_canvas_area(area):
                yield area


def link_canvases(scene=None, fit=True):
    """Canvas views through the 3D camera (or back to the flat view)."""
    from ..storyboard import canvas_view
    scene = scene or bpy.context.scene
    if scene is None or not hasattr(scene, "plastron_timeline"):
        return
    cam = camera(scene)
    for area in canvas_areas():
        space = area.spaces.active
        r3d = space.region_3d
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if linked():
            if space.camera != cam:
                space.camera = cam
            if not space.use_local_camera:
                space.use_local_camera = True
            if r3d.view_perspective != 'CAMERA':
                flat = scene.camera
                r3d.view_perspective = 'CAMERA'
                if scene.camera != flat:          # (Blender makes it the scene camera too)
                    scene.camera = flat
                if fit and region is not None and region.width > 1:
                    canvas_view.fit(scene, region, space, r3d)
        elif r3d.view_perspective == 'CAMERA' or space.use_local_camera:
            space.use_local_camera = False
            r3d.view_perspective = 'ORTHO'
            r3d.view_rotation = Euler((math.radians(90.0), 0.0, 0.0)).to_quaternion()
            if fit:
                # Blender settles the view after leaving the camera: fit after that.
                bpy.app.timers.register(lambda: canvas_view.fit_all_canvases() and None,
                                        first_interval=0.15)
        area.tag_redraw()


def frame_through_camera(context):
    """canvas_frame hook: looking through the 3D camera, the frame is its frame."""
    from ...core.views import through_camera
    space = context.space_data
    if not through_camera(space) or space.camera is None:
        return None
    cam = space.camera
    return [cam.matrix_world @ v for v in cam.data.view_frame(scene=context.scene)]


def _get_linked(_self):
    return linked()


def _set_linked(_self, value):
    from ...core import user_settings
    user_settings.set(SETTING, bool(value))
    link_canvases()


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


# --- the scene view's edits: cards move their track; the camera keys itself ----------------

_busy = [False]
_held = [0]          # >0: the camera is being moved for a view only (R rotate): no keys


def hold_keys():
    _held[0] += 1


def release_keys():
    # After the depsgraph has seen the camera put back.
    bpy.app.timers.register(lambda: _held.__setitem__(0, max(0, _held[0] - 1)), first_interval=0.3)


def _place_from(track, obj, scene):
    from ..storyboard import canvas_sync
    base = canvas_sync.order_y(scene, track)
    offset = (obj.location.x, obj.location.y - base, obj.location.z)
    rotation = tuple(obj.rotation_euler)
    scale = obj.scale.y                       # (x / z also carry the painting's size)
    changed = False
    if any(abs(a - b) > 1e-6 for a, b in zip(track.place_offset, offset)):
        track.place_offset = offset
        changed = True
    if any(abs(a - b) > 1e-6 for a, b in zip(track.place_rotation, rotation)):
        track.place_rotation = rotation
        changed = True
    if abs(track.place_scale - scale) > 1e-6 and scale > 1e-4:
        track.place_scale = scale
        changed = True
    if changed:
        key_card(scene, track)
    return changed


# Cards animate (Ollie: "the frames need to be moveable and animateable"):
# moving a card keys its track's placement at the playhead, like the camera.
CARD_PROPS = ("place_offset", "place_rotation", "place_scale")
_animated = {"scene": None, "yes": False}


def card_group(scene, track):
    from ...timeline import tracks
    return f"Card: {tracks.name(scene, track)}"


def key_card(scene, track):
    frame = scene.frame_current
    for prop in CARD_PROPS:
        track.keyframe_insert(prop, frame=frame, group=card_group(scene, track))
    _animated.update(scene=scene.name, yes=True)


def cards_animated(scene):
    """Does any track's card have keys? (Worked out once per edit / load.)"""
    if _animated["scene"] != scene.name:
        ad = scene.animation_data
        action = ad.action if ad else None
        yes = action is not None and any("plastron_timeline.tracks" in fc.data_path
                                         for fc in _all_fcurves(action))
        _animated.update(scene=scene.name, yes=yes)
    return _animated["yes"]


def _forget_animated(*_args):
    _animated["scene"] = None


def _cards_frame(scene, *_args):
    # Per-frame hook (allowed: Ollie asked for animated cards). O(1) when no
    # card is keyed; else re-places the track sheets (Blender has already
    # played the keys into the tracks' placement).
    if cards_animated(scene):
        from ..storyboard import canvas_sync
        canvas_sync.apply_places(scene)


def _keyed(owner, path, frame):
    """Is owner.path already keyed with its current value at frame?"""
    ad = owner.animation_data
    action = ad.action if ad else None
    if action is None:
        return False
    value = getattr(owner, path)
    values = list(value) if hasattr(value, "__len__") else [value]
    for i, v in enumerate(values):
        fc = _fcurve(action, owner, path, i)
        if fc is None or not any(abs(k.co[0] - frame) < 1e-3 for k in fc.keyframe_points) \
                or abs(fc.evaluate(frame) - v) > 1e-5:
            return False
    return True


def _fcurve(action, owner, path, index):
    return next((fc for fc in _all_fcurves(action) if fc.data_path == path and fc.array_index == index), None)


def _all_fcurves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []                                   # layered actions (Blender 4.4+)
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


_seen = {"pose": None}     # the camera's pose when last keyed / looked at


def _pose(cam):
    return tuple(cam.location) + tuple(cam.rotation_euler) + (cam.data.lens,)


def remember_pose(cam):
    _seen["pose"] = _pose(cam)


def key_camera(scene, cam):
    """Key the 3D camera where it is now, at the playhead, if it was moved
    (any other update to it, e.g. a view switching to it, keys nothing)."""
    pose = _pose(cam)
    last = _seen["pose"]
    if cam.animation_data is None and last is not None and \
            all(abs(a - b) < 1e-6 for a, b in zip(pose, last)):
        return
    _seen["pose"] = pose
    frame = scene.frame_current
    for owner, path in ((cam, "location"), (cam, "rotation_euler"), (cam.data, "lens")):
        if not _keyed(owner, path, frame):
            owner.keyframe_insert(path, frame=frame)


def _playing():
    wm = bpy.context.window_manager
    return wm is not None and any(w.screen and w.screen.is_animation_playing for w in wm.windows)


def _on_edit(scene, depsgraph):
    # Edits only (depsgraph_update_post doesn't run during playback): a card
    # moved in the scene view moves its track; the 3D camera moved is keyed.
    if _busy[0] or _held[0] or not (depsgraph.id_type_updated('OBJECT') or depsgraph.id_type_updated('CAMERA')):
        return
    if scene is None or not hasattr(scene, "plastron_timeline") or _playing():
        return
    from ..storyboard import canvas_sync
    _busy[0] = True
    try:
        for update in depsgraph.updates:
            obj = update.id.original if isinstance(update.id, (bpy.types.Object, bpy.types.Camera)) else None
            if obj is None:
                continue
            if obj.name == cfg.CAMERA_NAME:
                cam = bpy.data.objects.get(cfg.CAMERA_NAME)
                if cam is not None:
                    key_camera(scene, cam)
            elif isinstance(obj, bpy.types.Object) and update.is_updated_transform:
                track = canvas_sync.sheet_track(scene, obj)
                if track is not None:
                    _place_from(track, obj, scene)
    finally:
        _busy[0] = False


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


# --- card outlines in the scene view (empty cards are see-through) --------------------------

_draw_handle = [None]


def _draw_cards():
    context = bpy.context
    if not is_scene_view(context.space_data):
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    from ...config import theme as theme_cfg
    from ...core.theme import _color
    from ..storyboard import canvas_sync
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.uniform_float("viewportSize", (context.region.width, context.region.height))
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    for obj in context.scene.objects:
        is_canvas_sheet = obj.name == canvas_sync.CANVAS
        if not (is_canvas_sheet or obj.name.startswith(canvas_sync.DISPLAY_PREFIX)) or obj.hide_viewport:
            continue
        pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
        if len(pts) != 4:
            continue
        colour = theme_cfg.CANVAS["frame_edit"] if is_canvas_sheet else cfg.CARD_COLOR
        shader.uniform_float("lineWidth", 2.0 if is_canvas_sheet or obj.select_get() else 1.0)
        shader.uniform_float("color", _color(colour))
        batch_for_shader(shader, 'LINE_STRIP', {"pos": [tuple(p) for p in pts + pts[:1]]}).draw(shader)
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')


classes = (PLASTRON_OT_view_focus,)


def _on_load(scene):
    _animated["scene"] = None
    ensure(scene)
    link_canvases(scene, fit=False)      # (the canvas is fitted once the window is ready)


def _track_place(track):
    return tuple(track.place_offset), tuple(track.place_rotation), track.place_scale


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from ...timeline.tracks import PLASTRON_PG_track as Track
    Track.place_offset = bpy.props.FloatVectorProperty(size=3, subtype='TRANSLATION')
    Track.place_rotation = bpy.props.FloatVectorProperty(size=3, subtype='EULER')
    Track.place_scale = bpy.props.FloatProperty(default=1.0, min=0.001)
    from ..storyboard import canvas_sync
    canvas_sync.SHEET_PLACE[0] = _track_place
    canvas_sync.SHEET_ABSORB[0] = lambda scene, obj, track: _place_from(track, obj, scene)
    from ..storyboard import canvas_frame
    canvas_frame.FRAME_PROVIDERS.insert(0, frame_through_camera)
    from ..storyboard import canvas_view
    canvas_view.PLASTRON_OT_canvas_rotate.HOLD_KEYS[:] = [(hold_keys, release_keys)]
    bpy.types.WindowManager.plastron_canvas_3d = bpy.props.BoolProperty(
        name="3D Camera", description="The canvas looks through the 3D Camera (moving it moves what you see)",
        get=_get_linked, set=_set_linked)
    # First: a card moved in the scene view must be kept on its track before
    # the timeline's edit handler re-syncs the canvas (which would put it back).
    handlers.add("depsgraph_update_post", _on_edit, first=True)
    handlers.add("frame_change_post", _cards_frame)
    handlers.add("undo_post", _forget_animated)
    handlers.add("redo_post", _forget_animated)
    _draw_handle[0] = bpy.types.SpaceView3D.draw_handler_add(_draw_cards, (), 'WINDOW', 'POST_VIEW')
    handlers.on_load(_on_load)
    from ...timeline import events
    events.listen("project_created", ensure)


def unregister():
    if _draw_handle[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle[0], 'WINDOW')
        _draw_handle[0] = None
    from ..storyboard import canvas_sync
    canvas_sync.SHEET_PLACE[0] = None
    canvas_sync.SHEET_ABSORB[0] = None
    from ..storyboard import canvas_frame
    if frame_through_camera in canvas_frame.FRAME_PROVIDERS:
        canvas_frame.FRAME_PROVIDERS.remove(frame_through_camera)
    del bpy.types.WindowManager.plastron_canvas_3d
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
