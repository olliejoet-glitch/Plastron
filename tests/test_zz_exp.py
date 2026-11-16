import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa
import harness as h  # noqa
tracks = h.module("timeline.tracks")
th = h.module("timeline.track_headers")
panels = h.module("features.storyboard.panels")
events = h.module("timeline.events")
cs = h.module("features.storyboard.canvas_sync")


def steps():
    yield 1.0
    sc = bpy.context.scene
    tl = h.area('SEQUENCE_EDITOR')
    chan = h.region(tl, 'CHANNELS')
    by = lambda n: next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == n)  # noqa
    bg = by("Background")
    panels.create(sc, tracks.channel_of(sc, bg), 1, 48)
    events.clips_changed(sc)
    yield 0.5
    obj = bpy.data.objects.get(cs.DISPLAY_PREFIX + bg.uid)
    print("EXP before", obj and obj.hide_viewport, flush=True)
    y0, y1 = th.row_span(tl, chan, tracks.channel_of(sc, bg))
    for x in range(chan.width - 50, chan.width - 2, 4):
        h.move(chan.x + x, chan.y + int((y0 + y1) / 2))
        yield 0.05
        h._event('LEFTMOUSE', 'PRESS')
        h._event('LEFTMOUSE', 'RELEASE')
        yield 0.4
        ch = sc.sequence_editor.channels[tracks.channel_of(sc, bg)]
        print("EXP x", x, "mute", ch.mute, "lock", ch.lock, "sheet hidden", obj.hide_viewport, flush=True)
        if ch.mute:
            yield 1.0
            print("EXP later sheet hidden", obj.hide_viewport, flush=True)
            h._event('LEFTMOUSE', 'PRESS')
            h._event('LEFTMOUSE', 'RELEASE')
            yield 1.0
            print("EXP unmuted", ch.mute, "sheet hidden", obj.hide_viewport, flush=True)
            break
    top = by("Panels")
    y0, y1 = th.row_span(tl, chan, tracks.channel_of(sc, top))
    h.move(chan.x + 229, chan.y + int((y0 + y1) / 2))
    yield 0.1
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 1.0
    ch = sc.sequence_editor.channels[tracks.channel_of(sc, top)]
    cv = cs.canvas_object(sc)
    print("EXP panels mute", ch.mute, "canvas mat", cv.material_slots[0].material.name, "canvas track", cs._state["canvas_track"] == top.uid, flush=True)
    h.check("exp", True)


h.run(steps())
