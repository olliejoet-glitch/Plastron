"""Stage 6: the dot graph, camera moves (set by dragging, eased, shake), the
moved frame on the canvas, Clean View, layer / group motion (shown after
scrubbing, painting still lands where you see it), motion presets, panel
images showing where a panel starts, split panels with their own graphs."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

dot_graph = h.module("widgets.dot_graph")
camera = h.module("features.motion.camera")
layer_motion = h.module("features.motion.layer_motion")
motion_ui = h.module("features.motion.ui")
view_follow = h.module("features.motion.view_follow")
edit = h.module("features.motion.edit")
canvas_frame = h.module("features.storyboard.canvas_frame")
canvas_view = h.module("features.storyboard.canvas_view")
canvas_sync = h.module("features.storyboard.canvas_sync")
panel_cache = h.module("features.storyboard.panel_cache")
panels = h.module("features.storyboard.panels")
pixels = h.module("features.canvas_edit.pixels")
presets = h.module("core.presets")
clips = h.module("timeline.clips")
cfg = h.module("config.motion")


def win(world):
    """World point on the canvas -> window pixel."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area = h.area('VIEW_3D')
    r = h.region(area)
    p = location_3d_to_region_2d(r, area.spaces.active.region_3d, world)
    return r.x + p.x, r.y + p.y


from mathutils import Vector as _V  # noqa: E402


def Vector2(v):
    return _V((v[0], v[1]))


