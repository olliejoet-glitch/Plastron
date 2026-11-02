"""The 3D scene view under the script: layout, its camera, Blender's tools
and gizmos, painting / Object mode following the pen, canvas keys staying
out of it, Ctrl+Space maximise, Alt+drag orbit."""

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
    h.check("...perspective, away from the canvas, Blender's toolbar and navigation gizmo",
            space.region_3d.view_perspective == 'PERSP' and space.show_region_toolbar
            and space.show_gizmo_navigate and space.show_region_header
            and (space.region_3d.view_location - cam.location).length < 50)
    shelf = h.region(view, 'ASSET_SHELF')
    h.check("no brush shelf strip under it", shelf is None or shelf.height <= 1, shelf and shelf.height)
    h.check("new objects land in the 3D scene", (sc.cursor.location - cam.location).length < 50)
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
