"""The canvas colour can be changed in the tools area and is remembered."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

canvas_color = h.module("features.storyboard.canvas_color")
user_settings = h.module("core.user_settings")
theme_cfg = h.module("config.theme")
theme = h.module("core.theme")


def background():
    return tuple(bpy.context.preferences.themes[0].view_3d.space.gradients.high_gradient)


def same(a, b):
    return all(abs(x - y) < 0.01 for x, y in zip(a, b))


def steps():
    yield 1.0
    h.check("default canvas is the soft paper, not white",
            same(background(), theme._color("paper")[:3]) and background() != (1.0, 1.0, 1.0),
            background())
    h.check("Canvas panel is shown in the tools area",
            bpy.types.PLASTRON_PT_canvas.is_registered
            and not h.module("core.hidden_ui").is_hidden(bpy.types.PLASTRON_PT_canvas))

    for name, hex_color in theme_cfg.CANVAS_PRESETS:
        with h.override('PROPERTIES'):
            bpy.ops.plastron.canvas_color(color=hex_color)
        yield
        h.check(f"'{name}' swatch sets the canvas colour",
                same(background(), theme._color(hex_color)[:3]), background())

    custom = (0.3, 0.5, 0.4)
    bpy.context.window_manager.plastron_canvas_color = custom
    yield
    h.check("colour picker sets any colour", same(background(), custom), background())
    yield 1.0   # saving is debounced
    saved = json.load(open(user_settings.path()))
    h.check("choice is saved to Plastron's settings file",
            same(saved.get("canvas_color", ()), custom), saved)

    # Simulate the next start: reset the theme, reload settings, re-apply.
    theme.apply()
    user_settings.reload()
    canvas_color.apply(canvas_color.current())
    h.check("saved colour comes back on the next start", same(background(), custom), background())
    h.screenshot("canvas_color")


h.run(steps())