def close(a, b, tol=1e-3):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def steps():
    yield 1.0
    h.flat_canvas()                  # (this test is about the flat canvas / 2D camera)
    yield 0.5
    with h.override('VIEW_3D'):
        bpy.ops.plastron.canvas_fit()
    yield 0.5
    h.redraw()
    sc = bpy.context.scene
    strip = panels.all_panels(sc)[0]
    strip.right_handle = clips.start(strip) + 49          # frames 1..49: t = 0 .. 1
    start, last = clips.start(strip), clips.end(strip) - 1

    # --- the dot graph ------------------------------------------------------------------------
    h.check("a missing graph is a straight line", dot_graph.evaluate("nope", 0.3) == 0.3)
    dot_graph.set_points("test_g", [(0, 0), (0.5, 0.8), (1, 1)])
    h.check("a graph with a point added bends through it",
            abs(dot_graph.evaluate("test_g", 0.5) - 0.8) < 0.01 and len(dot_graph.points("test_g")) == 3)
    copy = dot_graph.copy("test_g")
    dot_graph.set_points(copy, [(0, 0), (1, 1)])
    h.check("a copied graph is its own", len(dot_graph.points("test_g")) == 3)
    for gid in ("test_g", copy):
        dot_graph.remove(gid)

    # --- camera move: the transform box on the frame --------------------------------------
    base = canvas_view.camera_frame(sc)
    h.check("no move yet: the canvas shows the camera's own frame",
            all((a - b).length < 1e-6 for a, b in zip(canvas_frame.shown_frame(bpy.context), base)))
    width = (base[0] - base[3]).length
    centre = sum(base, base[0] * 0) / 4
    area = h.area('VIEW_3D')
    r = h.region(area)
    r3d = area.spaces.active.region_3d
    with h.override('VIEW_3D'):
        bpy.ops.plastron.canvas_zoom(step=-2)              # room around the frame
    yield 0.3
    h.redraw()
    with h.override('VIEW_3D'):
        p = canvas_view.screen_to_world(bpy.context.region, bpy.context.space_data, r3d, 300, 200)
    from bpy_extras.view3d_utils import region_2d_to_location_3d
    q = region_2d_to_location_3d(r, r3d, (300, 200), (0, 0, 0))
    h.check("screen -> canvas maths matches Blender's", abs(p.x - q.x) < 1e-3 and abs(p.z - q.z) < 1e-3,
            (tuple(p), tuple(q)))
    rest_screen = [win(c) for c in base]                   # where the frame sits on screen

    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_set('INVOKE_DEFAULT', target='CAMERA', end='END')
    yield 0.2
    h.check("End jumps the playhead to the panel's last frame", sc.frame_current == last, sc.frame_current)
    sc_mid = Vector2(win(centre))
    yield from h.drag(tuple(sc_mid), tuple(sc_mid + Vector2((150, 0))))     # inside: move
    yield 0.2
    m = strip.plastron_motion
    frame_px = rest_screen[0][0] - rest_screen[3][0]
    h.check("dragging inside the box moves the camera with the hand",
            abs(m.end.x - 150 / frame_px * 100) < 1.5 and abs(m.end.y) < 1.5 and abs(m.end.zoom - 1) < 1e-6,
            camera.as_tuple(m.end))
    h.redraw()
    yield 0.1
    shown_screen = [win(c) for c in canvas_frame.shown_frame(bpy.context)]
    h.check("Camera View: the frame stays put on screen, the drawing moves behind it",
            all(abs(a[0] - b[0]) < 1.5 and abs(a[1] - b[1]) < 1.5 for a, b in zip(shown_screen, rest_screen)),
            (shown_screen, rest_screen))
    corner = Vector2(min(rest_screen))                      # a left corner handle
    yield from h.drag(tuple(corner), tuple(sc_mid + (corner - sc_mid) * 0.5))     # handle: zoom in 2x
    yield 0.2
    h.check("dragging a handle in zooms in", abs(m.end.zoom - 2) < 0.15, m.end.zoom)
    radius = (corner - sc_mid).length * 1.25
    angle = math.radians(20)
    p0 = sc_mid + Vector2((-radius, 0))
    p1 = sc_mid + Vector2((-radius * math.cos(angle), -radius * math.sin(angle)))
    yield from h.drag(tuple(p0), tuple(p1))                 # outside: rotate
    yield 0.2
    h.check("dragging outside rotates (a slight rotation)", abs(math.degrees(m.end.rotation) - 20) < 2,
            math.degrees(m.end.rotation))
    h.redraw()
    yield 0.1
    h.screenshot("camera_edit")
    h.key('TAB')
    yield 0.3
    h.check("Tab swaps to the start (playhead too)", sc.frame_current == start
            and motion_ui.edit.editing() == "CAMERA START")
    h.key('RET')
    yield 0.2
    h.check("Enter keeps it", abs(m.end.zoom - 2) < 0.15 and not motion_ui.edit.editing())

    # The box opens at the nearer end; Esc puts it back.
    sc.frame_current = start + 3
    yield 0.1
    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_set('INVOKE_DEFAULT', target='CAMERA', end='NEAREST')
    yield 0.3
    h.check("the box opens at the nearer end", motion_ui.edit.editing() == "CAMERA START"
            and sc.frame_current == start, motion_ui.edit.editing())
    yield from h.drag(tuple(sc_mid), tuple(sc_mid + Vector2((100, 40))))
    h.key('ESC')
    yield 0.2
    h.check("Esc cancels", close(camera.as_tuple(m.start), camera.REST), camera.as_tuple(m.start))

    # Scrubbing / playing: the frame (and the view, in Camera View) follow.
    sc.frame_current = (start + last) // 2 + 1
    yield
    t = camera.clip_time(strip, sc.frame_current)
    want_state = camera.blend(camera.REST, camera.as_tuple(m.end), t)
    want = camera.corners(base, want_state)
    shown = canvas_frame.shown_frame(bpy.context)
    h.check("halfway through, the frame is halfway (straight easing)",
            all((p - q).length < 1e-4 for p, q in zip(shown, want)))
    h.check("...and the canvas looks through it",
            close(view_follow.applied(r3d), want_state, 1e-5), (view_follow.applied(r3d), want_state))
    h.screenshot("camera_halfway")
    wm = bpy.context.window_manager
    wm.plastron_camera_view = False
    yield 0.1
    h.redraw()
    h.check("Camera View off: the frame moves over the drawing instead",
            close(view_follow.applied(r3d), camera.REST)
            and all(abs(a[0] - b[0]) < 1.5 for a, b in zip([win(c) for c in base], rest_screen)))
    wm.plastron_camera_view = True
    yield 0.1

    # --- camera controls box (canvas corner): no mode to enter --------------------------------
    pad = h.module("features.motion.camera_pad")
    h.redraw()
    parts = pad.layout(r)

    def at(name, fx=0.5, fy=0.5):
        x0, y0, x1, y1 = parts[name]
        return r.x + x0 + (x1 - x0) * fx, r.y + y0 + (y1 - y0) * fy

    h.move(*at("END"))
    yield
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.2
    h.check("the box's End button moves the playhead to the panel's end", sc.frame_current == last,
            sc.frame_current)
    before = camera.as_tuple(m.end)
    yield from h.drag(at("PAD"), (at("PAD")[0] + 100, at("PAD")[1]))
    yield 0.2
    cfg_pad = h.module("config.motion").CAMERA_PAD
    h.check("dragging the pad moves the camera (gently)",
            abs(m.end.x - (before[0] + 100 * cfg_pad["pan_per_px"])) < 1.0 and abs(m.end.y - before[1]) < 1.0,
            (before, camera.as_tuple(m.end)))
    z0 = m.end.zoom
    yield from h.drag(at("ZOOM", 0.3), (at("ZOOM", 0.3)[0] + 50, at("ZOOM")[1]))
    yield 0.2
    h.check("dragging the zoom strip right zooms in",
            abs(m.end.zoom - z0 * math.exp(50 * cfg_pad["zoom_per_px"])) < 0.05, (z0, m.end.zoom))
    r0 = m.end.rotation
    yield from h.drag(at("TURN", 0.3), (at("TURN", 0.3)[0] + 40, at("TURN")[1]))
    yield 0.2
    h.check("dragging the turn strip rotates", abs(math.degrees(m.end.rotation - r0) - 40 * cfg_pad["turn_per_px"]) < 0.5,
            math.degrees(m.end.rotation - r0))
    h.check("...and nothing was painted under the box", not motion_ui.edit.editing())
    h.screenshot("camera_pad")
    pad.reset_part(m.end, "PAD")          # double-click (can't be simulated: Blender times real clicks)
    h.check("double-clicking the pad centres the camera", abs(m.end.x) < 1e-6 and abs(m.end.y) < 1e-6
            and abs(m.end.zoom - 1) > 0.01, camera.as_tuple(m.end))
    camera.set_state(m.end, before)
    yield 0.1

    # Presets: easing + shake.
    with h.override('VIEW_3D'):
        bpy.ops.plastron.preset_apply(kind=motion_ui.CAMERA_KIND, name="Ease in")
    e_mid = dot_graph.evaluate(m.curve, 0.5)
    h.check("Ease in preset: slow start", m.curve and e_mid < 0.3, e_mid)
    names = [p["name"] for p in presets.all_presets(motion_ui.CAMERA_KIND)]
    h.check("camera presets: ease in / out / in-out, overshoot, shake",
            {"Ease in", "Ease out", "Ease in-out", "Overshoot", "Camera shake"} <= set(names), names)
    layer_names = [p["name"] for p in presets.all_presets(motion_ui.LAYER_KIND)]
    h.check("layer presets leave out the shake", "Camera shake" not in layer_names
            and "Overshoot" in layer_names, layer_names)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.preset_apply(kind=motion_ui.CAMERA_KIND, name="Overshoot")
    peak = max(dot_graph.evaluate(m.curve, i / 50) for i in range(51))
    h.check("Overshoot goes past the end and settles", peak > 1.05
            and abs(dot_graph.evaluate(m.curve, 1.0) - 1) < 1e-3, peak)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.preset_apply(kind=motion_ui.CAMERA_KIND, name="Camera shake")
    h.check("Camera shake preset", m.shake > 0, m.shake)
    wob = [camera.shake_offset(strip, f / 24) for f in range(48)]
    h.check("shake: small, moving, the same every time",
            max(abs(w[0]) for w in wob) <= m.shake + 1e-6 and len({round(w[0], 4) for w in wob}) > 20
            and wob == [camera.shake_offset(strip, f / 24) for f in range(48)])
    m.shake = 0.0

    # --- Clean View (F) ----------------------------------------------------------------
    area = h.area('VIEW_3D')
    r = h.region(area)
    h.move(r.x + r.width // 2, r.y + r.height // 2)
    yield
    h.key('F')
    yield 0.3
    wm = bpy.context.window_manager
    h.check("F turns Clean View on", wm.plastron_clean_view)
    h.screenshot("clean_view")
    h.key('F')
    yield 0.2
    h.check("...and off", not wm.plastron_clean_view)

    # --- layer / group motion -------------------------------------------------------------
    mat = strip.plastron_panel.material
    st = mat.plastron_stack
    layer = st.active
    w, hh = st.width, st.height
    img = layer.paint_image
    arr = np.zeros((hh, w, 4), np.float32)
    arr[1000:1040, 1780:1820] = (0, 0, 0, 1)                 # a dot in the middle
    pixels.write(img, arr)
    sc.frame_current = start
    yield
    h.check("the layer's box goes round what's drawn on it",
            edit.layer_bounds(st, layer) == (1756, 976, 1844, 1064), edit.layer_bounds(st, layer))
    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_set('INVOKE_DEFAULT', target='LAYER', end='END')
    yield 0.2
    h.redraw()
    yield 0.1
    sw, sh = canvas_sync.sheet_size(st)
    c = centre.copy()
    c.y = 0
    d = c.copy()
    d.x += sw * 300 / w                                     # 300 canvas px right
    yield from h.drag(win(c), win(d))
    h.redraw()
    yield 0.1
    h.screenshot("layer_box")
    h.key('RET')
    yield 0.2
    h.check("dragging moves the layer's end position", abs(layer.move_end[0] - 300) < 8
            and abs(layer.move_end[1]) < 8 and tuple(layer.move_start) == (0.0, 0.0), tuple(layer.move_end))
    h.check("...and it's shown there at the end", abs(layer.move_now[0] - layer.move_end[0]) < 1e-3)
    h.check("the layer being painted takes strokes where it's shown (UVs follow)",
            close(tuple(st.view_shift), tuple(layer.move_now))
            and abs(bpy.data.objects["Canvas"].data.uv_layers[0].data[0].uv[0] + layer.move_now[0] / w) < 1e-5)
    h.redraw()
    with h.override('VIEW_3D'):
        px = pixels.canvas_point(bpy.context, *[v - o for v, o in zip(win(d), (r.x, r.y))])
    h.check("...and selections / transforms work on its own pixels",
            abs(px[0] - w / 2) < 6 and abs(px[1] - hh / 2) < 6, px)

    # Scrubbing and playback: layers move with the playhead.
    sc.frame_current = (start + last) // 2 + 1
    halfway = camera.clip_time(strip, sc.frame_current) * layer.move_end[0]
    yield
    h.check("scrubbing: the layer shows where it is at the playhead", abs(layer.move_now[0] - halfway) < 0.5,
            (layer.move_now[0], halfway))
    yield cfg.LAYER_REFRESH_DELAY + 0.3
    h.check("...and painting is re-aimed once scrubbing stops", close(tuple(st.view_shift), tuple(layer.move_now)))
    sc.frame_current = start
    yield 0.2
    seen = []
    with h.override('VIEW_3D'):
        bpy.ops.screen.animation_play()
    for _ in range(6):
        yield 0.15
        f = sc.frame_current
        seen.append((f, layer.move_now[0], camera.clip_time(strip, f) * layer.move_end[0],
                     view_follow.applied(r3d)[2]))
    with h.override('VIEW_3D'):
        bpy.ops.screen.animation_cancel(restore_frame=False)
    yield 0.3
    moving = [x for x in seen if x[0] > start + 1]
    h.check("playback: the layer moves with the playhead",
            len({x[0] for x in moving}) >= 2 and all(abs(x[1] - x[2]) < 0.5 for x in moving), seen)
    h.check("playback: the canvas looks through the moving camera",
            len({round(x[3], 4) for x in moving}) >= 2, [x[3] for x in seen])

    # A group moves everything in it; the layer painted stays aligned.
    sc.frame_current = (start + last) // 2 + 1
    yield 0.3
    with h.override('VIEW_3D'):
        bpy.ops.plastron.layer_group()
    yield 0.2
    group = st.by_uid(st.layers[st.active_index].parent_uid) if st.active.layer_type != "GROUP" else st.active
    group.move_start = (0.0, 0.0)
    group.move_end = (0.0, 200.0)
    layer_motion.refresh(sc)
    child = next(l for l in st.layers if l.parent_uid == group.uid)
    sc_t = camera.clip_time(strip, sc.frame_current)
    lt = h.module("layers.layer_trees")
    shown = lt.shown_offset(child, st)
    h.check("a moving group carries its layers", abs(shown[1] - 200 * sc_t - child.move_now[1]) < 0.5 and abs(shown[0] - halfway) < 0.5,
            shown)
    st.active_index = list(st.layers).index(child)
    yield 0.1
    h.check("...and painting one of them still lines up", close(tuple(st.view_shift), shown, 1e-3),
            (tuple(st.view_shift), shown))
    h.screenshot("layer_motion")

    # Panel image: where the panel starts (layers at their start, the camera's start frame).
    m.end.zoom = 1.0
    camera.set_state(m.start, (0.0, 0.0, 2.0, 0.0))
    crop, offsets, _para = panel_cache.view(strip, st)
    fx, fy, fw, fh = panel_cache.frame_crop(st)
    h.check("the panel's image uses the camera's start frame", abs(crop[2] - fw / 2) < 1e-3
            and abs(crop[0] - (fx + fw / 4)) < 1e-3, crop)
    h.check("...and the layers where they start", all(o == (0.0, 0.0) for o in offsets.values()))
    panel_cache.request(mat)
    panel_cache.flush_now()

    # Undo of a typed change: the shown position follows.
    # Split: each half gets its own easing graph.
    sc.frame_current = start + 10
    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_curve(target='LAYER')
    for s in clips.all_clips(sc):
        s.select = s == strip
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.clip_split()
    yield 0.3
    halves = [s for s in panels.all_panels(sc) if s.plastron_motion.curve]
    h.check("split panels each get their own camera graph",
            len(halves) == 2 and halves[0].plastron_motion.curve != halves[1].plastron_motion.curve,
            [s.plastron_motion.curve for s in halves])
    graphs = [l.move_curve for s in panels.all_panels(sc) if s.plastron_panel.material
              for l in s.plastron_panel.material.plastron_stack.layers if l.move_curve]
    h.check("...and their layers too", len(graphs) == 2 and len(set(graphs)) == 2, graphs)

    # Reset takes it all off.
    sc.frame_current = start
    yield 0.3
    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_reset(target='CAMERA')
    s0 = canvas_sync.panel_on_canvas(sc)
    h.check("Reset: no camera move", s0 is not None and not camera.moves(s0))

    # The painting grows to fit the camera move (Ollie couldn't paint where the
    # camera had panned past its edge).
    s0 = canvas_sync.panel_on_canvas(sc)
    mat0 = s0.plastron_panel.material
    st0 = mat0.plastron_stack
    w_before, h_before = st0.width, st0.height
    lay0 = next(l for l in st0.layers if l.layer_type == 'PAINT' and l.paint_image)
    a0 = pixels.array(lay0.paint_image)
    ys, xs = np.nonzero(a0[..., 3] > 0.5)
    centre_before = (xs.mean() - w_before / 2, ys.mean() - h_before / 2) if len(xs) else None
    camera.set_state(s0.plastron_motion.start, (-40.0, 0.0, 1.0, 0.0))
    yield h.module("config.motion").CANVAS_FIT["delay"] + 1.5
    st0 = s0.plastron_panel.material.plastron_stack
    sheet_half = canvas_sync.sheet_size(st0)[0] / 2
    reach = width * (0.40 + 0.5)
    h.check("the painting grows to cover the camera move", st0.width > w_before and sheet_half >= reach,
            (w_before, st0.width, sheet_half, reach))
    h.check("...keeping the frame the same size", tuple(canvas_sync.frame_px(st0)) == (2880, 1620),
            tuple(canvas_sync.frame_px(st0)))
    lay0 = next(l for l in st0.layers if l.layer_type == 'PAINT' and l.paint_image)
    a1 = pixels.array(lay0.paint_image)
    ys, xs = np.nonzero(a1[..., 3] > 0.5)
    centre_after = (xs.mean() - st0.width / 2, ys.mean() - st0.height / 2) if len(xs) else None
    h.check("...and the drawing where it was", centre_before is not None and centre_after is not None
            and abs(centre_before[0] - centre_after[0]) < 1.5 and abs(centre_before[1] - centre_after[1]) < 1.5,
            (centre_before, centre_after))
    canvas_obj = bpy.data.objects["Canvas"]
    h.check("...and the canvas sheet is that big", abs(canvas_obj.scale.x * canvas_sync.sheet_size()[0] / 2
                                                   - sheet_half) < 1e-3, tuple(canvas_obj.scale))
    camera.set_state(s0.plastron_motion.start, camera.REST)
    yield 0.2

    # The Motion panel draws (tools area).
    h.redraw()
    yield 0.3
    h.screenshot("motion_panel")


h.run(steps())
