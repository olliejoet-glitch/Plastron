"""Each clip its own animation timeline: the keyframe view frames the clip
being drawn on (start to end), and moves to the next clip when the playhead
does; outside the clip is dimmed."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

panels = h.module("features.storyboard.panels")
tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
events = h.module("timeline.events")


def span(area):
    r = h.region(area)
    a = r.view2d.region_to_view(0, 0)[0]
    b = r.view2d.region_to_view(r.width, 0)[0]
    return a, b


def steps():
    yield 1.0
    sc = bpy.context.scene
    ch = tracks.channel_of(sc, tracks.video_tracks(sc)[-1])
    first = panels.all_panels(sc)[0]
    clips.apply(sc, {first: (1, 49)})
    second = panels.create(sc, ch, 49, 120)
    events.clips_changed(sc)
    keys = h.area('DOPESHEET_EDITOR')
    h.check("there's a keyframe view", keys is not None)
    sc.frame_current = 10
    yield 0.5
    h.redraw()
    yield 0.5
    a, b = span(keys)
    h.check("the keyframe view shows the clip being drawn on, start to end", abs(a - 1) < 6 and abs(b - 49) < 6, (a, b))
    sc.frame_current = 100
    yield 0.5
    h.redraw()
    yield 0.5
    a, b = span(keys)
    h.check("...and the next clip once the playhead is on it", abs(a - 49) < 10 and abs(b - 169) < 10, (a, b))
    h.screenshot("keys_view")


h.run(steps())
