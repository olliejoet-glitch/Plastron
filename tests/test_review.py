"""Stage 7 (planning and review): shot status (and the clip's colour), panel
notes, framing guides."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.review")
notes = h.module("features.review.notes")
guides = h.module("features.review.guides")
canvas_sync = h.module("features.storyboard.canvas_sync")
user_settings = h.module("core.user_settings")


def steps():
    yield 1.0
    sc = bpy.context.scene
    strip = canvas_sync.panel_on_canvas(sc)
    info = strip.plastron_panel
    h.check("a panel starts as a sketch", info.status == "SKETCH")
    info.status = "BLOCKING"
    h.check("setting its status colours its clip on the timeline",
            strip.color_tag == dict((s, t) for s, _l, t, _h in cfg.STATUS)["BLOCKING"], strip.color_tag)
    info.note = "Slow push in; door creak"
    h.check("panels keep notes", strip.plastron_panel.note == "Slow push in; door creak")
    h.redraw()
    yield 0.3
    h.screenshot("panel_info")

    # Guides: toggles remembered; thirds / safe areas / 9:16 drawn in the frame.
    wm = bpy.context.window_manager
    for gid, _label in cfg.GUIDES:
        setattr(wm, guides._prop_name(gid), True)
    h.check("guides toggle on and are remembered",
            set(user_settings.get("guides")) == {g for g, _l in cfg.GUIDES})
    from mathutils import Vector
    frame = (Vector((0, 0)), Vector((160, 0)), Vector((160, 90)), Vector((0, 90)))
    ls = guides.lines(frame, {"THIRDS"})
    xs = sorted({round(p.x, 3) for _c, pts in ls for p in pts if 0 < p.x < 160})
    h.check("rule of thirds lines at a third and two thirds", xs == [53.333, 106.667], xs)
    short = guides.lines(frame, {"SHORT"})[0][1]
    width = max(p.x for p in short) - min(p.x for p in short)
    h.check("the 9:16 frame is full height, 9/16 of it wide", abs(width - 90 * 9 / 16) < 1e-3, width)
    h.move(*h.center(h.region(h.area('VIEW_3D'))))
    yield 0.5
    h.redraw()
    yield 1.0                         # (through the camera the screen updates on a real redraw)
    h.screenshot("guides")
    for gid, _label in cfg.GUIDES:
        setattr(wm, guides._prop_name(gid), False)
    h.check("...and off again", not guides.shown())


h.run(steps())
