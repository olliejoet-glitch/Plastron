"""The 3D scene view under the script: layout, the panels as cards (moving
a card moves its track), the 3D camera (square-on at rest, keys itself
when moved), Blender's tools and gizmos, painting / Object mode following
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
    h.check("...perspective, Blender's toolbar and navigation gizmo",
            space.region_3d.view_perspective == 'PERSP' and space.show_region_toolbar
            and space.show_gizmo_navigate and space.show_region_header)
    shelf = h.region(view, 'ASSET_SHELF')
    h.check("no brush shelf strip under it", shelf is None or shelf.height <= 1, shelf and shelf.height)
    loc, rot = scene3d.rest_pose()
    h.check("the camera starts square-on, framing the picture exactly",
            (cam.location - loc).length < 1e-4 and abs(cam.data.lens - cfg.CAMERA_LENS) < 1e-6
            and abs(abs(cam.location.y) - 16 * cam.data.lens / 36) < 1e-4)
    h.check("the canvas's flat camera is drawn tiny in the 3D scene", sc.camera.data.display_size < 0.051)

    # Cards: a panel on another track shows as its own card; moving it back moves the track.
    panels = h.module("features.storyboard.panels")
    tracks = h.module("timeline.tracks")
    canvas_sync = h.module("features.storyboard.canvas_sync")
    videos = tracks.video_tracks(sc)
    active = canvas_sync._state["canvas_track"]
    other = next(t for t in videos if t.uid != active)
    panels.create(sc, tracks.channel_of(sc, other), sc.frame_current, 48)
    canvas_sync.invalidate(sc)
    yield 0.3
    card = bpy.data.objects[canvas_sync.DISPLAY_PREFIX + other.uid]
    h.check("a panel on another track is a card in the 3D scene", not card.hide_viewport and not card.hide_select)
    base_y = card.location.y
    card.location.y = base_y + 4.0
    card.scale = card.scale * 1.5
    yield 0.3
    h.check("moving a card back moves its track (kept on the track)",
            abs(other.place_offset[1] - 4.0) < 1e-4 and abs(other.place_scale - 1.5) < 1e-4,
            (tuple(other.place_offset), other.place_scale))
    canvas_sync.invalidate(sc)
    yield 0.2
    h.check("...and the canvas keeps it there", abs(card.location.y - (base_y + 4.0)) < 1e-4)

    # The 3D camera keys itself when moved (location / rotation / lens), at the playhead.
    sc.frame_current = 1
    yield 0.2
    cam.location.x = 1.0
    yield 0.3
    sc.frame_current = 25
    yield 0.2
    cam.location.x = 3.0
    cam.data.lens = 50.0
    yield 0.3
    sc.frame_current = 13
    yield 0.3
    h.check("moving the 3D camera keys it at the playhead (and plays between keys)",
            cam.animation_data is not None and 1.5 < cam.location.x < 2.5, cam.location.x)
    sc.frame_current = 25
    yield 0.3
    h.check("...lens too", abs(cam.data.lens - 50.0) < 1e-4, cam.data.lens)
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
