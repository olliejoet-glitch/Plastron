"""Panels from the script: one panel per line (blank lines skipped), the
blank starter panel replaced, reading-time lengths, re-running adds only new
lines, Import Script from a file, clicking a line jumps to its panel."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

panels = h.module("features.storyboard.panels")
script_panels = h.module("features.storyboard.script_panels")
script_link = h.module("features.voice.script_link")
clips = h.module("timeline.clips")
cfg = h.module("config.timeline").SCRIPT_PANELS


def steps():
    yield 1.0
    sc = bpy.context.scene
    text = script_panels.script_text()
    text.from_string("INT. KITCHEN - NIGHT\n\nShe opens the fridge, slowly, and stares at the light.\n"
                     "Nothing.\n")
    starter = panels.all_panels(sc)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_panels()
    yield 0.3
    made = sorted(panels.all_panels(sc), key=clips.start)
    h.check("one panel per line, blank lines skipped, blank starter replaced",
            len(starter) == 1 and len(made) == 3 and [s.plastron_panel.script_line for s in made] == [0, 2, 3],
            [(s.name, s.plastron_panel.script_line) for s in made])
    fps = sc.render.fps
    lengths = [clips.end(s) - clips.start(s) for s in made]
    sp = h.module("features.storyboard.script_panels")
    want = [round(s * fps) for s in (4 * 0.4 + 1.0, 10 * 0.4 + 1.0, 2.0)]      # (the last: the shortest)
    h.check("each lasts a little longer than its line takes to read (a pause after it)",
            lengths == want and sp.pause() == 1.0, (lengths, want))
    h.check("...a longer pause for each extra sentence in a line",
            abs(sp.seconds_for("Wait. Go now! Stop it.") - (5 * 0.4 + 1.0 + 2 * 0.5)) < 1e-6,
            sp.seconds_for("Wait. Go now! Stop it."))
    h.check("...one after another from the start",
            clips.start(made[0]) == sc.frame_start
            and all(clips.end(a) == clips.start(b) for a, b in zip(made, made[1:])))
    # The Pause slider: remembered, and script panels follow (ones trimmed by hand stay).
    ripple = h.module("timeline.ripple")
    ripple.trim(sc, made[2], 'RIGHT', clips.start(made[2]) + 60)        # (trimmed by hand)
    bpy.context.window_manager.plastron_script_pause = 2.0
    yield 0.8
    lengths2 = [clips.length(s) for s in made]
    h.check("Pause slider: panels made from the script get the new pause, one after another",
            lengths2 == [round((4 * 0.4 + 2.0) * fps), round((10 * 0.4 + 2.0) * fps), 60]
            and all(clips.end(a) == clips.start(b) for a, b in zip(made, made[1:])), lengths2)
    h.check("...remembered", h.module("core.user_settings").get(sp.PAUSE_KEY) == 2.0)
    bpy.context.window_manager.plastron_script_pause = 1.0
    yield 0.8
    h.check("...and back", [clips.length(s) for s in made] == [want[0], want[1], 60],
            [clips.length(s) for s in made])
    h.check("the panel remembers its line", made[1].plastron_panel.script_text.startswith("She opens"))

    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_panels()
    yield 0.2
    h.check("running it again adds nothing", len(panels.all_panels(sc)) == 3)
    text.from_string(text.as_string() + "He closes it.\n")
    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_panels()
    yield 0.2
    now = sorted(panels.all_panels(sc), key=clips.start)
    h.check("a new line gets a new panel, at the end", len(now) == 4
            and now[-1].plastron_panel.script_line == 4)

    sc.frame_current = 0
    h.check("clicking a line (not recorded yet) jumps to its panel",
            script_link.jump_to_line(sc, 2) and sc.frame_current == clips.start(made[1]), sc.frame_current)

    # The script follows the playhead: the line of the panel under it is lit.
    follow = h.module("features.voice.script_follow")
    sc.frame_current = clips.start(made[1]) + 5
    yield 0.2
    h.check("scrubbing onto a panel lights its script line", follow._now["line"] == 2
            and follow.line_at(sc) == 2, follow._now)
    sc.frame_current = clips.start(now[-1]) + 2
    yield 0.2
    h.check("...and the next panel's line when the playhead moves on", follow._now["line"] == 4, follow._now)
    calls = []
    real = follow.line_at
    follow.line_at = lambda *a, **k: calls.append(1) or real(*a, **k)
    for d in (3, 4, 5):
        sc.frame_current = clips.start(now[-1]) + d
        yield 0.05
    follow.line_at = real
    h.check("...doing nothing while it stays in the same panel", not calls, len(calls))
    h.redraw()
    yield 0.2
    h.screenshot("script_follow")

    # Import from a file: the script panel gets the file; new panels follow.
    path = os.path.join(bpy.app.tempdir, "script_test.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Line one.\r\nLine two is a little longer.\r\n")
    with h.override('VIEW_3D'):
        bpy.ops.plastron.script_import(filepath=path)
    yield 0.3
    h.check("Import Script reads the file into the script panel",
            script_panels.script_text().as_string().startswith("Line one.\nLine two"))
    h.check("...and makes its panels", len(panels.all_panels(sc)) == 6,
            [(s.name, s.plastron_panel.script_line) for s in panels.all_panels(sc)])
    # Paste Script: the copied script lands in the script panel, panels follow.
    bpy.context.window_manager.clipboard = "Pasted one.\r\nPasted two.\n"
    area = h.area('TEXT_EDITOR')
    bar = h.region(area, 'HEADER')
    h.check("the script panel has its bar", bar is not None and bar.height > 10)
    with h.override('TEXT_EDITOR'):
        bpy.ops.plastron.script_paste()
    yield 0.3
    h.check("Paste Script adds the copied lines to the script",
            script_panels.script_text().as_string().rstrip().endswith("Pasted one.\nPasted two."))
    h.check("...and makes their panels", len(panels.all_panels(sc)) == 8, len(panels.all_panels(sc)))
    h.redraw()
    yield 0.2
    h.screenshot("script_panels")


h.run(steps())
