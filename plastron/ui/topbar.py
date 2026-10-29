"""Slim top bar: Plastron icon, File menu, undo/redo, mode switcher."""

import os

import bpy
import bpy.utils.previews

from ..core import hidden_ui

_icons = None


class PLASTRON_OT_file_new(bpy.types.Operator):
    """Start a new, empty Plastron project"""
    bl_idname = "plastron.file_new"
    bl_label = "New Project"

    def invoke(self, context, event):
        if bpy.data.is_dirty:
            return context.window_manager.invoke_confirm(
                self, event, title="New project?",
                message="Unsaved changes to this project will be lost.", confirm_text="New")
        return self.execute(context)

    def execute(self, context):
        bpy.ops.wm.read_homefile(app_template="plastron")
        return {'FINISHED'}


class PLASTRON_MT_file(bpy.types.Menu):
    bl_label = "File"

    def draw(self, context):
        layout = self.layout
        layout.operator("plastron.file_new", text="New", icon='FILE_NEW')
        layout.operator("wm.open_mainfile", text="Open...", icon='FILE_FOLDER')
        layout.menu("TOPBAR_MT_file_open_recent")
        layout.separator()
        layout.operator("wm.save_mainfile", text="Save", icon='FILE_TICK')
        layout.operator("wm.save_as_mainfile", text="Save As...")
        layout.separator()
        layout.menu("PLASTRON_MT_recover")
        layout.separator()
        layout.operator("wm.quit_blender", text="Quit", icon='QUIT')


def draw_left(self, context):
    layout = self.layout
    if _icons and "plastron" in _icons:
        layout.label(text="", icon_value=_icons["plastron"].icon_id)
    layout.menu("PLASTRON_MT_file")
    layout.separator(type='LINE')
    row = layout.row(align=True)
    row.operator("ed.undo", text="", icon='LOOP_BACK')
    row.operator("ed.redo", text="", icon='LOOP_FORWARDS')
    layout.separator(type='LINE')
    layout.prop(context.window_manager, "plastron_mode", expand=True)


def draw_right(self, context):
    layout = self.layout
    layout.template_reports_banner()   # status bar is hidden, so messages show here
    layout.template_running_jobs()
    name = bpy.path.basename(bpy.data.filepath) or "Unsaved project"
    layout.label(text=name + (" *" if bpy.data.is_dirty else ""))


_classes = (PLASTRON_OT_file_new, PLASTRON_MT_file)


def register():
    global _icons
    for cls in _classes:
        bpy.utils.register_class(cls)
    _icons = bpy.utils.previews.new()
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon_256.png")
    _icons.load("plastron", path, 'IMAGE')
    hidden_ui.replace("TOPBAR_HT_upper_bar", "draw_left", draw_left)
    hidden_ui.replace("TOPBAR_HT_upper_bar", "draw_right", draw_right)


def unregister():
    global _icons
    bpy.utils.previews.remove(_icons)
    _icons = None
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
