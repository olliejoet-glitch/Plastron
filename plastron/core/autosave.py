"""Autosave and crash recovery.

- Every AUTOSAVE_MINUTES (config/preferences.py), if there are unsaved
  changes and nothing is playing or being dragged, a copy of the project is
  saved to "<project>_autosave/" next to it (untitled projects: Plastron's
  settings folder). Only the newest AUTOSAVE_KEEP copies are kept.
- A marker file exists while Plastron runs. If it's still there at the next
  start, Plastron didn't close normally, and offers the newest autosave.
- File > Recover lists the autosaves.
"""

import atexit
import os
import shutil
import time

import bpy

from ..config import preferences as cfg

saving = False          # True while an autosave copy is being written
crashed_last_time = False
MARKER = "plastron_running"


def _config_dir():
    return bpy.utils.user_resource('CONFIG')


def project_stem(blend_path=None):
    blend_path = blend_path if blend_path is not None else bpy.data.filepath
    return os.path.splitext(os.path.basename(blend_path))[0] if blend_path else "untitled"


def folder(blend_path=None):
    blend_path = blend_path if blend_path is not None else bpy.data.filepath
    if blend_path:
        return os.path.join(os.path.dirname(blend_path), project_stem(blend_path) + "_autosave")
    return os.path.join(_config_dir(), "plastron_autosave")


def list_autosaves():
    """[(path, modified time)] for this project and untitled ones, newest first."""
    found = []
    for f in {folder(), folder("")}:
        if os.path.isdir(f):
            for name in os.listdir(f):
                if name.endswith(".blend"):
                    path = os.path.join(f, name)
                    found.append((path, os.path.getmtime(path)))
    return sorted(found, key=lambda item: item[1], reverse=True)


def _prune(target_folder, stem):
    mine = sorted((os.path.join(target_folder, n) for n in os.listdir(target_folder)
                   if n.startswith(stem + "_") and n.endswith(".blend")),
                  key=os.path.getmtime, reverse=True)
    for old in mine[cfg.AUTOSAVE_KEEP:]:
        os.remove(old)


def _busy():
    wm = bpy.context.window_manager
    for window in wm.windows:
        if window.screen.is_animation_playing:
            return True
        if getattr(window, "modal_operators", None):   # a drag / stroke in progress
            return True
    return False


def save_now():
    """Write an autosave copy now. Returns its path."""
    global saving
    target = folder()
    os.makedirs(target, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(target, f"{project_stem()}_{stamp}.blend")
    saving = True
    try:
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False)
    finally:
        saving = False
    _prune(target, project_stem())
    return path


def _tick():
    try:
        if bpy.data.is_dirty and bpy.context.window_manager.windows and not _busy():
            save_now()
    except Exception as ex:          # never let autosave break Plastron
        print("Plastron autosave failed:", ex)
    _touch_marker()
    return cfg.AUTOSAVE_MINUTES * 60


def _marker_path():
    return os.path.join(_config_dir(), MARKER)


def _touch_marker():
    os.makedirs(_config_dir(), exist_ok=True)
    with open(_marker_path(), "w") as f:
        f.write(str(time.time()))


def _remove_marker():
    try:
        os.remove(_marker_path())
    except OSError:
        pass


def recover_into_project(autosave_path):
    """Make the open project's file the autosave, keeping the old one as
    '<project>_before_recover.blend'. Returns the project path to open."""
    project = bpy.data.filepath
    backup = os.path.join(os.path.dirname(project), project_stem() + "_before_recover.blend")
    if os.path.exists(project):
        shutil.copyfile(project, backup)
    shutil.copyfile(autosave_path, project)
    return project


class PLASTRON_OT_recover_autosave(bpy.types.Operator):
    """Open an autosaved copy"""
    bl_idname = "plastron.recover_autosave"
    bl_label = "Recover Autosave"

    filepath: bpy.props.StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        when = time.strftime("%H:%M on %d %b", time.localtime(os.path.getmtime(self.filepath)))
        if bpy.data.filepath and os.path.dirname(self.filepath) == folder():
            msg = (f"Replace '{project_stem()}' with the autosave from {when}? "
                   "The current file is kept as a backup.")
        else:
            msg = f"Open the autosave from {when}? Use Save As to keep it."
        return context.window_manager.invoke_confirm(self, event, title="Recover", message=msg)

    def execute(self, context):
        if bpy.data.filepath and os.path.dirname(self.filepath) == folder():
            bpy.ops.wm.open_mainfile(filepath=recover_into_project(self.filepath))
        else:
            bpy.ops.wm.open_mainfile(filepath=self.filepath)
        return {'FINISHED'}


class PLASTRON_MT_recover(bpy.types.Menu):
    bl_label = "Recover"

    def draw(self, context):
        layout = self.layout
        saves = list_autosaves()
        if not saves:
            layout.label(text="No autosaves yet")
        for path, mtime in saves[:10]:
            label = f"{os.path.basename(path)}   ({time.strftime('%H:%M %d %b', time.localtime(mtime))})"
            layout.operator("plastron.recover_autosave", text=label).filepath = path
        layout.separator()
        layout.operator("wm.recover_last_session", text="Last Session")
        layout.operator("wm.recover_auto_save", text="Blender Auto Save...")


class PLASTRON_OT_recover_prompt(bpy.types.Operator):
    """Plastron didn't close normally last time: offer the newest autosave"""
    bl_idname = "plastron.recover_prompt"
    bl_label = "Plastron closed unexpectedly"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, confirm_text="Recover", width=420)

    def draw(self, context):
        saves = list_autosaves()
        self.layout.label(text="Plastron didn't close normally last time.")
        if saves:
            when = time.strftime("%H:%M on %d %b", time.localtime(saves[0][1]))
            self.layout.label(text=f"Open the newest autosave ({os.path.basename(saves[0][0])}, {when})?")

    def execute(self, context):
        saves = list_autosaves()
        if saves:
            bpy.ops.wm.open_mainfile(filepath=saves[0][0])
        return {'FINISHED'}


def _offer_recovery():
    if crashed_last_time and list_autosaves() and bpy.context.window_manager.windows:
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bpy.ops.plastron.recover_prompt('INVOKE_DEFAULT')
    return None


classes = (PLASTRON_OT_recover_autosave, PLASTRON_MT_recover, PLASTRON_OT_recover_prompt)


def register():
    global crashed_last_time
    for cls in classes:
        bpy.utils.register_class(cls)
    crashed_last_time = os.path.exists(_marker_path())
    _touch_marker()
    atexit.register(_remove_marker)
    bpy.app.timers.register(_tick, first_interval=cfg.AUTOSAVE_MINUTES * 60, persistent=True)
    bpy.app.timers.register(_offer_recovery, first_interval=1.5)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _remove_marker()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
