"""Camera and motion (stage 6).

    view_follow   Camera View: the canvas looks through the camera
    camera_pad    camera controls box in the canvas corner (pan pad, zoom, turn)
    camera        each panel's camera move: start / end frame (pan, zoom, a
                  slight rotation), easing graph, shake; the moved frame on
                  the canvas (canvas_frame hook)
    layer_motion  layers / groups moving from a start to an end position;
                  shown after scrubbing stops (never per frame)
    edit          setting a start / end by dragging on the canvas
    canvas_fit    the painting grows to fit its camera move
    thumbnails    panel images show where a panel starts (panel_cache hook)
    ui            Motion panel (tools area) + motion presets (presets/motion/)

Clean View (F, hides everything outside the frame) is the storyboard
canvas_frame's. Easing graphs are the shared dot graph (widgets/dot_graph).
"""

import bpy

from ...core import handlers
from ...layers import events as layer_events
from ...timeline import events
from ..storyboard import canvas_frame
from . import camera, camera_pad, canvas_fit, edit, layer_motion, thumbnails, ui, view_follow
from ...widgets import dot_graph

_CLASSES = camera.classes + camera_pad.classes + edit.classes + ui.classes


def _on_split(scene, original, new):
    """Split panels each get their own copy of the camera's easing graph
    (Blender copies the rest: both halves keep the whole move)."""
    if original.plastron_motion.curve:
        new.plastron_motion.curve = dot_graph.copy(original.plastron_motion.curve)


def _on_layers_changed(_mat):
    camera.bump()
    layer_motion.refresh()


def _on_load(scene):
    canvas_fit.fit_all(scene)        # moves that went past their painting before this fix
    wm = bpy.context.window_manager
    if wm is not None and wm.get(edit.EDITING):
        wm[edit.EDITING] = ""


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Strip.plastron_motion = bpy.props.PointerProperty(type=camera.PLASTRON_PG_motion)
    canvas_frame.FRAME_PROVIDERS.append(camera.frame_provider)
    view_follow.register()
    camera_pad.register()
    thumbnails.register()
    layer_motion.register()
    ui.register()
    events.listen("clip_split", _on_split)
    layer_events.listen(_on_layers_changed)
    handlers.on_load(_on_load)


def unregister():
    layer_motion.unregister()
    canvas_fit.unregister()
    view_follow.unregister()
    camera_pad.unregister()
    thumbnails.unregister()
    if camera.frame_provider in canvas_frame.FRAME_PROVIDERS:
        canvas_frame.FRAME_PROVIDERS.remove(camera.frame_provider)
    del bpy.types.Strip.plastron_motion
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
