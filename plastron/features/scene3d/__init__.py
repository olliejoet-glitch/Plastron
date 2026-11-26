"""The 3D scene (Ollie: "this 3d view [should] move around the frames
I'm adding": add a frame on a new layer, drag it forwards or backwards,
then move the camera to add parallax; the camera move keyframes itself).

- The scene view (under the script) is Blender's own 3D view: header menus,
  toolbar (select, move, rotate, scale...), transform and navigation gizmos.
  Ctrl+Space maximises it (any area).
- It shows the panels as cards, one per video track, where the canvas has
  them. Moving / turning / scaling a card there moves that CLIP's card, keyed
  at the playhead (each clip owns its animation: shots.py).
- "3D Camera" is the view's own camera (View > Cameras > Active Camera looks
  through it). It starts square-on, exactly framing the picture. Moving it
  keys the shot's camera (the clip being drawn on) at the playhead, so a
  move is: playhead to the start, place the camera, playhead to the end,
  place it again. Other clips aren't touched; a clip with no camera of its
  own rests square-on.
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
from . import shots


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
    if abs(cam.data.display_size - cfg.CAMERA_DISPLAY_SIZE) > 1e-4:
        cam.data.display_size = cfg.CAMERA_DISPLAY_SIZE          # big enough to click
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
        if not flat.hide_select:           # clicks in the 3D scene go to the real camera
            flat.hide_select = True
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
    from ..storyboard import canvas_sync          # (cards in depth only through the camera)
    if bpy.context.scene is not None:
        canvas_sync.invalidate(bpy.context.scene)


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


def track_depth(scene, track):
    """(y, scale) of a video track's card by its place in the list: the top
    track in the picture plane, each one below TRACK_SPACING further back,
    scaled to fill the frame from the camera's rest spot. None: flat canvas."""
    if not linked():
        return None
    from ...timeline import tracks
    videos = tracks.video_tracks(scene)
    uids = [t.uid for t in videos]
    if track.uid not in uids:
        return None
    y = (len(uids) - 1 - uids.index(track.uid)) * cfg.TRACK_SPACING
    distance = -rest_pose()[0].y + cfg.ORIGIN[1]
    return y, (distance + y) / distance


def _sheet_clip(scene, obj, track):
    """The clip a sheet shows right now (its card is that clip's)."""
    from ..storyboard import canvas_sync
    from ...timeline import clips, tracks
    if obj.name == canvas_sync.CANVAS:
        return shot_clip(scene)
    return clips.at(scene, tracks.channel_of(scene, track), scene.frame_current)


def _place_from(track, obj, scene):
    """A card moved by hand in the scene view: the clip it shows keeps it."""
    from ..storyboard import canvas_sync
    clip = _sheet_clip(scene, obj, track)
    if clip is None:
        return False
    base, depth_scale = canvas_sync.depth_of(scene, track)
    offset = (obj.location.x, obj.location.y - base, obj.location.z)
    scale = obj.scale.y / depth_scale         # (x / z also carry the painting's size)
    return shots.set_card(scene, clip, offset, tuple(obj.rotation_euler), scale, scene.frame_current)


def _clip_place(scene, track):
    """canvas_sync hook: where a track's card stands now = its clip's."""
    from ...timeline import clips, tracks
    if scene is None or track is None:
        return shots.card_place(None)
    return shots.card_place(clips.at(scene, tracks.channel_of(scene, track), scene.frame_current), scene.frame_current)


def _clip_moves(scene, clip):
    """canvas_sync hook: does this clip's card move (keys)? Asked once per stretch."""
    return shots.animated(scene, clip, shots.CARD_PROPS)


# --- the 3D Camera: the shot's own (the clip being drawn on) --------------------------------

_seen = {"pose": None}     # the camera's pose as Plastron last put it / saw it keyed
_shot = {"work": -1, "name": "", "anim": False, "scene": None}


