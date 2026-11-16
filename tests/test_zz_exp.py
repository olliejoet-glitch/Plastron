import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa
import harness as h  # noqa
tracks = h.module("timeline.tracks")
ops = h.module("timeline.ops")
th = h.module("timeline.track_headers")


def steps():
    yield 1.0
    sc = bpy.context.scene
    tl = h.area('SEQUENCE_EDITOR')
    ch = h.region(tl, 'CHANNELS')
    hits = []
    real = ops.PLASTRON_OT_track_header_click.invoke
    def spy(self, context, event):
        hits.append((event.mouse_region_x, event.value))
        return real(self, context, event)
    ops.PLASTRON_OT_track_header_click.invoke = spy
    bg = next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == "Background")
    y0, y1 = th.row_span(tl, ch, tracks.channel_of(sc, bg))
    for x in (3, 8, 14, 20, 40, 80, 120):
        hits.clear()
        h.move(ch.x + x, ch.y + int((y0 + y1) / 2))
        yield 0.1
        h._event('LEFTMOUSE', 'PRESS')
        yield 0.1
        h._event('LEFTMOUSE', 'RELEASE')
        yield 0.2
        print("EXP x", x, "op got", hits, "width", ch.width, flush=True)
    h.check("exp", True)


h.run(steps())
