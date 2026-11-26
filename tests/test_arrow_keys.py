"""Left / Right step the playhead a frame, Shift+Left / Right jump to the
start / end, like Blender (over the timeline and the canvas); in the script
they still move the text cursor."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402


def over(kind):
    reg = h.region(h.area(kind))
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)


def steps():
    yield 1.0
    sc = bpy.context.scene
    sc.frame_current = 20
    yield 0.2
    over('SEQUENCE_EDITOR')
    yield 0.2
    h.key('RIGHT_ARROW')
    yield 0.2
    h.check("Right over the timeline: one frame on", bpy.context.scene.frame_current == 21,
            bpy.context.scene.frame_current)
    h.key('LEFT_ARROW')
    h.key('LEFT_ARROW')
    yield 0.2
    h.check("Left: one frame back", bpy.context.scene.frame_current == 19, bpy.context.scene.frame_current)
    over('VIEW_3D')
    yield 0.2
    h.key('RIGHT_ARROW')
    yield 0.2
    h.check("...over the canvas too", bpy.context.scene.frame_current == 20, bpy.context.scene.frame_current)
    h.key('RIGHT_ARROW', shift=True)
    yield 0.2
    sc = bpy.context.scene
    h.check("Shift+Right: to the end", sc.frame_current == sc.frame_end, (sc.frame_current, sc.frame_end))
    h.key('LEFT_ARROW', shift=True)
    yield 0.2
    sc = bpy.context.scene
    h.check("Shift+Left: to the start", sc.frame_current == sc.frame_start, (sc.frame_current, sc.frame_start))

    # The script: arrows move the text cursor, not the playhead.
    area = h.area('TEXT_EDITOR')
    text = area.spaces.active.text
    text.from_string("Hello there")
    text.cursor_set(0, character=5)
    sc.frame_current = 30
    over('TEXT_EDITOR')
    yield 0.2
    h.key('RIGHT_ARROW')
    yield 0.2
    h.check("in the script, Right moves the text cursor (the playhead stays)",
            text.current_character == 6 and bpy.context.scene.frame_current == 30,
            (text.current_character, bpy.context.scene.frame_current))


h.run(steps())
