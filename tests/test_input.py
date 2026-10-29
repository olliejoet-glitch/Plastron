"""Presses the real shortcuts and drags the mouse (simulated input) and checks
what happens: tools, brush size, canvas navigation, painting, undo, playback,
typing in the script, timeline pan/zoom/scrub."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

canvas_view = h.module("features.storyboard.canvas_view")
tools = h.module("features.storyboard.tools")


def r3d():
    return h.area('VIEW_3D').spaces.active.region_3d


def frame_px():
    h.redraw()
    region = h.region(h.area('VIEW_3D'))
    return canvas_view.frame_size_px(region, r3d(), canvas_view.camera_frame(bpy.context.scene))


def layer_image():
    return bpy.data.objects["Canvas"].active_material.plastron_stack.active.paint_image


def stroke_count():
    """Painted pixels on the active layer (the test's measure of "a stroke")."""
    img = layer_image()
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    return int((px[3::4] > 0.05).sum())


def tool_now():
    with h.override('VIEW_3D'):
        return tools.active_tool_id(bpy.context)


def brush_size():
    ip = bpy.context.scene.tool_settings.image_paint
    ups = ip.unified_paint_settings
    return ups.size if ups.use_unified_size else ip.brush.size


def steps():
    yield 1.5
    canvas = h.area('VIEW_3D')
    cx, cy = h.center(h.region(canvas))
    h.move(cx, cy)
    yield

    # --- Tools (Photoshop keys) ---------------------------------------------
    for key, shift, tool in [('E', False, 'ERASER'), ('G', False, 'FILL'), ('B', True, 'BLUR'),
                             ('S', True, 'SMUDGE'), ('B', False, 'PENCIL')]:
        h.key(key, shift=shift)
        yield 0.2
        name = ("Shift+" if shift else "") + key
        h.check(f"{name} picks {tool.lower()}", tool_now() == tool, tool_now())
    h.check("still in paint mode after B", bpy.context.object.mode == 'TEXTURE_PAINT')
    brush = bpy.context.scene.tool_settings.image_paint.brush
    h.check("B picks a paint brush, not the eraser", brush.blend == 'MIX', brush.blend)

    before = brush_size()
    h.key('W')
    yield
    bigger = brush_size()
    h.key('Q')
    yield
    h.check("W makes the brush bigger", bigger > before, (before, bigger))
    h.check("Q makes it smaller again", h.close(brush_size(), before, 0.05), (bigger, brush_size()))

    # --- Painting + undo ----------------------------------------------------
    n = stroke_count()
    yield from h.drag((cx - 150, cy), (cx + 150, cy + 60))
    yield 0.3
    painted = stroke_count()
    h.check("dragging with the pencil paints on the layer", painted > n + 100, (n, painted))
    h.key('Z', ctrl=True)
    yield 0.5
    h.check("Ctrl+Z undoes the stroke", stroke_count() == n, stroke_count())
    h.key('Z', ctrl=True, shift=True)
    yield 0.5
    h.check("Ctrl+Shift+Z redoes it", stroke_count() == painted, stroke_count())

    # Eraser takes paint away; B brings the pencil back.
    h.key('E')
    yield 0.2
    yield from h.drag((cx - 150, cy), (cx + 150, cy + 60))
    yield 0.3
    h.check("the eraser removes paint", stroke_count() < painted * 0.5, (painted, stroke_count()))
    h.key('Z', ctrl=True)
    yield 0.5
    h.key('B')
    yield 0.2

    # Alt+click picks the colour under the mouse. (It reads the screen, which
    # is black under the test display, so only check that it picked.)
    ups = bpy.context.scene.tool_settings.image_paint.unified_paint_settings
    owner = ups if ups.use_unified_color else bpy.context.scene.tool_settings.image_paint.brush
    owner.color = (1.0, 0.0, 0.0)
    h.move(cx - 300, cy - 200)              # bare paper
    yield
    h.key('LEFTMOUSE', alt=True)
    yield 0.3
    picked = tuple(owner.color)
    h.check("Alt+click picks a colour", picked != (1.0, 0.0, 0.0), picked)
    owner.color = (0.0, 0.0, 0.0)
    h.screenshot("painted")

    # --- Canvas view --------------------------------------------------------
    h.move(cx, cy)
    h.key('ZERO', ctrl=True)
    yield 0.3
    region = h.region(canvas)
    w, hgt = frame_px()
    fits = max(w / region.width, hgt / region.height)
    h.check("Ctrl+0 fits the frame to the canvas", abs(fits - 0.9) < 0.02, fits)

    h.key('ONE', ctrl=True)
    yield 0.3
    target = bpy.context.scene.render.resolution_x * bpy.context.scene.render.resolution_percentage / 100
    h.check("Ctrl+1 shows 100 % (preview pixels = screen pixels)",
            abs(frame_px()[0] - target) < 2, (frame_px()[0], target))

    h.key('ZERO', ctrl=True)
    yield 0.2
    dist = r3d().view_distance
    h.key('EQUAL', ctrl=True)
    yield 0.2
    h.check("Ctrl+= zooms in", r3d().view_distance < dist, (dist, r3d().view_distance))
    h.key('MINUS', ctrl=True)
    yield 0.2
    h.check("Ctrl+- zooms back out", h.close(r3d().view_distance, dist), (dist, r3d().view_distance))

    h.move(cx, cy)
    h._event('WHEELUPMOUSE', 'PRESS')
    yield 0.2
    h.check("mouse wheel zooms", r3d().view_distance < dist, r3d().view_distance)

    # Pan: Alt+Shift+drag (Ollie's emulate-3-button pan). Must not draw.
    h.key('ZERO', ctrl=True)
    yield 0.2
    loc = r3d().view_location.copy()
    n = stroke_count()
    yield from h.drag((cx, cy), (cx + 200, cy + 100), alt=True, shift=True)
    yield 0.3
    h.check("Alt+Shift+drag pans the canvas", (r3d().view_location - loc).length > 0.5,
            (loc, r3d().view_location))
    h.check("...without drawing", stroke_count() == n)

    # Zoom: Ctrl+Alt+drag.
    dist = r3d().view_distance
    yield from h.drag((cx, cy), (cx + 150, cy + 150), ctrl=True, alt=True)
    yield 0.3
    h.check("Ctrl+Alt+drag zooms the canvas", not h.close(r3d().view_distance, dist),
            (dist, r3d().view_distance))
    h.check("...without drawing", stroke_count() == n)

    # Rotate: hold R and move; snaps back on release.
    h.key('ZERO', ctrl=True)
    yield 0.2
    rot = r3d().view_rotation.copy()
    h.move(cx + 200, cy)
    yield
    h._event('R', 'PRESS')
    yield 0.2
    for i in range(1, 7):
        h.move(cx + 200 - i * 30, cy + i * 30)
        yield
    turned = r3d().view_rotation.rotation_difference(rot).angle
    h.check("holding R and moving rotates the view", turned > 0.3, turned)
    h._event('R', 'RELEASE')
    yield 0.3
    back = r3d().view_rotation.rotation_difference(rot).angle
    h.check("releasing R snaps the view back", back < 1e-4, back)

    # Flip view: Ctrl+F mirrors the view, again restores. Painting untouched.
    h.move(cx, cy)
    n = stroke_count()
    h.key('F', ctrl=True)
    yield 0.2
    flipped = r3d().view_rotation.rotation_difference(rot).angle
    h.key('F', ctrl=True)
    yield 0.2
    h.check("Ctrl+F flips the view", abs(flipped - 3.14159) < 0.01, flipped)
    same = all(abs(a - b) < 1e-4 for ra, rb in zip(r3d().view_rotation.to_matrix(), rot.to_matrix())
               for a, b in zip(ra, rb))
    h.check("Ctrl+F twice restores it", same)
    h.check("flipping doesn't change the painting", stroke_count() == n)

    # --- Playback -----------------------------------------------------------
    h.move(cx, cy)
    h.key('SPACE')
    yield 0.5
    h.check("Space plays", bpy.context.screen.is_animation_playing)
    h.key('SPACE')
    yield 0.3
    h.check("Space pauses", not bpy.context.screen.is_animation_playing)

    # --- Script panel: typing, including Space, goes into the text ----------
    script = h.area('TEXT_EDITOR')
    sx, sy = h.center(h.region(script))
    h.move(sx, sy)
    yield
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield
    h.type_text("Hi there")
    yield 0.3
    body = bpy.data.texts["Script"].as_string()
    h.check("typing in the script panel works (Space types a space)", "Hi there" in body, repr(body))
    h.check("...and Space there doesn't start playback", not bpy.context.screen.is_animation_playing)

    # --- Timeline: scrub, pan, zoom ----------------------------------------
    timeline = h.area('SEQUENCE_EDITOR')
    treg = h.region(timeline)
    tx, ty = h.center(treg)
    # The ruler is the strip along the top of the timeline.
    h.move(treg.x + treg.width // 2, treg.y + treg.height - 8)
    yield
    h._event('LEFTMOUSE', 'PRESS')
    yield
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.3
    h.check("clicking the ruler moves the playhead", bpy.context.scene.frame_current > 20,
            bpy.context.scene.frame_current)

    def view_x():
        return treg.view2d.region_to_view(0, 0)[0], treg.view2d.region_to_view(treg.width, 0)[0]

    start = view_x()
    yield from h.drag((tx, ty), (tx - 200, ty), alt=True, shift=True)
    yield 0.3
    panned = view_x()
    h.check("Alt+Shift+drag pans the timeline", abs(panned[0] - start[0]) > 1, (start, panned))
    span = panned[1] - panned[0]
    h.move(tx, ty)
    h.key('EQUAL', ctrl=True)
    yield 0.5
    zoomed = view_x()
    h.check("Ctrl+= zooms the timeline in", (zoomed[1] - zoomed[0]) < span * 0.95,
            (span, zoomed[1] - zoomed[0]))
    span = zoomed[1] - zoomed[0]
    yield from h.drag((tx, ty), (tx + 200, ty + 100), ctrl=True, alt=True)
    yield 0.5
    dragged = view_x()
    h.check("Ctrl+Alt+drag zooms the timeline", abs((dragged[1] - dragged[0]) - span) > 1,
            (span, dragged[1] - dragged[0]))

    h.screenshot("after_input")


h.run(steps())
