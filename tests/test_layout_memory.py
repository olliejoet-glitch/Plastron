"""Your layout kept (core/layout_memory): each mode's screen measured into a
rows / columns tree; an edge dragged / areas swapped (Ctrl+drag a corner) / a
mode cut differently put back at the next start; Reset Layout back to config's."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

mem = h.module("core.layout_memory")
cfg = h.module("config.layout")
settings = h.module("core.user_settings")


def run(steps):
    """Drive a restore generator to its end."""
    for wait in steps:
        yield wait or 0.05


def wait_done():
    yield 0.5
    for _ in range(100):
        if not mem.running():
            break
        yield 0.1
    yield 1.0             # (the canvas / timeline are fitted 0.2 s after setup)


def channels_width(screen):
    tl = mem._timeline_area(screen)
    return next(r.width for r in tl.regions if r.type == 'CHANNELS')


def steps():
    yield 1.0
    win = h.window()
    screen = win.screen
    tree = mem.capture(screen, "Storyboard")
    h.check("the screen is measured into the same tree as config's",
            tree is not None and mem.same_layout(tree, cfg.MODES["Storyboard"], tol=0.02), tree)
    for mode in cfg.MODES:
        s = mem._mode_screen(mode)
        t = mem.capture(s, mode)
        h.check(f"...{mode} too (areas named by what they are)",
                t is not None and mem._shape(t) == mem._shape(cfg.MODES[mode]), t)
    mem.save()
    h.check("nothing kept while the layouts are Plastron's own", not settings.get(mem.KEY), settings.get(mem.KEY))

    # Ollie drags the timeline's top edge up.
    tl = mem._timeline_area(screen)
    with bpy.context.temp_override(window=win, screen=screen, area=tl):
        bpy.ops.screen.area_move(x=tl.x + tl.width // 2, y=tl.y + tl.height, delta=120)
    yield 0.3
    mem.save()
    kept = (settings.get(mem.KEY) or {}).get("Storyboard")
    h.check("a dragged edge is kept (on save / every few seconds)",
            kept is not None and kept["rows"][1]["size"] > 0.33, kept)
    # Swapped areas (Ctrl+drag a corner: needs a real mouse, so swapped in the
    # kept tree here): areas are named by what they are, not where.
    right = kept["rows"][0]["columns"][2]["rows"]
    right[0]["area"], right[1]["area"] = right[1]["area"], right[0]["area"]
    width = channels_width(screen)

    # Next start: Plastron's own layout comes up; the kept one is put back.
    yield from run(mem.restore_steps(win, {"Storyboard": cfg.MODES["Storyboard"]}))
    yield 0.3
    h.check("(reset to config's for the test)",
            mem.same_layout(mem.capture(win.screen, "Storyboard"), cfg.MODES["Storyboard"], tol=0.02),
            mem.capture(win.screen, "Storyboard"))
    yield from run(mem.restore_steps(win, {"Storyboard": kept}))
    yield 0.3
    back = mem.capture(win.screen, "Storyboard")
    h.check("at the next start the layout is put back (areas swapped back, edges moved back)",
            back is not None and mem.same_layout(back, kept, tol=0.02), (back, kept))
    h.check("...the track headers keep their width", abs(channels_width(win.screen) - width) < 4,
            (channels_width(win.screen), width))
    h.check("...the canvas is still the canvas", h.area('VIEW_3D') is not None
            and h.area('VIEW_3D').spaces.active.show_region_tool_header)

    # A mode cut differently (Ollie docked the timeline at the side): rebuilt.
    other = {"columns": [
        {"size": 0.35, "area": "timeline"},
        {"size": 0.65, "rows": [{"size": 0.5, "area": "preview"}, {"size": 0.5, "area": "media"}]},
    ]}
    yield from run(mem.restore_steps(win, {"Edit": other}))
    yield 0.3
    edit = mem._mode_screen("Edit")
    got = mem.capture(edit, "Edit")
    h.check("a mode cut differently is rebuilt that way", got is not None and mem.same_layout(got, other, tol=0.02),
            got)
    h.check("...its timeline keeps its track-header width", abs(channels_width(edit) - width) < 4,
            (channels_width(edit), width))
    h.check("...and is back on the mode it started in", win.workspace.name == "Storyboard", win.workspace.name)

    # Ollie's Storyboard came back as three canvases: a rebuild left half
    # done was measured and kept. Such a layout is never kept nor used.
    broken = {"rows": [{"size": 0.75, "columns": [{"size": 0.25, "area": "canvas"},
                                                   {"size": 0.75, "area": "canvas#2"}]},
                       {"size": 0.25, "area": "canvas#3"}]}
    h.check("a layout without its timeline can't be kept", not mem.usable("Storyboard", broken))
    settings.set(mem.KEY, {"Storyboard": broken, "Edit": other})
    yield from run(mem.restore_steps(win, {"Storyboard": broken}))
    yield 0.3
    h.check("...one kept from before: Plastron's own comes up instead",
            mem.same_layout(mem.capture(win.screen, "Storyboard"), cfg.MODES["Storyboard"], tol=0.02),
            mem.capture(win.screen, "Storyboard"))
    h.check("...and it's no longer kept (others are)",
            "Storyboard" not in settings.get(mem.KEY) and "Edit" in settings.get(mem.KEY), settings.get(mem.KEY))
    builder = h.module("core.layout")
    h.check("a second area of a kind ('timeline#2') gets that kind's editor",
            builder.spec("timeline#2").get("editor") == 'SEQUENCE_EDITOR')
    # A rebuild that goes wrong half way: Plastron's own, not kept.
    two = {"rows": [{"size": 0.6, "columns": [{"size": 0.3, "area": "tools"}, {"size": 0.7, "area": "canvas"}]},
                    {"size": 0.4, "area": "timeline"}]}
    real = builder.set_view_types

    def broken_step(placed):
        builder.set_view_types = real           # (fails once: the layout kept)
        raise RuntimeError("test: rebuild fails")
    builder.set_view_types = broken_step
    settings.set(mem.KEY, {"Storyboard": two})
    try:
        yield from run(mem.restore_steps(win, {"Storyboard": two}))
    finally:
        builder.set_view_types = real
    yield 0.3
    now = mem.capture(win.screen, "Storyboard")
    h.check("a rebuild that fails half way: Plastron's own layout, every area right",
            now is not None and mem.same_layout(now, cfg.MODES["Storyboard"], tol=0.02)
            and h.area('VIEW_3D').spaces.active.show_region_tool_header
            and mem._timeline_area(win.screen) is not None, now)
    h.check("...and that layout isn't kept", "Storyboard" not in (settings.get(mem.KEY) or {}),
            settings.get(mem.KEY))
    mem.save()
    h.check("...nor measured and kept again", "Storyboard" not in (settings.get(mem.KEY) or {}),
            settings.get(mem.KEY))

    # At start (first load): restore() does it by itself from the settings.
    settings.set(mem.KEY, {"Edit": cfg.MODES["Edit"]})
    mem.restore()
    yield from wait_done()
    h.check("Plastron's start puts the kept layouts back by itself",
            mem.same_layout(mem.capture(mem._mode_screen("Edit"), "Edit"), cfg.MODES["Edit"], tol=0.02))

    # Reset Layout: config's everywhere, nothing kept.
    settings.set(mem.KEY, {"Storyboard": kept})
    with h.override('VIEW_3D'):
        bpy.ops.plastron.layout_reset()
    yield from wait_done()
    h.check("File > Reset Layout: Plastron's own layout again, nothing kept",
            mem.same_layout(mem.capture(win.screen, "Storyboard"), cfg.MODES["Storyboard"], tol=0.02)
            and not settings.get(mem.KEY), (mem.capture(win.screen, "Storyboard"), settings.get(mem.KEY)))
    canvas = h.area('VIEW_3D').spaces.active
    h.check("...the rebuilt canvas looks through the 3D camera again",
            canvas.use_local_camera and canvas.region_3d.view_perspective == 'CAMERA',
            (canvas.use_local_camera, canvas.region_3d.view_perspective))
    tl = mem._timeline_area(win.screen)
    region = next(r for r in tl.regions if r.type == 'WINDOW')
    tracks = h.module("timeline.tracks")
    top = tracks.channel(len(tracks.all_tracks(bpy.context.scene)) - 1)
    h.check("...and the rebuilt timeline is framed on the tracks (the top one in view)",
            region.view2d.region_to_view(0, region.height - 30)[1] >= top, 
            (region.view2d.region_to_view(0, region.height - 30), top))
    h.redraw()
    yield 0.3
    h.screenshot("layout_memory")


h.run(steps())
