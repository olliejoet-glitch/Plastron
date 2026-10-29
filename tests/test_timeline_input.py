"""Timeline with simulated mouse and keys: drag clip edges (ripple, snapping),
track header buttons, volume drag, N / Ctrl+K / Delete / I / O, undo, the
Slice tool (S / A)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
track_headers = h.module("timeline.track_headers")
panels = h.module("features.storyboard.panels")
edit_tools = h.module("timeline.edit_tools")


def scene():
    return bpy.context.scene


def track(name):
    return next(t for t in tracks.all_tracks(scene()) if tracks.name(scene(), t) == name)


def ch(name):
    return tracks.channel_of(scene(), track(name))


def span(strip):
    return (clips.start(strip), clips.end(strip))


def tl_region():
    return h.region(h.area('SEQUENCE_EDITOR'))


def at(frame, channel):
    """Window pixel of (frame, middle of channel) in the timeline."""
    r = tl_region()
    x, y = r.view2d.view_to_region(frame, channel + 0.5, clip=False)
    return r.x + x, r.y + y


def header_widget(track_name, wid):
    h.redraw()
    region = h.region(h.area('SEQUENCE_EDITOR'), 'CHANNELS')
    index = tracks.all_tracks(scene()).index(track(track_name))
    for i, w, (x0, y0, x1, y1) in track_headers.widgets(h.area('SEQUENCE_EDITOR'), region, scene()):
        if i == index and w == wid:
            return region, (region.x + (x0 + x1) / 2, region.y + (y0 + y1) / 2), (x0, x1)
    return region, None, None


def steps():
    yield 1.0
    sc = scene()
    p1 = panels.all_panels(sc)[0]

    # Show frames 1-300 with the tracks in view.
    sc.frame_end = 300
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.anim.scene_range_frame()
    r = tl_region()
    v2d = r.view2d
    yield 0.3

    # --- N adds panels (over the timeline and over the canvas) ----------------------
    tx, ty = at(10, ch("Panels"))
    h.move(tx, ty)
    h.key('N')
    yield 0.3
    h.check("N over the timeline adds a panel", len(panels.all_panels(sc)) == 2)
    cx, cy = h.center(h.region(h.area('VIEW_3D')))
    h.move(cx, cy)
    h.key('N')
    yield 0.3
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("N over the canvas adds one too", len(ps) == 3 and [span(p) for p in ps] ==
            [(1, 49), (49, 97), (97, 145)], [span(p) for p in ps])
    p1, p2, p3 = ps

    # --- Ctrl+Z undoes it -----------------------------------------------------------------
    h.key('Z', ctrl=True)
    yield 0.5
    sc = scene()   # undo reloads project data
    h.check("Ctrl+Z undoes adding a panel", len(panels.all_panels(sc)) == 2, len(panels.all_panels(sc)))
    h.key('Z', ctrl=True, shift=True)
    yield 0.5
    sc = scene()   # undo reloads project data
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("Ctrl+Shift+Z redoes it", len(ps) == 3)
    p1, p2, p3 = ps

    # --- Drag a clip edge (Panels has ripple on) --------------------------------------------
    sc.frame_current = 300           # keep the playhead out of the way
    yield
    start = at(49, ch("Panels"))
    end = at(61, ch("Panels"))
    yield from h.drag((start[0] - 1, start[1]), end)
    yield 0.3
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("dragging a panel's end retimes it, ripple pushes the rest",
            [span(p) for p in ps] == [(1, 61), (61, 109), (109, 157)], [span(p) for p in ps])

    h.key('Z', ctrl=True)
    yield 0.5
    sc = scene()   # undo reloads project data
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("Ctrl+Z undoes the trim", [span(p) for p in ps] == [(1, 49), (49, 97), (97, 145)],
            [span(p) for p in ps])

    # Grabbing the edge from a little inside the clip ripples too (Blender used to
    # take that grab itself and resize without ripple).
    ps = sorted(panels.all_panels(sc), key=clips.start)
    start = at(49, ch("Panels"))
    yield from h.drag((start[0] - 12, start[1]), at(60, ch("Panels")))
    yield 0.3
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("grabbing an edge from inside the clip ripples the rest",
            clips.end(ps[0]) > 52 and clips.start(ps[1]) == clips.end(ps[0])
            and clips.length(ps[1]) == 48, [span(p) for p in ps])
    h.key('Z', ctrl=True)
    yield 0.5
    sc = scene()

    # --- Snapping to the playhead -----------------------------------------------------------
    sc.frame_current = 70
    yield
    px_per_frame = 1.0 / abs(v2d.region_to_view(1, 0)[0] - v2d.region_to_view(0, 0)[0])
    near = 70 + 4 / px_per_frame      # 4 px from the playhead: within snapping range
    start = at(49, ch("Panels"))
    end = at(near, ch("Panels"))
    yield from h.drag((start[0] - 1, start[1]), end)
    yield 0.3
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("snapping is off by default", clips.end(ps[0]) == round(near), (span(ps[0]), near))
    h.key('Z', ctrl=True)
    yield 0.5
    sc = scene()
    sc.frame_current = 70            # (undo put the playhead back too)
    yield
    yield from h.drag((start[0] - 1, start[1]), end, ctrl=True)
    yield 0.3
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("holding Ctrl snaps the edge to the playhead", clips.end(ps[0]) == 70, span(ps[0]))
    h.key('Z', ctrl=True)
    yield 0.5
    sc = scene()   # undo reloads project data

    # --- Ctrl+K splits, Delete deletes ----------------------------------------------------
    sc.frame_current = 20
    for s in clips.all_clips(sc):
        s.select = False
    h.move(*at(20, ch("Panels")))
    h.key('K', ctrl=True)
    yield 0.3
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("Ctrl+K splits the panel under the playhead", len(ps) == 4 and span(ps[0]) == (1, 20), [span(p) for p in ps])
    for s in clips.all_clips(sc):
        s.select = False
    ps[0].select = True
    h.key('DEL')
    yield 0.3
    ps = sorted(panels.all_panels(sc), key=clips.start)
    h.check("Delete removes the selected clip and closes the gap (ripple)",
            len(ps) == 3 and span(ps[0]) == (1, 30), [span(p) for p in ps])

    # --- I / O set the loop range ---------------------------------------------------------
    sc.frame_current = 12
    h.move(*at(12, ch("Panels")))
    h.key('I')
    yield 0.2
    sc.frame_current = 40
    yield
    h.key('O')
    yield 0.2
    h.check("I and O set the loop range",
            (sc.use_preview_range, sc.frame_preview_start, sc.frame_preview_end) == (True, 12, 40),
            (sc.use_preview_range, sc.frame_preview_start, sc.frame_preview_end))

    # --- Track headers -------------------------------------------------------------------
    region, pos, _ = header_widget("Background", "RIPPLE")
    h.check("Background track shows a ripple button", pos is not None)
    before = track("Background").ripple
    h.move(*pos)
    yield
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.2
    h.check("clicking R toggles the track's ripple", track("Background").ripple != before)

    region, pos, _ = header_widget("Music", "SOLO")
    h.move(*pos)
    yield
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.2
    h.check("clicking S solos an audio track", track("Music").solo)

    region, pos, (x0, x1) = header_widget("Voice", "VOLUME")
    left = (region.x + x0 + 1, pos[1])
    quarter = (region.x + x0 + (x1 - x0) * 0.25, pos[1])
    yield from h.drag(left, quarter)
    yield 0.2
    h.check("dragging the volume bar sets the track volume (bar = 0-200 %)",
            abs(track("Voice").volume - 0.5) < 0.08, track("Voice").volume)

    # Clicking a track's name makes it the active track.
    name_x = region.x + 20
    _r, pos, _ = header_widget("Background", "RIPPLE")
    h.move(name_x, pos[1])
    yield
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.2
    h.check("clicking a track header makes it active", tracks.active(sc).uid == track("Background").uid)

    # Dragging the middle of a clip moves it (Blender's own move, with snapping).
    bgp = panels.create(sc, ch("Background"), 150, 30)
    sc.frame_current = 300
    yield 0.2
    mid = at(165, ch("Background"))
    yield from h.drag(mid, at(185, ch("Background")))
    yield 0.4
    h.check("dragging a clip's middle moves it", clips.start(bgp) != 150 and clips.length(bgp) == 30
            and bgp.channel == ch("Background"), span(bgp))

    # Lock (Blender's own lock button) stops edits on that track.
    clips.editor(sc).channels[ch("Panels")].lock = True
    ps = sorted(panels.all_panels(sc), key=clips.start)
    before = span(ps[0])
    start = at(clips.end(ps[0]), ch("Panels"))
    yield from h.drag((start[0] - 1, start[1]), (start[0] + 60, start[1]))
    yield 0.3
    h.check("a locked track's clips can't be dragged", span(ps[0]) == before, span(ps[0]))
    clips.editor(sc).channels[ch("Panels")].lock = False

    # --- Slice tool: S, click a clip to cut it there; A back to moving -------------
    def tool():
        with h.override('SEQUENCE_EDITOR'):
            return edit_tools.active_tool(bpy.context)

    sc.frame_current = 300
    ps = sorted(panels.all_panels(sc), key=clips.start)
    target = ps[0]
    a0, a1 = span(target)
    cut = (a0 + a1) // 2 + 3
    h.move(*at(cut, ch("Panels")))
    yield
    h.key('S')
    yield 0.2
    h.check("S switches the timeline to the Slice tool", tool() == 'SLICE', tool())
    h.move(*at(cut, ch("Panels")))
    yield 0.2
    h.check("with Slice on, moving over the timeline shows where it would cut",
            edit_tools._hover["area"] == h.area('SEQUENCE_EDITOR').as_pointer())
    h.screenshot("slice_preview")
    n = len(panels.all_panels(sc))
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.4
    after = sorted(panels.all_panels(sc), key=clips.start)
    h.check("clicking a clip with Slice cuts it where you clicked",
            len(after) == n + 1 and span(after[0]) == (a0, cut) and span(after[1]) == (cut, a1),
            [span(p) for p in after])
    h.check("...each half keeps its own painting",
            after[1].plastron_panel.material not in (None, after[0].plastron_panel.material))
    h.check("...and nothing moved", clips.start(bgp) != 150 and clips.length(bgp) == 30)
    # A drag with Slice only cuts where it starts; nothing gets moved.
    edges = {e for p in after for e in span(p)}
    yield from h.drag(at(cut + 5, ch("Panels")), at(cut + 25, ch("Panels")))
    yield 0.3
    now = {e for p in panels.all_panels(sc) for e in span(p)}
    h.check("dragging with Slice doesn't move clips", now == edges | {cut + 5}, sorted(now ^ edges))
    h.key('A')
    yield 0.2
    h.check("A switches back to moving / resizing clips", tool() == 'MOVE', tool())
    h.screenshot("timeline_input")


h.run(steps())
