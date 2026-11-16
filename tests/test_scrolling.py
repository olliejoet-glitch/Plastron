"""Scrolling the tools area and the script: mouse wheel, and Alt+Shift+drag
(the pen has no wheel), also when the drag starts on a button."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa
import harness as h  # noqa


def steps():
    yield 1.0
    h.flat_canvas()                  # (the tools area is longest with the 2D camera panel)
    yield 0.5
    area = h.area('PROPERTIES')
    reg = h.region(area)
    v2d = reg.view2d
    top0 = v2d.region_to_view(0, reg.height)[1]
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield
    for _ in range(6):
        h._event('WHEELDOWNMOUSE', 'PRESS')
        yield 0.05
    yield 0.3
    top1 = v2d.region_to_view(0, reg.height)[1]
    print("SCROLL", top0, top1)
    h.check("wheel scrolls the tools area", top1 < top0 - 5, (top0, top1))
    h.screenshot("tools_area_scrolled")
    # Can a button there be clicked? Pencil button test via Motion header collapse
    for _ in range(6):
        h._event('WHEELUPMOUSE', 'PRESS')
        yield 0.05
    yield 0.3
    h.screenshot("tools_area")
    top0 = v2d.region_to_view(0, reg.height)[1]
    cx = reg.x + reg.width // 2
    yield from h.drag((cx, reg.y + 200), (cx, reg.y + 260), alt=True, shift=True)
    yield 0.3
    top1 = v2d.region_to_view(0, reg.height)[1]
    print("PAN", top0, top1)
    h.check("...at the speed of the hand (60 px drag = 60 px scroll)", abs((top0 - top1) - 60) < 8,
            top0 - top1)
    area_t = h.area('TEXT_EDITOR')
    st = area_t.spaces.active
    st.text.from_string("\n".join(f"line {i}" for i in range(300)))
    st.top = 0
    rt = h.region(area_t)
    yield 0.2
    tx = rt.x + rt.width // 2
    yield from h.drag((tx, rt.y + 100), (tx, rt.y + 300), alt=True, shift=True)
    yield 0.3
    print("TEXT", st.top)
    h.check("Alt+Shift+drag scrolls the script", st.top != 0, st.top)
    h.check("Alt+Shift+drag scrolls the tools area", abs(top1 - top0) > 50, (top0, top1))

    # The script follows the playhead with long (wrapped) lines: the line
    # played is always on screen, and scrolling by hand stays put while paused.
    st.text.from_string("\n".join(f"Line {i} is a fairly long sentence that wraps in the narrow script panel."
                                   for i in range(40)))
    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_panels()
    yield 0.5
    sc = bpy.context.scene
    follow = h.module("features.voice.script_follow")
    off = []
    for f in range(1, 1800, 41):
        sc.frame_current = f
        yield 0.02
        line = follow._now["line"]
        if line is None:
            continue
        y = st.region_location_from_cursor(line, 0)[1]
        if not 0 < y <= rt.height:
            off.append((f, line, st.top, y))
    h.check("playing / scrubbing keeps the line being played on screen (wrapped lines)", not off, off[:5])
    yield from h.drag((tx, rt.y + 100), (tx, rt.y + 300), alt=True, shift=True)
    yield 0.2
    top = st.top
    yield 1.0
    h.check("...and a hand scroll stays put while paused", st.top == top, (top, st.top))


h.run(steps())