def shot_clip(scene):
    """The clip being drawn on (the shot whose camera the 3D Camera shows)."""
    from ..storyboard import canvas_sync
    name = canvas_sync._state.get("canvas_clip")
    sed = scene.sequence_editor
    return sed.strips_all.get(name) if (sed is not None and name) else None


def _pose(cam):
    return tuple(cam.location) + tuple(cam.rotation_euler) + (cam.data.lens,)


def remember_pose(cam):
    _seen["pose"] = _pose(cam)


def shot_pose(scene):
    pose = shots.camera_pose(shot_clip(scene), scene.frame_current)
    if pose is not None:
        return pose
    loc, rot = rest_pose()
    return tuple(loc), tuple(rot), cfg.CAMERA_LENS


def apply_camera(scene):
    """Put the 3D Camera where the shot says (only what differs)."""
    cam = bpy.data.objects.get(cfg.CAMERA_NAME)
    if cam is None:
        return
    loc, rot, lens = shot_pose(scene)
    if any(abs(a - b) > 1e-6 for a, b in zip(cam.location, loc)):
        cam.location = loc
    if any(abs(a - b) > 1e-6 for a, b in zip(cam.rotation_euler, rot)):
        cam.rotation_euler = rot
    if abs(cam.data.lens - lens) > 1e-6:
        cam.data.lens = lens
    remember_pose(cam)


def _camera_frame(scene, *_args):
    # Per-frame hook (allowed: Ollie asked for animated cameras). O(1) unless
    # the canvas moved on to another clip, or the shot's camera is keyed.
    if scene is None or not hasattr(scene, "plastron_timeline"):
        return
    from ..storyboard import canvas_sync
    canvas_sync.on_frame(scene)                 # (its clip for this frame first; O(1) if done)
    work = canvas_sync._state["work"]
    if _shot["work"] != work or _shot["scene"] != scene.name:
        clip = shot_clip(scene)
        _shot.update(work=work, scene=scene.name, name=clip.name if clip else "",
                     anim=shots.animated(scene, clip, shots.CAM_PROPS))
        apply_camera(scene)
    elif _shot["anim"]:
        apply_camera(scene)


def _forget_shot(*_args):
    _shot["work"] = -1


def key_camera(scene, cam):
    """The camera was moved by hand: the shot keeps it, keyed at the playhead
    (any other update to it, e.g. Plastron putting it where the shot says,
    keys nothing)."""
    pose = _pose(cam)
    last = _seen["pose"]
    if last is not None and all(abs(a - b) < 1e-6 for a, b in zip(pose, last)):
        return
    _seen["pose"] = pose
    clip = shot_clip(scene)
    if clip is None:
        return                                  # (no clip here: nothing to keep it in)
    shots.set_camera(scene, clip, tuple(cam.location), tuple(cam.rotation_euler), cam.data.lens,
                     scene.frame_current)
    _forget_shot()


ANIM_DRAGS = {"TRANSFORM_OT_transform"}   # (moving keys in the keyframe view; 3D moves are TRANSLATE / ROTATE...)


def _dragging_keys():
    wm = bpy.context.window_manager
    return wm is not None and any(op.bl_idname in ANIM_DRAGS for w in wm.windows for op in w.modal_operators)


def _playing():
    wm = bpy.context.window_manager
    return wm is not None and any(w.screen and w.screen.is_animation_playing for w in wm.windows)


