"""The media bin (Edit mode's left area): Blender's file browser showing
thumbnails of video, sound and pictures. Drag a file onto the timeline, or
select files and press Add to Timeline (at the playhead, on the active
track). Also sets how big the preview plays footage (config/edit.py).
"""

import os

import bpy

from ...config import edit as cfg
from ...core import handlers
from ...core.layout import setup_media_browser
from . import media


def media_browsers():
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for screen in [ws.screens[0] for ws in bpy.data.workspaces if ws.screens] + [window.screen]:
            for area in screen.areas:
                if area.type == 'FILE_BROWSER':
                    yield area, area.spaces.active


def previews():
    for ws in bpy.data.workspaces:
        for screen in ws.screens:
            for area in screen.areas:
                space = area.spaces.active
                if area.type == 'SEQUENCE_EDITOR' and space.view_type == 'PREVIEW':
                    yield area, space


def start_folder():
    if bpy.data.filepath:
        return os.path.dirname(bpy.data.filepath)
    for path in cfg.MEDIA_START:
        path = os.path.expanduser(path)
        if os.path.isdir(path):
            return path
    return os.path.expanduser("~")


def set_up(scene=None, *_args):
    """At load: the preview's size and the media bin's filters / folder."""
    scene = scene or bpy.context.scene
    if scene is not None and scene.sequence_editor is None:
        scene.sequence_editor_create()
    first = scene is not None and not scene.get("plastron_edit_ready")
    for _area, space in previews():
        if first and space.proxy_render_size != cfg.PREVIEW_SIZE:
            space.proxy_render_size = cfg.PREVIEW_SIZE
    done = False
    for _area, space in media_browsers():
        if space.params is None:
            continue
        done = setup_media_browser(space) or done
        if first or not os.path.isdir(bpy.path.abspath(space.params.directory.decode()
                                                       if isinstance(space.params.directory, bytes)
                                                       else space.params.directory)):
            folder = start_folder()
            space.params.directory = folder.encode() if isinstance(space.params.directory, bytes) else folder
    if scene is not None and (done or not any(True for _ in media_browsers())):
        scene["plastron_edit_ready"] = True


def _later(scene_name):
    def run():
        scene = bpy.data.scenes.get(scene_name)
        if scene is not None:
            set_up(scene)
        return None
    return run


def _on_load(scene):
    set_up(scene)
    if scene is not None:      # (a file browser's settings only exist once it has drawn)
        bpy.app.timers.register(_later(scene.name), first_interval=0.5)


def selected_paths(context):
    space = context.space_data
    folder = space.params.directory
    folder = folder.decode() if isinstance(folder, bytes) else folder
    names = [f.relative_path for f in (getattr(context, "selected_files", None) or [])]
    if not names and space.params.filename:
        names = [space.params.filename]
    return [os.path.join(bpy.path.abspath(folder), n) for n in names]


class PLASTRON_OT_media_add(bpy.types.Operator):
    """Put the selected files on the timeline at the playhead (on the active track)"""
    bl_idname = "plastron.media_add"
    bl_label = "Add to Timeline"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'FILE_BROWSER' \
            and context.space_data.params is not None

    def execute(self, context):
        scene = context.scene
        paths = [p for p in selected_paths(context) if os.path.isfile(p)]
        if not paths:
            self.report({'WARNING'}, "Select a video, sound or picture first")
            return {'CANCELLED'}
        frame = scene.frame_current
        added = 0
        for path in paths:
            result = media.place(scene, path, frame)
            if isinstance(result, str):
                self.report({'WARNING'}, result)
                continue
            added += 1
            frame = max(media.clips.end(s) for s in result)     # one after another
        if added:
            scene.frame_current = frame
        return {'FINISHED'} if added else {'CANCELLED'}


def _draw_header(self, context):
    space = context.space_data
    if getattr(space, "active_operator", None) is not None:      # (an Open / Save dialog)
        return
    self.layout.operator("plastron.media_add", icon='ADD')


classes = (PLASTRON_OT_media_add,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.FILEBROWSER_HT_header.append(_draw_header)
    handlers.on_load(_on_load)


def unregister():
    bpy.types.FILEBROWSER_HT_header.remove(_draw_header)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
