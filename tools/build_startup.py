"""Builds plastron/startup.blend from config/layout.py and project_defaults.py.

Run from a normal terminal:   python tools/build_startup.py
(It launches Blender under a virtual display and runs itself inside it.)
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "plastron", "startup.blend")

try:
    import bpy
except ImportError:
    bpy = None


def launch():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import blender_env
    code, out = blender_env.run(["--factory-startup", "--enable-event-simulate",
                                    "--python", os.path.abspath(__file__)])
    if code != 0 or "PLASTRON BUILD OK" not in out:
        print(out[-3000:])
        sys.exit("Build failed.")
    print("Built", OUT)


def build_steps():
    """Generator: each yield lets Blender refresh its UI before the next step."""
    sys.path.insert(0, REPO)
    from plastron.config import layout as cfg
    from plastron.core import layout, project
    from plastron.features.storyboard import canvas_sync

    project.register()   # scene.plastron must exist to set up the project
    window = bpy.context.window_manager.windows[0]

    others = [ws for ws in bpy.data.workspaces if ws != window.workspace]
    bpy.data.batch_remove(others)
    yield

    for i, mode in enumerate(cfg.MODES):
        if i > 0:
            with bpy.context.temp_override(window=window):
                bpy.ops.workspace.duplicate()
            yield
        placed = {}
        yield from layout.split_mode(window, mode, placed)
        yield
        layout.configure_mode(placed)
        yield
        layout.hide_navigation_bars(window, placed)
        yield
        yield from layout.widen_channel_columns(window, placed)
        window.workspace.name = mode
        window.screen.name = mode
        window.workspace[layout.HASH_KEY] = layout.build_hash()
        yield
    window.workspace = bpy.data.workspaces[cfg.DEFAULT_MODE]
    yield

    scene = window.scene
    for coll in list(scene.collection.children):
        bpy.data.collections.remove(coll)
    project.setup_new_project(scene)
    canvas = canvas_sync.canvas_object(scene)
    scene.view_layers[0].objects.active = canvas
    canvas.select_set(True)
    layout.use_project_scene(window)
    bpy.data.orphans_purge(do_recursive=True)
    yield

    # Open in drawing mode with the pencil.
    canvas = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in canvas.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=canvas, region=region):
        bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')
        bpy.ops.wm.tool_set_by_id(name="builtin.brush", space_type='VIEW_3D')
    yield

    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
    print("PLASTRON BUILD OK", flush=True)
    bpy.ops.wm.quit_blender()


def run_steps(steps):
    def tick():
        try:
            next(steps)
        except StopIteration:
            return None
        except Exception:
            import traceback
            traceback.print_exc()
            bpy.ops.wm.quit_blender()
            return None
        return 0.3
    bpy.app.timers.register(tick, first_interval=1.0)


if bpy is None:
    launch()
else:
    run_steps(build_steps())
