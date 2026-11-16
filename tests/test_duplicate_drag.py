"""Alt+drag a clip: a copy follows the pen and goes where it's dropped
(on a ripple track: in at the nearest cut, later clips move along); a panel
copy has its own painting; Alt+click without moving, or Esc, leaves none."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

panels = h.module("features.storyboard.panels")
tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
events = h.module("timeline.events")


def steps():
    yield 1.0
    sc = bpy.context.scene
    track = tracks.video_tracks(sc)[-1]
    ch = tracks.channel_of(sc, track)
    a = panels.all_panels(sc)[0]
    clips.apply(sc, {a: (1, 49)})
    b = panels.create(sc, ch, 49, 48)
    c = panels.create(sc, ch, 97, 48)
    events.clips_changed(sc)
    for s in clips.all_clips(sc):
        s.select = False
    yield 0.3
    bpy.ops.ed.undo_push(message="Test panels")
    tl = h.area('SEQUENCE_EDITOR')
    reg = h.region(tl)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.5
    na, nb, nc = a.name, b.name, c.name
    on = lambda: sorted(clips.on_channel(bpy.context.scene, ch), key=clips.start)  # noqa: E731
    v2d = reg.view2d

    def at(frame):
        x, y = v2d.view_to_region(frame, ch + 0.5, clip=False)
        return reg.x + x, reg.y + y

    yield from h.drag(at(73), at(73 + 66), steps=12, alt=True)      # B's middle past C's middle
    yield 1.2
    now = on()
    copy = now[-1] if len(now) == 4 else None
    h.check("Alt+drag: a copy of the panel goes in after C; the originals stay put",
            [s.name for s in now[:3]] == [na, nb, nc] and copy is not None
            and (clips.start(copy), clips.end(copy)) == (145, 193)
            and [(clips.start(s), clips.end(s)) for s in now[:3]] == [(1, 49), (49, 97), (97, 145)],
            [(s.name, clips.start(s), clips.end(s)) for s in now])
    orig = bpy.context.scene.sequence_editor.strips_all[nb]
    h.check("...the copy is a panel with its own painting (and its own name)",
            copy is not None and panels.is_panel(copy) and copy.plastron_panel.material is not None
            and copy.plastron_panel.material != orig.plastron_panel.material
            and copy.plastron_panel.uid != orig.plastron_panel.uid and copy.name.startswith("Panel"),
            copy and (copy.name, copy.plastron_panel.material, orig.plastron_panel.material))
    count = len(clips.all_clips(bpy.context.scene))
    yield from h.drag(at(25), at(25), steps=2, alt=True)               # Alt+click, no move
    yield 1.0
    h.check("Alt+click without moving: no copy", len(clips.all_clips(bpy.context.scene)) == count,
            [s.name for s in clips.all_clips(bpy.context.scene)])
    h.move(*at(25))
    yield 0.2
    h.hold_mods({"alt": True}, 'PRESS')
    h._event('LEFTMOUSE', 'PRESS', alt=True)
    yield
    for i in range(6):
        h.move(at(25 + 10 * i)[0], at(25)[1], alt=True)
        yield
    h.key('ESC')
    yield 0.2
    h._event('LEFTMOUSE', 'RELEASE', alt=True)
    h.hold_mods({"alt": True}, 'RELEASE')
    yield 1.0
    h.check("Esc while Alt+dragging: no copy, nothing moved", len(clips.all_clips(bpy.context.scene)) == count
            and [(clips.start(s), clips.end(s)) for s in on()][:3] == [(1, 49), (49, 97), (97, 145)],
            [(s.name, clips.start(s), clips.end(s)) for s in on()])


h.run(steps())
