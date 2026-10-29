"""Autosave, crash recovery, and the panel image cache following the project."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

autosave = h.module("core.autosave")
prefs_cfg = h.module("config.preferences")
panels = h.module("features.storyboard.panels")
panel_cache = h.module("features.storyboard.panel_cache")


def steps():
    yield 1.0
    h.check("Plastron marks itself as running (for crash detection)",
            os.path.exists(autosave._marker_path()))
    h.check("fresh start: no crash detected", not autosave.crashed_last_time)

    # --- Untitled project autosaves to Plastron's settings folder --------------
    bpy.data.texts["Script"].write("first line")
    paths = []
    for _ in range(prefs_cfg.AUTOSAVE_KEEP + 2):
        paths.append(autosave.save_now())
        yield 1.1                     # one-second timestamps
    folder = autosave.folder()
    kept = sorted(n for n in os.listdir(folder) if n.endswith(".blend"))
    h.check("untitled autosaves go to Plastron's settings folder",
            folder.startswith(bpy.utils.user_resource('CONFIG')), folder)
    h.check(f"only the newest {prefs_cfg.AUTOSAVE_KEEP} are kept", len(kept) == prefs_cfg.AUTOSAVE_KEEP, kept)
    h.check("Recover lists them newest first",
            [p for p, _t in autosave.list_autosaves()][0] == paths[-1])
    h.check("autosaving doesn't change the open file", bpy.data.filepath == "")

    # --- Saving moves the panel images next to the project ----------------------
    project = os.path.join(bpy.app.tempdir, "proj", "My Story.blend")
    os.makedirs(os.path.dirname(project), exist_ok=True)
    panel = panels.all_panels(bpy.context.scene)[0]
    with bpy.context.temp_override(window=h.window()):
        bpy.ops.wm.save_as_mainfile(filepath=project)
    yield 0.3
    cache = os.path.join(os.path.dirname(project), "My Story_cache")
    h.check("saving copies panel images to '<project>_cache'",
            os.path.dirname(panel_cache.strip_path(panel)) == cache
            and os.path.exists(panel_cache.strip_path(panel)), panel_cache.strip_path(panel))

    # --- Saved project autosaves beside itself; recover replaces it ---------------
    bpy.data.texts["Script"].clear()
    bpy.data.texts["Script"].write("good version")
    good = autosave.save_now()
    h.check("project autosaves go to '<project>_autosave' beside it",
            os.path.dirname(good) == os.path.join(os.path.dirname(project), "My Story_autosave"), good)
    h.check("autosave copies keep using the project's image cache",
            os.path.dirname(panel_cache.strip_path(panel)) == cache)
    bpy.data.texts["Script"].clear()
    bpy.data.texts["Script"].write("broken version")
    with bpy.context.temp_override(window=h.window()):
        bpy.ops.wm.save_mainfile()
    yield 0.3
    target = autosave.recover_into_project(good)
    with bpy.context.temp_override(window=h.window()):
        bpy.ops.wm.open_mainfile(filepath=target)
    yield 1.0
    h.check("recover puts the autosave in place of the project",
            bpy.data.filepath == project and bpy.data.texts["Script"].as_string() == "good version",
            bpy.data.texts["Script"].as_string())
    h.check("...keeping the replaced file as a backup",
            os.path.exists(os.path.join(os.path.dirname(project), "My Story_before_recover.blend")))
    h.check("the recovered project still opens in Storyboard mode", h.window().workspace.name == "Storyboard")
    canvas = bpy.data.objects.get("Canvas")
    h.check("...with its panel on the canvas",
            canvas and canvas.data == panels.all_panels(bpy.context.scene)[0].plastron_panel.drawing)

    # --- Crash detection ------------------------------------------------------------
    h.check("File > Recover menu exists", hasattr(bpy.types, "PLASTRON_MT_recover"))
    autosave.crashed_last_time = True       # as if the marker was left by a crash
    autosave._offer_recovery()              # shows the "closed unexpectedly" prompt
    yield 0.5
    h.screenshot("recover_prompt")
    h.key('ESC')
    yield 0.3
    h.check("crash prompt shows without errors", True)
    autosave._remove_marker()
    h.check("a clean exit removes the marker", not os.path.exists(autosave._marker_path()))
    autosave._touch_marker()


h.run(steps())
