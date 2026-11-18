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
    lines_mod = h.module("features.voice.script_lines")
    h.redraw()
    yield 0.2
    with h.override('TEXT_EDITOR'):
        row_h = st.font_size * bpy.context.preferences.system.ui_scale * h.module("config.voice").SCRIPT_FOLLOW["row"]
        bands = lines_mod.bands(st, rt, st.text, row_h)
    h.check("script lines told apart: every other one tinted, a clear blank line between them",
            len(bands) >= 3 and [b[3] for b in bands[:4]] in ([False, True, False, True], [True, False, True, False])
            and all(b[0] == a[0] + 2 and a[2] > b[1] + 5 for a, b in zip(bands, bands[1:])),
            bands[:4])
    h.screenshot("script_lines")
    yield from h.drag((tx, rt.y + 100), (tx, rt.y + 300), alt=True, shift=True)
    yield 0.2
    top = st.top
    yield 1.0
    h.check("...and a hand scroll stays put while paused", st.top == top, (top, st.top))

    # Ctrl+Alt+drag scrolls the script too (Ollie's other drag).
    st.top = 0
    yield 0.2
    yield from h.drag((tx, rt.y + 100), (tx, rt.y + 300), ctrl=True, alt=True)
    yield 0.3
    h.check("Ctrl+Alt+drag scrolls the script", st.top > 0, st.top)
    # While Blender smooth-scrolls (scrollbar / middle-drag) the marks drawn
    # over the text are left out (they'd sit half a line off), then come back.
    link = h.module("features.voice.script_link")
    h.move(tx, rt.y + 200)
    yield 0.2
    h._event('MIDDLEMOUSE', 'PRESS')
    yield
    h.move(tx, rt.y + 230)
    yield 0.1
    with h.override('TEXT_EDITOR'):
        during = link.scrolling(bpy.context)
    h._event('MIDDLEMOUSE', 'RELEASE')
    yield 0.3
    with h.override('TEXT_EDITOR'):
        after = link.scrolling(bpy.context)
    h.check("smooth scrolling is spotted while it runs (marks hidden), and ends", during and not after,
            (during, after, [o.bl_idname for o in bpy.context.window.modal_operators]))

    # A project reopened (Ollie's file: the script was drawn from Blender's old
    # cached layout of the wrapped lines, so the band / scrolling were rows
    # off): the layout is redone on load and before every follow scroll,
    # without moving the text cursor or the selection.
    path = os.path.join(bpy.app.tempdir, "scroll_reopen.blend")
    st.text.cursor_set(5, character=3)
    st.text.cursor_set(7, character=2, select=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    yield 0.5
    bpy.ops.wm.open_mainfile(filepath=path)
    yield 2.0
    sc = bpy.context.scene
    area_t = h.area('TEXT_EDITOR')
    st = area_t.spaces.active
    rt = h.region(area_t)
    txt = st.text
    sel = (txt.current_line_index, txt.current_character, txt.select_end_line_index, txt.select_end_character)
    called = []
    real = follow.refresh_layout
    follow.refresh_layout = lambda t: called.append(t.name) or real(t)
    sc.frame_current = 1700
    yield 0.5
    follow.refresh_layout = real
    line = follow._now["line"]
    y = st.region_location_from_cursor(line, 0)[1] if line is not None else None
    after = (txt.current_line_index, txt.current_character, txt.select_end_line_index, txt.select_end_character)
    h.check("after reopening a project the script's layout is redone before it scrolls to the line",
            called and y is not None and 0 < y <= rt.height, (called, line, y))
    h.check("...the text cursor and selection stay where they were", sel == after, (sel, after))
    h.redraw()
    yield 0.5
    h.screenshot("script_reopened")


h.run(steps())
