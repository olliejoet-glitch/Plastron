"""Track cards in depth (Ollie: "if I add a new video track, it should appear
as a card either closer to or further away from the camera depending on
where it is in the list"): the top track in the picture plane, each lower
one further back, scaled so it still fills the camera's frame; painting a
card further back works; the flat canvas keeps them flat."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.scene3d")
scene3d = h.module("features.scene3d")
cs = h.module("features.storyboard.canvas_sync")
panels = h.module("features.storyboard.panels")
tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
events = h.module("timeline.events")


def sheet(sc, track):
    if cs._state["canvas_track"] == track.uid:
        return cs.canvas_object(sc)
    return bpy.data.objects.get(cs.DISPLAY_PREFIX + track.uid)


def frame_box(sc, obj):
    """The sheet's corners as seen by the 3D camera (0..1 = the frame)."""
    cam = scene3d.camera(sc)
    pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    uv = [world_to_camera_view(sc, cam, p)[:2] for p in pts]
    return np.round(np.array(sorted(tuple(p) for p in uv)), 4)


def steps():
    yield 1.0
    h.add_background()
    yield 0.5
    sc = bpy.context.scene
    names = {tracks.name(sc, t): t for t in tracks.all_tracks(sc)}
    top, bg = names["Panels"], names["Background"]
    first = panels.all_panels(sc)[0]
    panels.create(sc, tracks.channel_of(sc, bg), clips.start(first), clips.length(first))
    events.clips_changed(sc)
    yield 0.5
    a, b = sheet(sc, top), sheet(sc, bg)
    d = -scene3d.rest_pose()[0].y
    h.check("the top track's card is the picture plane; the one below stands TRACK_SPACING back",
            abs(a.location.y) < 1e-4 and abs(b.location.y - cfg.TRACK_SPACING) < 1e-4,
            (a.location.y, b.location.y))
    h.check("...scaled up so it fills the frame from the camera's spot",
            abs(b.scale.x / a.scale.x - (d + cfg.TRACK_SPACING) / d) < 1e-4, (a.scale.x, b.scale.x))
    h.check("...both fill the camera's frame the same", np.allclose(frame_box(sc, a), frame_box(sc, b), atol=2e-3),
            (frame_box(sc, a), frame_box(sc, b)))

    # A new video track goes on top: in the picture plane, the others step back.
    new = tracks.add(sc, 'VIDEO', "Foreground")
    yield 0.5
    ys = [round(sheet(sc, t).location.y, 3) for t in (new, top, bg) if sheet(sc, t) is not None]
    h.check("a new video track's card is nearest; the others move back a step each",
            ys[-2:] == [round(cfg.TRACK_SPACING, 3), round(2 * cfg.TRACK_SPACING, 3)], ys)

    # Painting on the card further back.
    tracks.set_active(sc, bg)
    events.active_track_changed(sc)
    yield 0.8
    canvas = cs.canvas_object(sc)
    h.check("drawing on the Background track: the canvas sheet is its card, further back",
            abs(canvas.location.y - 2 * cfg.TRACK_SPACING) < 1e-4, canvas.location.y)
    img = sc.tool_settings.image_paint.canvas
    before = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(before)
    view = h.region(h.area('VIEW_3D'))
    cx, cy = view.x + view.width // 2, view.y + view.height // 2
    h.move(cx, cy)
    yield 0.3
    yield from h.drag((cx - 80, cy), (cx + 80, cy + 20), steps=10)
    yield 1.0
    after = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(after)
    h.check("...a stroke there lands on its painting", int((after[3::4] > before[3::4] + 0.1).sum()) > 50,
            int((after[3::4] > before[3::4] + 0.1).sum()))
    h.redraw()
    yield 0.3
    h.screenshot("card_depth")

    # The flat canvas: all flat again.
    bpy.context.window_manager.plastron_canvas_3d = False
    yield 0.8
    ys = [abs(sheet(sc, t).location.y) for t in (new, top, bg) if sheet(sc, t) is not None]
    h.check("flat canvas (3D Camera off): the cards are flat again", max(ys) < 0.1, ys)
    bpy.context.window_manager.plastron_canvas_3d = True
    yield 0.5


h.run(steps())
