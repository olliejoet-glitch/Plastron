"""The 3D scene view under the script: layout, the panels as cards (moving
a card moves that clip's card), the 3D camera (square-on at rest, keys the
shot when moved; each clip owns its animation: moves / splits carry it), Blender's tools and gizmos, painting / Object mode following
the pen, canvas keys staying out of it, Ctrl+Space maximise, Alt+drag orbit."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.scene3d")
scene3d = h.module("features.scene3d")


def centre(area):
    r = h.region(area)
    return r.x + r.width // 2, r.y + r.height // 2


def steps():
    yield 1.0
    h.add_background()
    yield 0.5
    sc = bpy.context.scene
    view = h.area('SCENE_3D')
    script = h.area('TEXT_EDITOR')
    canvas = h.area('VIEW_3D')
    h.check("a 3D scene view under the script", view is not None and script is not None
            and abs(view.x - script.x) < 3 and view.y < script.y, (view and (view.x, view.y), script and (script.x, script.y)))
    space = view.spaces.active
    cam = bpy.data.objects.get(cfg.CAMERA_NAME)
    h.check("...with its own 3D camera, in the 3D Scene collection",
            cam is not None and cam.type == 'CAMERA' and space.camera == cam
            and cam.name in bpy.data.collections[cfg.COLLECTION].objects)
    h.check("...perspective, no toolbar, move + rotate gizmos on whatever's selected",
            space.region_3d.view_perspective == 'PERSP' and not space.show_region_toolbar
            and space.show_gizmo_object_translate and space.show_gizmo_object_rotate
            and space.show_gizmo_navigate and space.show_region_header)
    shelf = h.region(view, 'ASSET_SHELF')
    h.check("no brush shelf strip under it", shelf is None or shelf.height <= 1, shelf and shelf.height)
    loc, rot = scene3d.rest_pose()
    h.check("the camera starts square-on, framing the picture exactly",
            (cam.location - loc).length < 1e-4 and abs(cam.data.lens - cfg.CAMERA_LENS) < 1e-6
            and abs(abs(cam.location.y) - 16 * cam.data.lens / 36) < 1e-4)
    h.check("the canvas's flat camera is drawn tiny in the 3D scene", sc.camera.data.display_size < 0.051)

    # The canvas looks through the 3D camera.
    cspace = canvas.spaces.active
    cr3d = cspace.region_3d
    h.check("the canvas looks through the 3D camera", cr3d.view_perspective == 'CAMERA'
            and cspace.camera == cam)
    cv = h.module("features.storyboard.canvas_view")
    cregion = h.region(canvas)
    h.move(*centre(canvas))
    yield 0.2
    h.key('ZERO', ctrl=True)
    yield 0.3
    h.redraw()
    yield 0.1
    frame = scene3d.frame_through_camera(type("C", (), {"space_data": cspace, "scene": sc})())
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    pts = [location_3d_to_region_2d(cregion, cr3d, c) for c in frame]
    fw = max(p.x for p in pts) - min(p.x for p in pts)
    fh = max(p.y for p in pts) - min(p.y for p in pts)
    h.check("Ctrl+0 fits the 3D camera's frame to the canvas (90 %)",
            abs(max(fw / cregion.width, fh / cregion.height) - 0.9) < 0.02, (fw, fh))
    zoom0 = cr3d.view_camera_zoom
    h.key('EQUAL', ctrl=True)
    yield 0.2
    h.check("Ctrl+= zooms in through the camera", cr3d.view_camera_zoom > zoom0, (zoom0, cr3d.view_camera_zoom))
    h.key('ZERO', ctrl=True)
    yield 0.2
    # Holding R turns the view (by rolling the camera for a moment): no keyframe.
    before_rot = tuple(cam.rotation_euler)
    c = centre(canvas)
    h.move(c[0] + 100, c[1])
    yield
    h._event('R', 'PRESS')
    yield 0.1
    for i in range(1, 6):
        h.move(c[0] + 100 - 15 * i, c[1] + 20 * i)
        yield 0.05
    yield 0.1
    turned = (cam.rotation_euler.to_quaternion().rotation_difference(
        __import__("mathutils").Euler(before_rot).to_quaternion()).angle > 0.05)
    h._event('R', 'RELEASE')
    yield 0.6
    h.check("holding R turns the canvas view; letting go puts it back, unkeyed",
            turned and all(abs(a - b) < 1e-5 for a, b in zip(cam.rotation_euler, before_rot))
            and cam.animation_data is None, (turned, tuple(cam.rotation_euler)))

    # Cards: a panel on another track shows as its own card; moving it back moves the track.
    panels = h.module("features.storyboard.panels")
    tracks = h.module("timeline.tracks")
    canvas_sync = h.module("features.storyboard.canvas_sync")
    videos = tracks.video_tracks(sc)
    active = canvas_sync._state["canvas_track"]
    other = next(t for t in videos if t.uid != active)
    opanel = panels.create(sc, tracks.channel_of(sc, other), sc.frame_current, 48)
    canvas_sync.invalidate(sc)
    yield 0.3
    shots = h.module("features.scene3d.shots")
    clips_mod = h.module("timeline.clips")
    card = bpy.data.objects[canvas_sync.DISPLAY_PREFIX + other.uid]
    h.check("a panel on another track is a card in the 3D scene", not card.hide_viewport and not card.hide_select)
    base_y = card.location.y
    card.location.y = base_y + 4.0
    card.scale = card.scale * 1.5
    yield 0.3
    h.check("moving a card moves THAT CLIP's card (kept on the clip, keyed)",
            abs(opanel.plastron_card_offset[1] - 4.0) < 1e-4 and abs(opanel.plastron_card_scale - 1.5) < 1e-4
            and shots.animated(sc, opanel, shots.CARD_PROPS) and abs(other.place_offset[1]) < 1e-6,
            (tuple(opanel.plastron_card_offset), opanel.plastron_card_scale))
    canvas_sync.invalidate(sc)
    yield 0.2
    h.check("...and the canvas keeps it there", abs(card.location.y - (base_y + 4.0)) < 1e-4)

    # Cards animate: moving one at another frame keys its clip; in between it moves.
    start_frame = sc.frame_current
    sc.frame_current = start_frame + 24
    yield 0.3
    card.location.y = base_y + 10.0
    yield 0.4
    sc.frame_current = start_frame + 12
    yield 0.4
    h.check("moving a card at another frame animates it (in between: in between)",
            base_y + 4.5 < card.location.y < base_y + 9.5, card.location.y - base_y)
    later = panels.create(sc, tracks.channel_of(sc, other), clips_mod.end(opanel), 48)
    canvas_sync.invalidate(sc)
    sc.frame_current = clips_mod.start(later) + 10
    yield 0.4
    shown = bpy.data.objects[canvas_sync.CANVAS] if canvas_sync._state["canvas_track"] == other.uid else card
    h.check("...the next clip on that track has its own card (at rest: nothing carried over)",
            abs(shown.location.y - base_y) < 1e-4,
            (shown.name, shown.location.y - base_y))
    keys = h.area('DOPESHEET_EDITOR')
    h.check("a keyframes view (Dope Sheet) shows what's keyed", keys is not None
            and keys.spaces.active.ui_mode == 'DOPESHEET')
    sc.frame_current = start_frame
    yield 0.3

    # The 3D camera: moving it keys the SHOT (the clip being drawn on) at the playhead.
    sc.frame_current = 1
    yield 0.2
    first = scene3d.shot_clip(sc)
    cam.location.x = 1.0
    yield 0.3
    sc.frame_current = 25
    yield 0.2
    cam.location.x = 3.0
    cam.data.lens = 50.0
    yield 0.3
    sc.frame_current = 13
    yield 0.3
    h.check("moving the 3D camera keys the shot at the playhead (and plays between keys)",
            first is not None and shots.animated(sc, first, shots.CAM_PROPS) and cam.animation_data is None
            and 1.5 < cam.location.x < 2.5, (first and first.name, cam.location.x))
    sc.frame_current = 25
    yield 0.3
    h.check("...lens too", abs(cam.data.lens - 50.0) < 1e-4, cam.data.lens)

    # Reset (scene view header): the panel being drawn on gets its card back
    # square-on and its camera at rest (Ollie: a panel didn't show; its card
    # had been moved out of the camera's view).
    sheet = bpy.data.objects[canvas_sync.CANVAS]
    rest_y = sheet.location.y
    sheet.location.x += 30.0
    sheet.rotation_euler.z = 1.2
    yield 0.4
    h.check("(the drawn-on panel's card moved off, keyed on it)",
            shots.animated(sc, first, shots.CARD_PROPS) and abs(first.plastron_card_offset[0] - 30.0) < 1e-3,
            tuple(first.plastron_card_offset))
    with h.override('SCENE_3D'):
        bpy.ops.plastron.shot_reset(what='BOTH')
    yield 0.4
    rest_loc, _rest_rot = scene3d.rest_pose()
    h.check("Reset Card and Camera: the card is back square-on in its place, its keys gone",
            not shots.animated(sc, first, shots.CARD_PROPS) and abs(sheet.location.x) < 1e-4
            and abs(sheet.rotation_euler.z) < 1e-4 and abs(sheet.location.y - rest_y) < 1e-4,
            (tuple(sheet.location), tuple(sheet.rotation_euler)))
    h.check("...and the camera at rest, its keys gone (nothing re-keyed)",
            not shots.animated(sc, first, shots.CAM_PROPS) and not first.plastron_cam_set
            and (cam.location - rest_loc).length < 1e-4, tuple(cam.location))
    sc.frame_current = 13
    yield 0.3
    h.check("...it stays put at other frames of the clip", abs(sheet.location.x) < 1e-4
            and (cam.location - rest_loc).length < 1e-4, (sheet.location.x, tuple(cam.location)))
    # Put the camera keys back for the checks below.
    sc.frame_current = 1
    yield 0.2
    cam.location.x = 1.0
    yield 0.3
    sc.frame_current = 25
    yield 0.2
    cam.location.x = 3.0
    cam.data.lens = 50.0
    yield 0.3
    h.redraw()
    yield 0.3
    h.check("the keyframe view lists only this clip's channels",
            keys.spaces.active.dopesheet.filter_text == f"({first.name})", keys.spaces.active.dopesheet.filter_text)

    def key_frames():
        return {(fc.data_path, round(k.co[0])) for fc in shots.scene_fcurves(sc) for k in fc.keyframe_points}

    # Each clip owns its animation (Ollie: "the animation isn't actually stored per clip").
    a0, a1 = clips_mod.start(first), clips_mod.end(first)
    second = panels.create(sc, first.channel, a1, 48)
    canvas_sync.invalidate(sc)
    rest_loc, _rest_rot = scene3d.rest_pose()
    sc.frame_current = a1 + 24
    yield 0.4
    h.check("a camera move keyed in one clip doesn't carry into the next clip",
            (cam.location - rest_loc).length < 1e-4 and abs(cam.data.lens - scene3d.cfg.CAMERA_LENS) < 1e-4,
            (tuple(cam.location), tuple(rest_loc), cam.data.lens))
    sc.frame_current = a1 - 1
    yield 0.3
    h.check("...the clip holds its last keyed pose to its end", abs(cam.location.x - 3.0) < 1e-4, cam.location.x)
    sc.frame_current = a1 + 10
    yield 0.3
    cam.location.y -= 2.0                            # key the second clip
    yield 0.4
    sc.frame_current = 13
    yield 0.3
    h.check("...and keying the next clip leaves the first as it was", 1.5 < cam.location.x < 2.5, cam.location.x)
    # Its keys move with it.
    clips_mod.apply(sc, {second: (a1 + 100, a1 + 148)})
    sc.frame_current = a1 + 110
    yield 0.4
    h.check("moving a clip carries its camera move along",
            abs(cam.location.y - (rest_loc.y - 2.0)) < 1e-4, (cam.location.y, rest_loc.y))
    sc.frame_current = a1 + 10
    yield 0.3
    h.check("...and leaves nothing where it was", (cam.location - rest_loc).length < 1e-4, tuple(cam.location))
    # A split clip: both halves keep the move.
    ripple = h.module("timeline.ripple")
    right = ripple.split(sc, [first], 20)
    canvas_sync.invalidate(sc)
    sc.frame_current = 22
    yield 0.4
    h.check("splitting a clip: both halves keep its animation",
            right and shots.animated(sc, right[0], shots.CAM_PROPS) and 2.5 < cam.location.x < 3.0,
            (right and right[0].name, cam.location.x))
    sc.frame_current = 25
    yield 0.3

    # No keys Ollie didn't make: scrubbing to frames between keys, touching the
    # camera (an update, not a move), switching the active track back and forth.
    before = key_frames()
    for f in (7, 19, 31):
        sc.frame_current = f
        yield 0.2
        cam.data.lens = cam.data.lens                # (an update with nothing moved)
        yield 0.2
    tracks_mod = h.module("timeline.tracks")
    for t in list(tracks_mod.video_tracks(sc)) * 2:
        tracks_mod.set_active(sc, t)
        canvas_sync.invalidate(sc)
        yield 0.3
    after = key_frames()
    h.check("no keys appear by themselves (scrubbing, camera updates, switching the active track)",
            after == before, sorted(after - before)[:6])
    sc.frame_current = 9
    yield 0.2
    cam.location.z += 0.5                           # a real move between keys: keyed
    yield 0.3
    h.check("...a real camera move between keys is keyed",
            any(f == 9 for _p, f in key_frames() - before), sorted(key_frames() - before)[:6])
    h.redraw()
    yield 0.1
    a = location_3d_to_region_2d(cregion, cr3d, card.matrix_world.translation)
    sc.frame_current = 1
    yield 0.3
    h.redraw()
    yield 0.1
    b = location_3d_to_region_2d(cregion, cr3d, card.matrix_world.translation)
    h.check("moving the camera moves what the canvas shows", (a - b).length > 5, (a, b))
    h.redraw()
    yield 0.3
    h.screenshot("scene3d_cards")
    h.redraw()
    yield 0.3
    h.screenshot("scene3d")

    # Moving the pen into the scene view: Object mode; back to the canvas: painting.
    h.move(*centre(view))
    yield 0.3
    h.move(centre(view)[0] + 5, centre(view)[1])
    yield 0.3
    h.check("over the 3D scene: Object mode (Blender's tools work)", bpy.context.mode == 'OBJECT',
            bpy.context.mode)
    h.key('B')
    yield 0.2
    h.check("...and the canvas keys stay out of it (B doesn't start painting)", bpy.context.mode == 'OBJECT')
    rot = space.region_3d.view_rotation.copy()
    c = centre(view)
    yield from h.drag(c, (c[0] + 60, c[1] + 20), alt=True)
    yield 0.2
    h.check("Alt+drag orbits the 3D scene", space.region_3d.view_rotation.rotation_difference(rot).angle > 0.05)
    cam = scene3d.camera(sc)
    h.check("the 3D Camera is drawn big enough to click",
            abs(cam.data.display_size - cfg.CAMERA_DISPLAY_SIZE) < 1e-4, cam.data.display_size)
    h.check("the canvas's flat camera can't be clicked by mistake",
            bpy.data.objects["Canvas Camera"].hide_select)
    with h.override('SCENE_3D'):
        bpy.ops.plastron.scene_select_camera()
    h.check("the scene view's Camera button selects the camera (and only it)",
            cam.select_get() and bpy.context.view_layer.objects.active == cam
            and [o.name for o in bpy.context.selected_objects] == [cam.name],
            [o.name for o in bpy.context.selected_objects])
    h.redraw()
    yield 0.3
    h.screenshot("scene3d_camera_selected")
    # Clicking the camera itself in the scene view selects it too.
    for o in bpy.context.selected_objects:
        o.select_set(False)
    vreg = h.region(view)
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    # a point on the camera's drawing: its frame corner nearest the viewer's side
    frame = [cam.matrix_world @ v for v in cam.data.view_frame(scene=sc)]
    p = location_3d_to_region_2d(vreg, space.region_3d, (frame[0] + frame[1]) / 2)
    h.move(vreg.x + p.x, vreg.y + p.y)
    yield 0.2
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.3
    h.check("clicking the camera in the 3D scene selects it", cam.select_get(),
            [o.name for o in bpy.context.selected_objects])
    h.move(*centre(canvas))
    yield 0.3
    h.move(centre(canvas)[0] + 5, centre(canvas)[1])
    yield 0.3
    h.check("back over the canvas: painting again, on the canvas",
            bpy.context.mode == 'PAINT_TEXTURE'
            and bpy.context.view_layer.objects.active.name == "Canvas", bpy.context.mode)

    # Ctrl+Space maximises the area under the pen, and again goes back.
    h.move(*centre(view))
    yield 0.3
    h.key('SPACE', ctrl=True)
    yield 0.5
    areas = [a.type for a in h.window().screen.areas]
    h.check("Ctrl+Space maximises the 3D scene", areas == ['VIEW_3D'], areas)
    h.screenshot("scene3d_max")
    h.move(*centre(h.window().screen.areas[0]))
    yield 0.2
    h.key('SPACE', ctrl=True)
    yield 0.5
    h.check("...and again puts the layout back", len(h.window().screen.areas) >= 5,
            [a.type for a in h.window().screen.areas])


h.run(steps())
