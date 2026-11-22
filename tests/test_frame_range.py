"""The project's range set by hand (Ollie: "I need to be able to set the
frame range myself"): Shift+I / Shift+O at the playhead, or the header's
fields; it then stays put when clips change; Auto follows the clips again."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402


def steps():
    yield 1.0
    scene = bpy.context.scene
    tl = scene.plastron_timeline
    h.check("the range follows the clips at first", tl.range_auto)
    area = h.area('SEQUENCE_EDITOR')
    reg = h.region(area)
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    scene.frame_current = 10
    yield 0.2
    h.key('I', shift=True)
    yield 0.3
    scene.frame_current = 30
    yield 0.2
    h.key('O', shift=True)
    yield 0.3
    scene = bpy.context.scene
    tl = scene.plastron_timeline
    h.check("Shift+I / Shift+O set the project's start / end at the playhead",
            (scene.frame_start, scene.frame_end) == (10, 30), (scene.frame_start, scene.frame_end))
    h.check("...and the range no longer follows the clips", not tl.range_auto)
    h.check("...the loop range is left alone", not scene.use_preview_range)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.panel_new()
    yield 0.6
    h.check("adding a clip keeps the range you set", (scene.frame_start, scene.frame_end) == (10, 30),
            (scene.frame_start, scene.frame_end))
    tl.range_end = 5
    h.check("the end can't go before the start", scene.frame_end == 10, scene.frame_end)
    tl.range_start = 20
    h.check("...nor the start after the end (the end moves along)", scene.frame_end >= 20, scene.frame_end)
    tl.range_auto = True
    yield 0.6
    clips = h.module("timeline.clips")
    ends = [clips.end(s) for s in clips.top_clips(scene)]
    h.check("Auto: the range follows the clips again", scene.frame_end == max(ends) - 1,
            (scene.frame_end, max(ends)))
    h.redraw()
    yield 0.2
    h.screenshot("frame_range")


h.run(steps())
