"""Search the script (features/storyboard/script_search): matches found case-
blind, the first from the cursor selected and scrolled to, next / previous
wrap round, Ctrl+F over the script opens the search box ready to type."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

ss = h.module("features.storyboard.script_search")


def steps():
    yield 1.0
    h.check("matches: case-blind, every one, in order",
            ss.matches(["Moon jellies", "", "the moon and the MOON"], "moon")
            == [(0, 0, 4), (2, 4, 8), (2, 17, 21)])
    h.check("...nothing for an empty search", ss.matches(["a"], "") == [])
    found = [(0, 0, 4), (2, 4, 8), (2, 17, 21)]
    h.check("pick: the first at / after the cursor", ss.pick(found, (1, 0), 0) == 1)
    h.check("...next wraps round to the first", ss.pick(found, (2, 17), 1) == 0)
    h.check("...previous wraps round to the last", ss.pick(found, (0, 0), -1) == 2)

    text = bpy.data.texts["Script"]
    lines = [f"Line {n} about nothing much." for n in range(60)]
    lines[45] = "Scattered moon jellies scrape by."
    lines[50] = "The Moon again."
    text.from_string("\n\n".join(lines))          # (lines kept a blank line apart)
    text.cursor_set(0, character=0)
    area = h.area('TEXT_EDITOR')
    space = area.spaces.active
    space.top = 0
    yield 0.3
    wm = bpy.context.window_manager
    wm.plastron_script_find = "moon"
    yield 0.3
    h.check("typing a search selects the first match from the cursor",
            (text.current_line_index, text.select_end_line_index) == (90, 90)
            and sorted((text.current_character, text.select_end_character)) == [10, 14],
            (text.current_line_index, text.current_character, text.select_end_character))
    h.check("...and scrolls it into view", space.top > 40, space.top)
    with h.override('TEXT_EDITOR'):
        bpy.ops.plastron.script_find_step(step=1)
    h.check("the down arrow goes to the next match", text.current_line_index == 100, text.current_line_index)
    with h.override('TEXT_EDITOR'):
        bpy.ops.plastron.script_find_step(step=1)
    h.check("...and wraps round", text.current_line_index == 90, text.current_line_index)
    with h.override('TEXT_EDITOR'):
        bpy.ops.plastron.script_find_step(step=-1)
    h.check("the up arrow goes back", text.current_line_index == 100, text.current_line_index)
    found = ss._found(text, "moon")
    h.check("the count knows which match is selected", ss.current(text, found) == 1, ss.current(text, found))
    h.redraw()
    yield 0.3
    h.screenshot("script_search")

    # Ctrl+F over the script: the search box opens, ready to type.
    wm.plastron_script_find = ""
    reg = h.region(area)
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    h.key('F', ctrl=True)
    yield 0.5
    h.type_text("again")
    yield 0.3
    h.screenshot("script_search_box")
    h.key('RET')
    yield 0.3
    h.check("Ctrl+F opens a search box you type straight into",
            wm.plastron_script_find == "again", wm.plastron_script_find)
    h.check("...which finds it", text.current_line_index == 100, text.current_line_index)
    h.key('ESC')
    yield 0.3


h.run(steps())
