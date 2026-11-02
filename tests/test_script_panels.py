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
    want = [round(min(cfg["max_seconds"], max(cfg["min_seconds"], len(l.split()) * cfg["seconds_per_word"])) * fps)
            for l in ("INT. KITCHEN - NIGHT", "She opens the fridge, slowly, and stares at the light.", "Nothing.")]
    h.check("each lasts about as long as its line takes to read", lengths == want, (lengths, want))
    h.check("...one after another from the start",
            clips.start(made[0]) == sc.frame_start
            and all(clips.end(a) == clips.start(b) for a, b in zip(made, made[1:])))
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
    h.screenshot("script_panels")


h.run(steps())