def _on_edit(scene, depsgraph):
    # Edits only (depsgraph_update_post doesn't run during playback): a card
    # moved in the scene view moves its track; the 3D camera moved is keyed.
    if _busy[0] or _held[0] or not (depsgraph.id_type_updated('OBJECT') or depsgraph.id_type_updated('CAMERA')
                                    or depsgraph.id_type_updated('SCENE') or depsgraph.id_type_updated('ACTION')):
        return
    if scene is None or not hasattr(scene, "plastron_timeline") or _playing() or _dragging_keys():
        return
    from ..storyboard import canvas_sync
    _busy[0] = True
    try:
        moved_camera = False
        for update in depsgraph.updates:
            obj = update.id.original if isinstance(update.id, (bpy.types.Object, bpy.types.Camera)) else None
            if obj is None:
                continue
            if obj.name == cfg.CAMERA_NAME:
                cam = bpy.data.objects.get(cfg.CAMERA_NAME)
                if cam is not None:
                    key_camera(scene, cam)
                    moved_camera = True
            elif isinstance(obj, bpy.types.Object) and update.is_updated_transform:
                track = canvas_sync.sheet_track(scene, obj)
                if track is not None and canvas_sync.moved_by_hand(obj):
                    _place_from(track, obj, scene)
        if not moved_camera and (depsgraph.id_type_updated('SCENE') or depsgraph.id_type_updated('ACTION')):
            # Keys edited (keyframe view): back into the clip's own keys; the
            # camera / cards show the clips' new values.
            shots.check_mirror(scene)
            _forget_shot()
            apply_camera(scene)
            canvas_sync.apply_places(scene)
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


class PLASTRON_OT_scene_select_camera(bpy.types.Operator):
    """Select the 3D Camera (its move / turn gizmos show straight away)"""
    bl_idname = "plastron.scene_select_camera"
    bl_label = "Select Camera"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and hasattr(context.scene, "plastron_timeline")

    def execute(self, context):
        select_camera(context)
        if context.area is not None:
            context.area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_shot_reset(bpy.types.Operator):
    """Put the panel being drawn on back: its card square-on in its place,
    and / or its camera at rest (their keys go)"""
    bl_idname = "plastron.shot_reset"
    bl_label = "Reset"
    bl_options = {'REGISTER', 'UNDO'}

    what: bpy.props.EnumProperty(items=(
        ('CARD', "Reset Card", "This panel's card back square-on in its place (its card keys go)"),
        ('CAMERA', "Reset Camera", "This panel's camera back at rest (its camera keys go)"),
        ('BOTH', "Reset Card and Camera", "Both")), default='CARD')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and hasattr(context.scene, "plastron_timeline") \
            and shot_clip(context.scene) is not None

    def execute(self, context):
        scene = context.scene
        clip = shot_clip(scene)
        if not reset_shot(scene, clip, card=self.what in ('CARD', 'BOTH'), camera=self.what in ('CAMERA', 'BOTH')):
            self.report({'INFO'}, f"{clip.name}: nothing to reset")
            return {'CANCELLED'}
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def reset_shot(scene, clip, card=True, camera=True):
    """shots.reset, then the camera / cards shown where the clip now says."""
    from ..storyboard import canvas_sync
    hold_keys()
    try:
        changed = shots.reset(scene, clip, card=card, camera=camera)
        _forget_shot()
        canvas_sync.invalidate(scene)
        canvas_sync.apply_places(scene)
        apply_camera(scene)
    finally:
        release_keys()
    return changed


class PLASTRON_MT_shot_reset(bpy.types.Menu):
    bl_idname = "PLASTRON_MT_shot_reset"
    bl_label = "Reset"

    def draw(self, context):
        clip = shot_clip(context.scene)
        layout = self.layout
        if clip is not None:
            layout.label(text=clip.name)
        for what, text in (('CARD', "Reset Card"), ('CAMERA', "Reset Camera"), ('BOTH', "Reset Card and Camera")):
            layout.operator("plastron.shot_reset", text=text).what = what


def select_camera(context):
    cam = camera(context.scene)
    view_layer = context.view_layer
    if context.mode != 'OBJECT' and view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in view_layer.objects:
        if obj.select_get() and obj != cam:
            obj.select_set(False)
    cam.hide_select = False
    cam.select_set(True)
    view_layer.objects.active = cam
    return cam


def _draw_header(self, context):
    """Scene view header: a Camera button (on while the camera is selected)."""
    if not is_scene_view(context.space_data):
        return
    cam = bpy.data.objects.get(cfg.CAMERA_NAME)
    selected = cam is not None and cam.name in context.view_layer.objects and cam.select_get()
    self.layout.operator("plastron.scene_select_camera", text="Camera", icon='CAMERA_DATA', depress=selected)
    self.layout.menu("PLASTRON_MT_shot_reset", text="Reset", icon='LOOP_BACK')


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


