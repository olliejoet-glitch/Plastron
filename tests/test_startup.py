"""Plastron starts into its own layout, theme and settings."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

layout_cfg = h.module("config.layout")
defaults = h.module("config.project_defaults")
theme_cfg = h.module("config.theme")
handlers = h.module("core.handlers")
layout = h.module("core.layout")
theme = h.module("core.theme")


def steps():
    yield 1.0
    prefs = bpy.context.preferences
    win = h.window()
    screen = win.screen

    h.check("app template is Plastron", prefs.app_template == "plastron", prefs.app_template)
    pinned_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "install", "blender_version.txt")
    pinned = open(pinned_file).read().strip()
    h.check("tested on the Blender version the installer pins",
            bpy.app.version_string.split()[0] == pinned, (bpy.app.version_string, pinned))
    h.check("opens in Storyboard mode", win.workspace.name == "Storyboard", win.workspace.name)
    h.check("only Plastron's workspaces exist",
            sorted(w.name for w in bpy.data.workspaces) == sorted(layout_cfg.MODES),
            [w.name for w in bpy.data.workspaces])
    built = win.workspace.get(layout.HASH_KEY)
    h.check("startup.blend matches config (else run: python tools/build_startup.py)",
            built == layout.build_hash(), f"{built} vs {layout.build_hash()}")

    # Layout
    kinds = sorted(a.type for a in screen.areas)
    h.check("four-area layout: script, canvas, tool strip, timeline",
            kinds == sorted(['TEXT_EDITOR', 'VIEW_3D', 'PROPERTIES', 'SEQUENCE_EDITOR']), kinds)
    script, canvas, timeline = h.area('TEXT_EDITOR'), h.area('VIEW_3D'), h.area('SEQUENCE_EDITOR')
    if script and canvas and timeline:
        h.check("script panel is left of canvas", script.x < canvas.x)
        h.check("timeline is along the bottom", timeline.y < canvas.y and timeline.y < script.y)
        h.check("timeline spans the full width", timeline.width >= win.width * 0.99,
                (timeline.width, win.width))
        h.check("script panel ~18% wide",
                abs(script.width / win.width - 0.18) < 0.03, script.width / win.width)
        sp = canvas.spaces.active
        h.check("canvas: no header, no Blender toolbar",
                not sp.show_region_header and not sp.show_region_toolbar)
        h.check("canvas: options bar shown", sp.show_region_tool_header)
        h.check("canvas: orthographic, rotation locked",
                sp.region_3d.view_perspective == 'ORTHO' and sp.region_3d.lock_rotation)
        h.check("canvas: grid and axes hidden",
                not sp.overlay.show_floor and not sp.overlay.show_axis_x)
        h.check("timeline: track headers column shown", timeline.spaces.active.show_region_channels)
        h.check("script panel: no header", not script.spaces.active.show_region_header)
        h.check("script panel shows the project's Script",
                script.spaces.active.text and script.spaces.active.text.name == defaults.SCRIPT_TEXT_NAME)
    h.check("status bar hidden", not screen.show_statusbar)

    # Blender UI hidden
    hidden_ui = h.module("core.hidden_ui")
    shown = [c.__name__ for c in hidden_ui.panels_to_hide() if not hidden_ui.is_hidden(c)]
    h.check("Blender's panels hidden (tools area, canvas, timeline, script)", not shown, shown[:10])
    tools_area = h.area('PROPERTIES')
    h.check("tools area right of canvas", tools_area and canvas and tools_area.x > canvas.x)
    h.check("canvas ~70% wide, tools ~12% wide",
            canvas and tools_area and abs(canvas.width / win.width - 0.70) < 0.03
            and abs(tools_area.width / win.width - 0.12) < 0.03,
            canvas and tools_area and (canvas.width / win.width, tools_area.width / win.width))
    h.check("timeline ~30% tall", timeline and abs(timeline.height / win.height - 0.30) < 0.04,
            timeline and timeline.height / win.height)
    h.check("timeline shows the project", win.workspace.sequencer_scene == bpy.context.scene)
    h.check("canvas: no Blender sidebar", canvas and not canvas.spaces.active.show_region_ui)
    h.check("top bar replaced (no workspace tabs / Blender menus)",
            "plastron" in bpy.types.TOPBAR_HT_upper_bar.draw_left.__module__)
    h.check("timeline header replaced",
            "plastron" in bpy.types.SEQUENCER_HT_header.draw.__module__)

    # Project defaults
    scene = bpy.context.scene
    r = scene.render
    h.check("4K project, previews at 50%",
            (r.resolution_x, r.resolution_y, r.resolution_percentage) == (3840, 2160, 50))
    h.check(f"{defaults.FPS} fps", r.fps == defaults.FPS and r.fps_base == 1.0, r.fps)
    h.check("audio scrubbing on", scene.use_audio_scrub)
    h.check("colour view transform is Standard", scene.view_settings.view_transform == 'Standard')
    h.check("project has a sequencer", scene.sequence_editor is not None)
    h.check("canvas opens in drawing mode with the pencil",
            bpy.context.mode == 'PAINT_GREASE_PENCIL', bpy.context.mode)

    # Preferences
    h.check("no splash screen", not prefs.view.show_splash)
    h.check("opening a project keeps Plastron's layout", not prefs.filepaths.use_load_ui)
    h.check("Blender won't save its preferences", not prefs.use_preferences_save)

    # Theme
    h.check("theme applies cleanly", theme.apply() == [])
    back = list(prefs.themes[0].sequence_editor.space.back)[:3]
    want = theme._color(theme_cfg.COLORS["sequence_editor.space.back"])[:3]
    h.check("theme: timeline background is teal",
            all(abs(a - b) < 0.01 for a, b in zip(back, want)), back)

    # Performance guard: nothing Plastron hooks may run every frame (stage 1).
    per_frame = [(n, f) for n, f in handlers.registered() if n in handlers.PER_FRAME]
    h.check("no per-frame handlers", not per_frame, per_frame)
    drivers = sum(len(o.animation_data.drivers) for o in bpy.data.objects if o.animation_data)
    h.check("no drivers in a new project", drivers == 0, drivers)

    # Mode switcher
    h.check("mode switcher shows Storyboard",
            bpy.context.window_manager.plastron_mode == "Storyboard")

    h.screenshot("startup")
    yield

    # File > New gives a fresh Plastron project in the same layout.
    bpy.data.texts[defaults.SCRIPT_TEXT_NAME].write("A line of script")
    with bpy.context.temp_override(window=h.window()):
        bpy.ops.plastron.file_new("EXEC_DEFAULT")
    yield 1.0
    h.check("New project: still Storyboard layout", h.window().workspace.name == "Storyboard")
    text = bpy.data.texts.get(defaults.SCRIPT_TEXT_NAME)
    h.check("New project: empty script", text is not None and text.as_string() == "")
    h.check("New project: script panel connected",
            h.area('TEXT_EDITOR') and h.area('TEXT_EDITOR').spaces.active.text == text)


h.run(steps())
