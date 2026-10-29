"""Project data (scene.plastron) and project setup.

setup_new_project() runs only when the startup file is built.
ensure_project() runs after any project is opened, cheaply filling in
anything a Plastron project needs.
"""

import math

import bpy
from mathutils import Euler

from ..config import project_defaults as cfg
from . import handlers

PROJECT_VERSION = 1


class PLASTRON_PG_project(bpy.types.PropertyGroup):
    version: bpy.props.IntProperty(name="Project format version", default=0)


def setup_new_project(scene):
    """Turn a fresh scene into an empty Plastron project."""
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj)

    render = scene.render
    render.resolution_x, render.resolution_y = cfg.RESOLUTION
    render.resolution_percentage = cfg.PREVIEW_PERCENT
    render.fps, render.fps_base = cfg.FPS, 1.0
    scene.frame_start, scene.frame_end = cfg.FRAME_START, cfg.FRAME_END
    scene.frame_current = cfg.FRAME_START
    scene.use_audio_scrub = cfg.AUDIO_SCRUB
    scene.sync_mode = cfg.PLAYBACK_SYNC
    scene.view_settings.view_transform = cfg.VIEW_TRANSFORM
    scene.view_settings.look = 'None'

    _add_canvas(scene)
    ensure_project(scene)


def _add_canvas(scene):
    """The canvas camera. The sheets painted on come from
    features/storyboard/canvas_sync.py."""
    cam_data = bpy.data.cameras.new("Canvas Camera")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = cfg.CANVAS_WIDTH
    cam_data.show_name = False
    camera = bpy.data.objects.new("Canvas Camera", cam_data)
    camera.location = (0.0, -10.0, 0.0)
    camera.rotation_euler = Euler((math.radians(90), 0.0, 0.0))
    scene.collection.objects.link(camera)
    scene.camera = camera

    ts = scene.tool_settings
    ts.use_keyframe_insert_auto = False        # panel timing lives in clips, not keyframes


def ensure_project(scene):
    """Make sure an opened project has everything Plastron needs."""
    if scene is None:
        return
    if scene.sequence_editor is None:
        scene.sequence_editor_create()
    if cfg.SCRIPT_TEXT_NAME not in bpy.data.texts:
        bpy.data.texts.new(cfg.SCRIPT_TEXT_NAME)
    if scene.plastron.version < PROJECT_VERSION:
        scene.plastron.version = PROJECT_VERSION
    _connect_ui()


def _connect_ui():
    """Point the script panel at the project's script, and the timeline at
    the project's scene (Blender 5 timelines show the workspace's sequencer scene)."""
    wm = bpy.context.window_manager
    text = bpy.data.texts.get(cfg.SCRIPT_TEXT_NAME)
    for window in wm.windows:
        if window.workspace.sequencer_scene != window.scene:
            window.workspace.sequencer_scene = window.scene
        for area in window.screen.areas:
            if area.type == 'TEXT_EDITOR' and area.spaces.active.text != text:
                area.spaces.active.text = text


def register():
    bpy.utils.register_class(PLASTRON_PG_project)
    bpy.types.Scene.plastron = bpy.props.PointerProperty(type=PLASTRON_PG_project)
    handlers.on_load(ensure_project)


def unregister():
    del bpy.types.Scene.plastron
    bpy.utils.unregister_class(PLASTRON_PG_project)
