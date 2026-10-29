"""Storyboard mode: script, canvas, tool strip, timeline.

Stage 1: canvas navigation, tool switching, tool strip, options bar.
"""

import bpy

from ...core import handlers
from . import canvas_frame, canvas_view, options_bar, tools

_CLASSES = canvas_view.classes + tools.classes


def _after_load(_scene):
    # Fit once the window has its final size (not possible inside load_post).
    bpy.app.timers.register(lambda: canvas_view.fit_all_canvases(), first_interval=0.2)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    options_bar.register()
    canvas_frame.register()
    handlers.on_load(_after_load)


def unregister():
    canvas_frame.unregister()
    options_bar.unregister()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
