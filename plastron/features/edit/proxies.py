"""Half-size preview copies of footage (Ollie: "the frame rate is really
jittery": the preview decoded his full-size phone video every frame).

Clips were set to play from Blender's proxies (PREVIEW_SIZE /
PROXY_BUILD in config/edit.py), but Blender only MAKES them when asked:
placed footage now has them built in the background (Blender's own job,
progress in the top bar), and footage in a project that's missing them is
built when the project opens. They live next to the footage in BL_proxy/.
Renders / exports never use them.
"""

import os

import bpy

from ...config import edit as cfg
from ...core import handlers
from ...timeline import clips, ripple

SIZES = {"build_25": "25", "build_50": "50", "build_75": "75", "build_100": "100"}


def proxy_files(strip):
    """Where Blender keeps (or will keep) this clip's preview copies."""
    if strip.proxy.use_proxy_custom_directory:
        folder = bpy.path.abspath(strip.proxy.directory)
    else:
        folder = os.path.join(os.path.dirname(bpy.path.abspath(strip.filepath)), "BL_proxy")
    folder = os.path.join(folder, os.path.basename(strip.filepath))
    return [os.path.join(folder, f"proxy_{SIZES[a]}.avi") for a in cfg.PROXY_BUILD]


def missing(strip):
    return (strip.type == 'MOVIE' and strip.use_proxy and cfg.PREVIEW_SIZE != 'SCENE'
            and os.path.exists(bpy.path.abspath(strip.filepath))
            and not all(os.path.exists(p) for p in proxy_files(strip)))


_building = set()        # (scene name, clip name) whose copies are being made


def building(scene):
    """How many clips' preview copies are still being made."""
    left = set()
    sed = scene.sequence_editor if scene else None
    for sc_name, name in _building:
        strip = sed.strips_all.get(name) if sed and sc_name == scene.name else None
        if strip is not None and missing(strip):
            left.add((sc_name, name))
    _building.intersection_update(left | {b for b in _building if b[0] != (scene.name if scene else "")})
    return len(left)


def build(scene, strips):
    """Have Blender make the preview copies of these clips (in the
    background). Returns how many were started."""
    todo = [s for s in strips if missing(s)]
    over = ripple._timeline_override()
    if not todo or over is None:
        return 0
    sed = clips.editor(scene)
    was = {s: s.select for s in sed.strips_all}
    for s in was:
        s.select = s in todo
    try:
        with bpy.context.temp_override(**over, scene=scene):
            bpy.ops.sequencer.rebuild_proxy('INVOKE_DEFAULT')    # (a background job: EXEC builds them right there, freezing Plastron)
    except RuntimeError as err:
        print("Plastron: couldn't make preview copies:", err)
        return 0
    finally:
        for s, sel in was.items():
            try:
                s.select = sel
            except ReferenceError:
                pass
    _building.update((scene.name, s.name) for s in todo)
    return len(todo)


def _on_load(scene):
    if scene is None or scene.sequence_editor is None:
        return

    def later():
        sc = bpy.data.scenes.get(scene_name)
        if sc is not None and sc.sequence_editor is not None:
            build(sc, [s for s in sc.sequence_editor.strips_all if s.type == 'MOVIE'])
        return None
    scene_name = scene.name
    bpy.app.timers.register(later, first_interval=1.5)


def register():
    handlers.on_load(_on_load)


def unregister():
    pass
