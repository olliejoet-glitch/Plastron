"""Drag a track's header to move the whole track: clips, name, mute / lock,
ripple and its 3D card keys go with it; video stays above audio; a plain
click on the header doesn't move anything."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
th = h.module("timeline.track_headers")
panels = h.module("features.storyboard.panels")
events = h.module("timeline.events")


def steps():
    yield 1.0
    h.add_background()
    yield 0.5
    sc = bpy.context.scene
    tl = h.area('SEQUENCE_EDITOR')
    chan = h.region(tl, 'CHANNELS')
    names = lambda: [tracks.name(bpy.context.scene, t) for t in tracks.all_tracks(bpy.context.scene)]  # noqa: E731
    by = lambda n: next(t for t in tracks.all_tracks(bpy.context.scene) if tracks.name(bpy.context.scene, t) == n)  # noqa: E731
    h.check("starting tracks (bottom up)", names() == ["Music", "Voice", "Script", "Background", "Panels"], names())
    panel = panels.all_panels(sc)[0]
    bg = by("Background")
    bg_panel = panels.create(sc, tracks.channel_of(sc, bg), 1, 24)
    bg.ripple = True
    events.clips_changed(sc)
    panel.plastron_card_offset = (0.0, 1.0, 0.0)          # (a 3D card key on the clip)
    panel.keyframe_insert("plastron_card_offset", frame=1)
    yield 0.3
    bpy.ops.ed.undo_push(message="Test setup")

    def row_mid(name):
        y0, y1 = th.row_span(tl, chan, tracks.channel_of(bpy.context.scene, by(name)))
        return chan.x + 60, chan.y + int((y0 + y1) / 2)

    # A plain click on a header moves nothing.
    h.move(*row_mid("Background"))
    yield 0.1
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.3
    h.check("clicking a header doesn't move tracks", names() == ["Music", "Voice", "Script", "Background", "Panels"], names())

    # Drag Background above Panels.
    start, end = row_mid("Background"), row_mid("Panels")
    yield from h.drag(start, (end[0], end[1] + 10), steps=10)
    yield 0.6
    sc = bpy.context.scene
    h.check("dragging Background's header above Panels moves the track", names() == ["Music", "Voice", "Script", "Panels", "Background"],
            names())
    bg = by("Background")
    h.check("...its clips, its ripple go with it",
            bg_panel.channel == tracks.channel_of(sc, bg) and panel.channel == tracks.channel_of(sc, by("Panels"))
            and bg.ripple, (bg_panel.channel, panel.channel, tracks.channel_of(sc, bg)))
    shots = h.module("features.scene3d.shots")
    h.check("...its clips' 3D card keys go with them",
            shots.animated(sc, panel, shots.CARD_PROPS) and abs(panel.plastron_card_offset[1] - 1.0) < 1e-6,
            tuple(panel.plastron_card_offset))
    h.key('Z', ctrl=True)
    yield 0.8
    h.check("one Ctrl+Z puts it back", names() == ["Music", "Voice", "Script", "Background", "Panels"], names())

    # Video can't go among the audio tracks.
    start, end = row_mid("Background"), row_mid("Music")
    yield from h.drag(start, end, steps=10)
    yield 0.6
    h.check("a video track dragged down stops at the bottom of the video tracks",
            names() == ["Music", "Voice", "Script", "Background", "Panels"], names())
    start, end = row_mid("Music"), row_mid("Voice")
    yield from h.drag(start, (end[0], end[1] + 10), steps=10)
    yield 0.6
    h.check("audio tracks move among themselves", names() == ["Voice", "Music", "Script", "Background", "Panels"], names())
    h.redraw()
    yield 0.3
    h.screenshot("track_drag")


h.run(steps())
