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


def close(a, b, tol=1e-3):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def steps():
    yield 1.0
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

    # --- camera move: drag the end frame ----------------------------------------------------
    base = canvas_view.camera_frame(sc)
    h.check("no move yet: the canvas shows the camera's own frame",
            canvas_frame.shown_frame(bpy.context) == base or
            all((a - b).length < 1e-6 for a, b in zip(canvas_frame.shown_frame(bpy.context), base)))
    width = (base[0] - base[3]).length
    centre = sum(base, base[0] * 0) / 4
    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_set('INVOKE_DEFAULT', target='CAMERA', end='END')
    yield 0.2
    h.check("End jumps the playhead to the panel's last frame", sc.frame_current == last, sc.frame_current)
    shift = centre.copy()
    shift.x += width * 0.2
    yield from h.drag(win(centre), win(shift))             # inside: move
    yield 0.1
    m = strip.plastron_motion
    h.check("dragging inside the frame pans it", abs(m.end.x - 20) < 1.5 and abs(m.end.y) < 1.5
            and abs(m.end.zoom - 1) < 1e-6, camera.as_tuple(m.end))
    c_now = camera.corners(base, camera.as_tuple(m.end))
    corner = min(c_now, key=lambda c: c.x)                 # a left corner (the right ones are off screen)
    mid = sum(c_now, c_now[0] * 0) / 4
    half = mid + (corner - mid) * 0.5
    yield from h.drag(win(corner), win(half))               # corner: zoom in 2x
    yield 0.1
    h.check("dragging a corner zooms", abs(m.end.zoom - 2) < 0.15, m.end.zoom)
    radius, angle = width * 0.45, math.radians(20)
    p0 = mid.copy()
    p0.x -= radius
    p1 = mid.copy()
    p1.x -= radius * math.cos(angle)
    p1.z -= radius * math.sin(angle)
    yield from h.drag(win(p0), win(p1))                      # outside: rotate
    yield 0.1
    h.check("dragging outside rotates (a slight rotation)", abs(math.degrees(m.end.rotation) - 20) < 2,
            math.degrees(m.end.rotation))
    h.screenshot("camera_edit")
    h.key('RET')
    yield 0.2
    h.check("Enter keeps it", abs(m.end.zoom - 2) < 0.15 and not motion_ui.edit.editing())

    # Esc puts it back.
    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_set('INVOKE_DEFAULT', target='CAMERA', end='START')
    yield 0.2
    h.check("Start jumps to the panel's first frame", sc.frame_current == start)
    yield from h.drag(win(centre), win(shift))
    h.key('ESC')
    yield 0.2
    h.check("Esc cancels", close(camera.as_tuple(m.start), camera.REST), camera.as_tuple(m.start))

    # The frame on the canvas follows the playhead (worked out as it draws).
    sc.frame_current = (start + last) // 2 + 1
    yield
    t = camera.clip_time(strip, sc.frame_current)
    want = camera.corners(base, camera.blend(camera.REST, camera.as_tuple(m.end), t))
    shown = canvas_frame.shown_frame(bpy.context)
    h.check("halfway through, the frame is halfway (straight easing)",
            all((p - q).length < 1e-4 for p, q in zip(shown, want)))
    h.screenshot("camera_halfway")

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
    with h.override('VIEW_3D'):
        bpy.ops.plastron.motion_set('INVOKE_DEFAULT', target='LAYER', end='END')
    yield 0.2
    sw, sh = canvas_sync.sheet_size()
    c = centre.copy()
    c.y = 0
    d = c.copy()
    d.x += sw * 300 / w                                     # 300 canvas px right
    yield from h.drag(win(c), win(d))
    h.key('RET')
    yield 0.2
    h.check("dragging moves the layer's end position", abs(layer.move_end[0] - 300) < 8
            and abs(layer.move_end[1]) < 8 and tuple(layer.move_start) == (0.0, 0.0), tuple(layer.move_end))
    h.check("...and it's shown there at the end", abs(layer.move_now[0] - layer.move_end[0]) < 1e-3)
    h.check("the layer being painted takes strokes where it's shown (UVs follow)",
            close(tuple(st.view_shift), tuple(layer.move_now))
            and abs(bpy.data.objects["Canvas"].data.uv_layers[0].data[0].uv[0] + layer.move_now[0] / w) < 1e-5)
    with h.override('VIEW_3D'):
        px = pixels.canvas_point(bpy.context, *[v - o for v, o in zip(win(d), (r.x, r.y))])
    h.check("...and selections / transforms work on its own pixels",
            abs(px[0] - w / 2) < 6 and abs(px[1] - hh / 2) < 6, px)

    # Scrubbing: shown once scrubbing stops (a short timer); never during playback.
    sc.frame_current = (start + last) // 2 + 1
    halfway = camera.clip_time(strip, sc.frame_current) * layer.move_end[0]
    yield cfg.LAYER_REFRESH_DELAY + 0.3
    h.check("scrubbing: the layer shows where it is at the playhead", abs(layer.move_now[0] - halfway) < 0.5,
            (layer.move_now[0], halfway))

    # A group moves everything in it; the layer painted stays aligned.
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
    h.check("a moving group carries its layers", abs(shown[1] - 200 * sc_t) < 0.5 and abs(shown[0] - halfway) < 0.5,
            shown)
    st.active_index = list(st.layers).index(child)
    yield 0.1
    h.check("...and painting one of them still lines up", close(tuple(st.view_shift), shown, 1e-3),
            (tuple(st.view_shift), shown))
    h.screenshot("layer_motion")

    # Panel image: where the panel starts (layers at their start, the camera's start frame).
    m.end.zoom = 1.0
    camera.set_state(m.start, (0.0, 0.0, 2.0, 0.0))
    crop, offsets = panel_cache.view(strip, st)
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

    # The Motion panel draws (tools area).
    h.redraw()
    yield 0.3
    h.screenshot("motion_panel")


h.run(steps())
