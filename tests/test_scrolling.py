"""Scrolling the tools area and the script: mouse wheel, and Alt+Shift+drag
(the pen has no wheel), also when the drag starts on a button."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa
import harness as h  # noqa


def steps():
    yield 1.0
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
    yield from h.drag((cx, reg.y + 200), (cx, reg.y + 500), alt=True, shift=True)
    yield 0.3
    top1 = v2d.region_to_view(0, reg.height)[1]
    print("PAN", top0, top1)
    area_t = h.area('TEXT_EDITOR')
    st = area_t.spaces.active
    st.text.from_string("\n".join(f"line {i}" for i in range(300)))
    st.top = 0
    rt = h.region(area_t)
    yield 0.2
    tx = rt.x + rt.width // 2
    yield from h.drag((tx, rt.y + 100), (tx, rt.y + 500), alt=True, shift=True)
    yield 0.3
    print("TEXT", st.top)
    h.check("Alt+Shift+drag scrolls the script", st.top != 0, st.top)
    h.check("Alt+Shift+drag scrolls the tools area", abs(top1 - top0) > 50, (top0, top1))


h.run(steps())
