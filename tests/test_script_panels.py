"""The script on the Script lane: a block per line (between the audio and
video tracks), panels made where the lines are; the Pause slider; "Panels
follow script" (on: dragging a line / Retime / splitting a line move and make
panels; off: panels left alone); script edits sync the blocks (a split line
shares its time, lines added at the end lengthen the lane, removed ones close
up); Retime; clicking a line; the highlight follows the lane; Import, Paste."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

panels = h.module("features.storyboard.panels")
sp = h.module("features.storyboard.script_panels")
lane = h.module("features.storyboard.script_lane")
script_link = h.module("features.voice.script_link")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")
events = h.module("timeline.events")


def spans(strips):
    return [(clips.start(s), clips.end(s)) for s in strips]


def linked_panels(sc):
    out = [p for p in panels.all_panels(sc) if p.plastron_panel.script_block]
    return sorted(out, key=clips.start)


def steps():
    yield 1.0
    sc = bpy.context.scene
    fps = sc.render.fps
    kinds = [t.kind for t in tracks.all_tracks(sc)]
    h.check("the Script lane sits between the audio and the video tracks",
            kinds == ['AUDIO', 'AUDIO', 'SCRIPT', 'VIDEO', 'VIDEO'], kinds)
    text = sp.script_text()
    text.from_string("INT. KITCHEN - NIGHT\n\nShe opens the fridge, slowly, and stares at the light.\n"
                     "Nothing.\n")
    starter = panels.all_panels(sc)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_panels()
    yield 0.3
    blocks = lane.blocks(sc)
    made = linked_panels(sc)
    want = [round(s * fps) for s in (4 * 0.4 + 1.0, 10 * 0.4 + 1.0, 2.0)]      # (the last: the shortest)
    h.check("Make: a block per line on the Script lane (blank lines skipped), its reading time + pause",
            [b.text for b in blocks] == ["INT. KITCHEN - NIGHT", "She opens the fridge, slowly, and stares at the light.",
                                         "Nothing."]
            and [clips.length(b) for b in blocks] == want and clips.start(blocks[0]) == sc.frame_start
            and all(clips.end(a) == clips.start(b) for a, b in zip(blocks, blocks[1:])),
            ([b.text for b in blocks], [clips.length(b) for b in blocks], want))
    h.check("...a panel where each line is (the blank starter replaced)",
            len(starter) == 1 and len(panels.all_panels(sc)) == 3 and spans(made) == spans(blocks)
            and [p.plastron_panel.script_line for p in made] == [0, 2, 3], spans(made))
    h.check("...a longer pause for each extra sentence in a line",
            abs(sp.seconds_for("Wait. Go now! Stop it.") - (5 * 0.4 + 1.0 + 2 * 0.5)) < 1e-6)
    h.check("the lines are see-through text clips (never in a render)",
            all(b.type == 'TEXT' and b.blend_alpha == 0.0 for b in blocks))

    # The Pause slider: lines not dragged by hand get the new pause; panels
    # don't follow while "Panels follow script" is off.
    ripple.trim(sc, blocks[2], 'RIGHT', clips.start(blocks[2]) + 60)      # (a line dragged by hand)
    events.clips_changed(sc)
    yield 0.2
    panel_spans = spans(linked_panels(sc))
    bpy.context.window_manager.plastron_script_pause = 2.0
    yield 1.6
    blocks = lane.blocks(sc)
    h.check("Pause slider: the lines get the new pause (the one dragged by hand stays)",
            [clips.length(b) for b in blocks] == [round((4 * 0.4 + 2.0) * fps), round((10 * 0.4 + 2.0) * fps), 60],
            [clips.length(b) for b in blocks])
    h.check("...panels left alone (they don't follow the script)", spans(linked_panels(sc)) == panel_spans,
            (spans(linked_panels(sc)), panel_spans))
    bpy.context.window_manager.plastron_script_pause = 1.0
    yield 1.6

    # Panels follow script: on = panels take their lines' spans.
    sc.plastron_script_follow = True
    yield 0.3
    blocks = lane.blocks(sc)
    h.check("'Panels follow script' on: the panels jump to their lines", spans(linked_panels(sc)) == spans(blocks),
            (spans(linked_panels(sc)), spans(blocks)))
    ripple.trim(sc, blocks[0], 'RIGHT', clips.end(blocks[0]) + 12)          # drag a line's end
    events.clips_changed(sc)
    yield 0.3
    blocks = lane.blocks(sc)
    h.check("...dragging a line's edge moves the panels with it", spans(linked_panels(sc)) == spans(blocks),
            (spans(linked_panels(sc)), spans(blocks)))

    # Splitting a line in the script: the two share its time; with panels
    # following, its panel shrinks and a new blank panel takes the rest.
    end0 = clips.end(lane.blocks(sc)[-1])
    text.from_string("INT. KITCHEN - NIGHT\n\nShe opens the fridge, slowly,\nand stares at the light.\nNothing.\n")
    sp._auto_panels()
    yield 0.3
    blocks = lane.blocks(sc)
    h.check("splitting a line: two lines share its time (nothing later moves)",
            [b.text for b in blocks] == ["INT. KITCHEN - NIGHT", "She opens the fridge, slowly,",
                                         "and stares at the light.", "Nothing."] and clips.end(blocks[-1]) == end0,
            ([b.text for b in blocks], clips.end(blocks[-1]), end0))
    h.check("...its panel takes the first part, a new panel the second (panels follow)",
            len(linked_panels(sc)) == 4 and spans(linked_panels(sc)) == spans(blocks)
            and linked_panels(sc)[1].plastron_panel.uid == made[1].plastron_panel.uid,
            spans(linked_panels(sc)))

    # Panels not following: a line added at the end lengthens the lane, no panel.
    sc.plastron_script_follow = False
    n_panels = len(panels.all_panels(sc))
    text.from_string(text.as_string().rstrip("\n") + "\nHe closes it.\n")
    sp._auto_panels()
    yield 0.3
    blocks = lane.blocks(sc)
    h.check("a line added at the end: a new block after the last (the lane gets longer)",
            blocks[-1].text == "He closes it." and clips.start(blocks[-1]) == end0
            and clips.length(blocks[-1]) == round(sp.seconds_for("He closes it.") * fps)
            and len(panels.all_panels(sc)) == n_panels, (blocks[-1].text, clips.start(blocks[-1]), end0))
    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_panels()
    yield 0.3
    h.check("...Make gives it a panel where it is", len(panels.all_panels(sc)) == n_panels + 1
            and spans(linked_panels(sc))[-1] == spans(lane.blocks(sc))[-1])

    # A line removed: its block goes, later ones close up.
    nothing = next(b for b in lane.blocks(sc) if b.text == "Nothing.")
    gap = clips.length(nothing)
    last_start = clips.start(lane.blocks(sc)[-1])
    text.from_string(text.as_string().replace("Nothing.\n", ""))
    sp._auto_panels()
    yield 0.3
    blocks = lane.blocks(sc)
    h.check("a line removed: its block goes, the next close up",
            "Nothing." not in [b.text for b in blocks] and clips.start(blocks[-1]) == last_start - gap,
            ([b.text for b in blocks], clips.start(blocks[-1]), last_start - gap))

    # Retime: every line its reading time (+ pause), one after another.
    with h.override('TEXT_EDITOR'):
        bpy.ops.plastron.script_retime()
    yield 0.3
    blocks = lane.blocks(sc)
    h.check("Retime: each line as long as it takes to read (+ the pause)",
            [clips.length(b) for b in blocks] == [round(sp.seconds_for(b.text) * fps) for b in blocks]
            and all(clips.end(a) == clips.start(b) for a, b in zip(blocks, blocks[1:])),
            [clips.length(b) for b in blocks])

    # Clicking a line / the highlight follow the lane.
    target = blocks[2]
    li = target[lane.INDEX]
    sc.frame_current = 0
    h.check("clicking a line (not recorded yet) jumps to where it is on the Script lane",
            script_link.jump_to_line(sc, li) and sc.frame_current == clips.start(target), sc.frame_current)
    follow = h.module("features.voice.script_follow")
    sc.frame_current = clips.start(target) + 3
    yield 0.3
    h.check("the script lights the line under the playhead", follow.line_at(sc) == li, (follow.line_at(sc), li))
    calls = []
    yield 0.6
    real = follow._stretch
    follow._stretch = lambda *a, **k: calls.append(1) or real(*a, **k)
    for d in (4, 5, 6):
        sc.frame_current = clips.start(target) + d
        yield 0.05
    follow._stretch = real
    h.check("...doing nothing while it stays on the same line", not calls, len(calls))
    h.redraw()
    yield 0.3
    h.screenshot("script_lane")

    # Typing: Enter in the middle of the first line splits it (synced 1.5 s later).
    area = h.area('TEXT_EDITOR')
    with h.override('TEXT_EDITOR'):
        x, y = bpy.context.space_data.region_location_from_cursor(0, 5)
    r = h.region(area)
    h.move(r.x + x + 1, r.y + y + 6)
    yield 0.2
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.3
    n_blocks = len(lane.blocks(sc))
    h.key('RET')
    yield 2.8
    h.check("typing Enter in a line: the Script lane gets the new line by itself",
            len(lane.blocks(sc)) == n_blocks + 1, [b.text for b in lane.blocks(sc)])

    # Import from a file: the script panel gets the file; new lines and panels.
    path = os.path.join(bpy.app.tempdir, "script_test.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Line one.\r\nLine two is a little longer.\r\n")
    count0 = len(panels.all_panels(sc))
    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_import(filepath=path)
    yield 0.3
    h.check("Import Script reads the file into the script panel",
            sp.script_text().as_string().startswith("Line one.\nLine two"))
    h.check("...its lines on the Script lane, a panel each",
            [b.text for b in lane.blocks(sc)] == ["Line one.", "Line two is a little longer."]
            and len(panels.all_panels(sc)) == count0 + 2, [b.text for b in lane.blocks(sc)])
    bpy.context.window_manager.clipboard = "Pasted one.\r\nPasted two.\n"
    bar = h.region(area, 'HEADER')
    h.check("the script panel has its bar", bar is not None and bar.height > 10)
    with h.override('TEXT_EDITOR'):
        bpy.ops.plastron.script_paste()
    yield 0.3
    h.check("Paste Script adds the copied lines to the script, the lane and the panels",
            sp.script_text().as_string().rstrip().endswith("Pasted one.\nPasted two.")
            and len(lane.blocks(sc)) == 4 and len(panels.all_panels(sc)) == count0 + 4,
            ([b.text for b in lane.blocks(sc)], len(panels.all_panels(sc))))
    h.redraw()
    yield 0.2
    h.screenshot("script_panels")


h.run(steps())