classes = (PLASTRON_OT_view_focus, PLASTRON_OT_scene_select_camera, PLASTRON_OT_shot_reset, PLASTRON_MT_shot_reset)


def _clips_changed(scene, **_info):
    shots.track(scene)                   # (still pictures' clip time follows whole-clip moves)
    shots.check_mirror(scene)


def _after_undo(scene, *_args):
    _forget_shot()
    shots.forget_mirror()
    if scene is not None and hasattr(scene, "plastron_timeline"):
        shots.mirror(scene, force=True)
    if scene is not None and hasattr(scene, "plastron_timeline"):
        _camera_frame(scene)


def _shot_clip_at(scene, frame):
    """The clip that would be drawn on at frame (older projects' camera keys go there)."""
    from ..storyboard import canvas_sync
    from ...timeline import clips, tracks
    sed = clips.editor(scene)
    track = canvas_sync._drawing_track(scene, tracks.video_tracks(scene), frame, sed)
    return clips.at(scene, tracks.channel_of(scene, track), frame) if track is not None else None


def _on_load(scene):
    _forget_shot()
    ensure(scene)
    if scene is not None and hasattr(scene, "plastron_timeline"):
        loc, rot = rest_pose()
        shots.migrate(scene, loc, rot, _shot_clip_at)
        shots.migrate_local(scene)
        shots.forget_mirror()
        from ..storyboard import canvas_sync
        canvas_sync.invalidate(scene)
        _camera_frame(scene)
    link_canvases(scene, fit=False)      # (the canvas is fitted once the window is ready)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from . import keys_view
    keys_view.register()
    shots.register()
    from ...timeline.tracks import PLASTRON_PG_track as Track      # (older projects' per-track cards: read once)
    Track.place_offset = bpy.props.FloatVectorProperty(size=3, subtype='TRANSLATION')
    Track.place_rotation = bpy.props.FloatVectorProperty(size=3, subtype='EULER')
    Track.place_scale = bpy.props.FloatProperty(default=1.0, min=0.001)
    from ..storyboard import canvas_sync
    canvas_sync.SHEET_PLACE[0] = _clip_place
    canvas_sync.SHEET_MOVES[0] = _clip_moves
    canvas_sync.SHEET_ABSORB[0] = lambda scene, obj, track: _place_from(track, obj, scene)
    canvas_sync.SHEET_DEPTH[0] = track_depth
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
    handlers.add("frame_change_post", _camera_frame)
    handlers.add("undo_post", _after_undo)
    handlers.add("redo_post", _after_undo)
    _draw_handle[0] = bpy.types.SpaceView3D.draw_handler_add(_draw_cards, (), 'WINDOW', 'POST_VIEW')
    bpy.types.VIEW3D_HT_header.prepend(_draw_header)      # (left end: the header is narrow)
    handlers.on_load(_on_load)
    from ...timeline import events
    events.listen("project_created", ensure)
    for event in ("clips_changed", "tracks_changed", "active_track_changed"):
        events.listen(event, _forget_shot)
    events.listen("clips_changed", _clips_changed)


def unregister():
    from . import keys_view
    keys_view.unregister()
    bpy.types.VIEW3D_HT_header.remove(_draw_header)
    if _draw_handle[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle[0], 'WINDOW')
        _draw_handle[0] = None
    from ..storyboard import canvas_sync
    canvas_sync.SHEET_PLACE[0] = None
    canvas_sync.SHEET_MOVES[0] = None
    canvas_sync.SHEET_ABSORB[0] = None
    canvas_sync.SHEET_DEPTH[0] = None
    from ..storyboard import canvas_frame
    if frame_through_camera in canvas_frame.FRAME_PROVIDERS:
        canvas_frame.FRAME_PROVIDERS.remove(frame_through_camera)
    del bpy.types.WindowManager.plastron_canvas_3d
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    shots.unregister()
