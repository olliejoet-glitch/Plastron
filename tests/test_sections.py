"""The timeline shows only tracks: video above, audio below, each section
tinted, a line between them; Blender's other channels are covered over
(Ollie: no "Channel 5 / 6 / 7" rows above the tracks)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

tracks = h.module("timeline.tracks")
sections = h.module("timeline.sections")
headers = h.module("timeline.track_headers")


def grab(name):
    path = h.screenshot(name)
    img = bpy.data.images.load(path, check_existing=False)
    w, hh = img.size
    px = np.empty(w * hh * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(hh, w, 4)[:, :, :3]          # (row 0 = the bottom, like Blender)


def steps():
    yield 1.0
    sc = bpy.context.scene
    found, top = sections.spans(sc)
    kinds = [t.kind for t in tracks.all_tracks(sc)]
    h.check("tracks in order: audio at the bottom, video on top",
            kinds == sorted(kinds, key=lambda k: k == 'VIDEO') and 'VIDEO' in found and 'AUDIO' in found, kinds)
    tl = h.area('SEQUENCE_EDITOR')
    main = h.region(tl)
    chan = h.region(tl, 'CHANNELS')
    # Scroll so several empty channels show above the top track.
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.view2d.pan(deltax=0, deltay=int(main.view2d.view_to_region(0, top + 1, clip=False)[1]
                                                   - main.height * 0.4))
    h.redraw()
    yield 0.5
    px = grab("sections")
    v2d = main.view2d
    y_empty = int(v2d.view_to_region(0, top + 2.5, clip=False)[1])
    h.check("there's room above the top track to look at", 0 < y_empty < main.height, y_empty)
    xp = int(v2d.view_to_region(sc.frame_current, 0, clip=False)[0])
    row = px[main.y + y_empty, main.x + max(10, xp + 20): main.x + main.width - 30]
    h.check("timeline: no channel rows above the tracks (one flat colour)", float(row.std(axis=0).max()) < 0.01,
            float(row.std(axis=0).max()))
    band = px[main.y + y_empty - 8: main.y + y_empty + 8, chan.x + 4: chan.x + chan.width - 4]
    h.check("channel column: no 'Channel n' names / buttons there", float(band.std(axis=(0, 1)).max()) < 0.01,
            float(band.std(axis=(0, 1)).max()))
    play = px[main.y + y_empty, main.x + xp - 2: main.x + xp + 3]
    h.check("...the playhead line still shows there", float(play.max(axis=0).max() - row.mean(axis=0).max()) > 0.1,
            play)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.view2d.pan(deltax=0, deltay=-int(main.height * 0.45))
    h.redraw()
    yield 0.5
    px = grab("sections_lines")
    xm = main.x + main.width // 2
    lines = []
    for ch_line in (found['AUDIO'][1] + 1, found['SCRIPT'][1] + 1):      # audio | script | video
        y_line = int(v2d.view_to_region(0, ch_line, clip=False)[1])
        lines.append(px[main.y + y_line, xm] if 0 < y_line < main.height else None)
    h.check("light lines between the audio tracks, the Script lane and the video tracks",
            all(l is not None and float(l.mean()) > 0.55 for l in lines), lines)
    yv = int(v2d.view_to_region(0, found['VIDEO'][0] + 0.5, clip=False)[1])
    ys = int(v2d.view_to_region(0, found['SCRIPT'][0] + 0.5, clip=False)[1])
    ya = int(v2d.view_to_region(0, found['AUDIO'][1] + 0.5, clip=False)[1])
    xs = main.x + 6
    hv, hs, ha = px[main.y + yv, xs], px[main.y + ys, xs], px[main.y + ya, xs]
    h.check("video, script and audio rows are tinted differently",
            min(float(np.abs(a - b).max()) for a, b in ((hv, hs), (hs, ha), (hv, ha))) > 0.01, (hv, hs, ha))
    h.screenshot("sections_all")


h.run(steps())
