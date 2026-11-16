"""Ripple for whole-clip drags: on a ripple track the gap a dragged clip
leaves closes, and it goes in at the cut nearest where it's dropped (later
clips move along); linked sounds follow; other tracks keep Blender's way."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

rm = h.module("timeline.ripple_move")
panels = h.module("features.storyboard.panels")
tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
events = h.module("timeline.events")


def plan_checks():
    old = {"A": (4, 1, 49), "B": (4, 49, 97), "C": (4, 97, 145), "V": (2, 1, 300)}
    out = rm.plan(old, {"B": (4, 49 + 77)}, {}, {4, 2}, set(), {})
    h.check("plan: B dropped over C's second half -> after C, the gap closed (A C B)",
            out == {"B": (4, 97, 145), "C": (4, 49, 97)}, out)
    out = rm.plan(old, {"C": (4, -13)}, {}, {4, 2}, set(), {})
    h.check("plan: C's middle dropped over A's first half -> before A (C A B)",
            out == {"C": (4, 1, 49), "A": (4, 49, 97), "B": (4, 97, 145)}, out)
    out = rm.plan(old, {"A": (4, 200)}, {}, {4}, set(), {})
    h.check("plan: dropped into empty space: it keeps its distance from the clip before it; the gap closes",
            out == {"A": (4, 152, 200), "B": (4, 1, 49), "C": (4, 49, 97)}, out)
    old2 = {"A": (4, 1, 49), "M": (4, 49, 97), "Ms": (1, 49, 97), "C": (4, 97, 145), "Cs": (1, 97, 145)}
    links = {"M": ["Ms"], "Ms": ["M"], "C": ["Cs"], "Cs": ["C"]}
    out = rm.plan(old2, {"M": (4, 49 + 80)}, {"Ms": ("M", 1)}, {4}, set(), links)
    h.check("plan: a video's sound goes with it, and the sound of the clip moving up too",
            out == {"M": (4, 97, 145), "Ms": (1, 97, 145), "C": (4, 49, 97), "Cs": (1, 49, 97)}, out)
    out = rm.plan(old, {"B": (4, 126)}, {}, set(), set(), {})
    h.check("plan: no ripple on the track: nothing (Blender's own result stays)", out == {}, out)


def drag_clip(sc, strip, frames, reg, ch, keep_selection=False):
    if not keep_selection:                   # (as after a click on empty space)
        for s in clips.all_clips(sc):
            s.select = False
    v2d = reg.view2d
    x0, y0 = v2d.view_to_region(clips.start(strip) + clips.length(strip) / 2, ch + 0.5, clip=False)
    x1, _ = v2d.view_to_region(clips.start(strip) + clips.length(strip) / 2 + frames, ch + 0.5, clip=False)
    yield from h.drag((reg.x + x0, reg.y + y0), (reg.x + x1, reg.y + y0), steps=12)
    yield 1.0


def steps():
    yield 1.0
    plan_checks()
    sc = bpy.context.scene
    track = tracks.video_tracks(sc)[-1]
    ch = tracks.channel_of(sc, track)
    a = panels.all_panels(sc)[0]
    clips.apply(sc, {a: (1, 49)})
    b = panels.create(sc, ch, 49, 48)
    c = panels.create(sc, ch, 97, 48)
    events.clips_changed(sc)
    yield 0.3
    bpy.ops.ed.undo_push(message="Test panels")
    tl = h.area('SEQUENCE_EDITOR')
    reg = h.region(tl)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.5
    names = lambda: [s.name for s in sorted(clips.on_channel(bpy.context.scene, ch), key=clips.start)]  # noqa: E731
    spans = lambda: [(clips.start(s), clips.end(s)) for s in sorted(clips.on_channel(bpy.context.scene, ch), key=clips.start)]  # noqa: E731
    yield from drag_clip(sc, b, 66, reg, ch)            # B's middle onto C's second half
    h.check("dragging a panel past the next one on a ripple track swaps them, no gap",
            names() == [a.name, c.name, b.name] and spans() == [(1, 49), (49, 97), (97, 145)],
            (names(), spans()))
    na, nb, nc = a.name, b.name, c.name
    h.key('Z', ctrl=True)
    yield 1.0
    sc = bpy.context.scene
    a, b, c = (sc.sequence_editor.strips_all[n] for n in (na, nb, nc))
    h.check("...one Ctrl+Z puts it back", names() == [na, nb, nc] and spans()[1] == (49, 97),
            (names(), spans()))
    yield from drag_clip(sc, c, -110, reg, ch)          # C onto A's first half
    h.check("dragging a panel to the front: it goes in first, the rest move along",
            names() == [c.name, a.name, b.name] and spans() == [(1, 49), (49, 97), (97, 145)],
            (names(), spans()))
    # Several clips at once: Shift+click two, then drag one of them: both go.
    sc = bpy.context.scene
    a, b, c = (sc.sequence_editor.strips_all[n] for n in (na, nb, nc))
    order0 = names()
    first, second = sorted([a, b, c], key=clips.start)[:2]
    for s_ in clips.all_clips(sc):
        s_.select = False
    for strip, shift in ((first, False), (second, True)):
        x, y = reg.view2d.view_to_region(clips.start(strip) + clips.length(strip) / 2, ch + 0.5, clip=False)
        h.move(reg.x + x, reg.y + y)
        yield 0.1
        if shift:
            h._event('LEFT_SHIFT', 'PRESS')
            h._event('LEFTMOUSE', 'PRESS', shift=True)
            h._event('LEFTMOUSE', 'RELEASE', shift=True)
            h._event('LEFT_SHIFT', 'RELEASE')
        else:
            h._event('LEFTMOUSE', 'PRESS')
            h._event('LEFTMOUSE', 'RELEASE')
        yield 0.3
    picked = [s_.name for s_ in clips.all_clips(sc) if s_.select]
    h.check("Shift+click picks two clips", sorted(picked) == sorted([first.name, second.name]), picked)
    yield from drag_clip(sc, first, 120, reg, ch, keep_selection=True)   # drag the first past the third
    h.check("dragging one of two selected clips moves both (the third closes up, they go in after it)",
            names() == [order0[2], order0[0], order0[1]] and spans() == [(1, 49), (49, 97), (97, 145)],
            (names(), spans(), order0))

    track = tracks.video_tracks(sc)[-1]
    track.ripple = False
    before = spans()
    yield from drag_clip(sc, sc.sequence_editor.strips_all[names()[1]], 200, reg, ch)   # the middle one
    h.check("ripple off: Blender's own drag (the gap stays)", spans()[0] == before[0] and spans()[1] == before[2],
            (spans(), before))


h.run(steps())
