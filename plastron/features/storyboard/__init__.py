"""Storyboard mode: script, canvas, tool strip, timeline.

    panels         panel clips + their paintings (layer stacks); New Panel
    panel_cache    cached panel images shown on the timeline (re-made after edits)
    canvas_sync    shows the panel(s) under the playhead on the canvas
    canvas_view    canvas navigation; canvas_frame: frame overlay
    canvas_color   Canvas panel (paper colour)
    tools          tool switching, tool strip; options_bar
    (the Layers panel comes from plastron/layers)
"""

import bpy

from ...core import handlers
from . import (canvas_color, canvas_frame, canvas_sync, canvas_view, options_bar, panel_cache,
               panels, tools)

_CLASSES = canvas_view.classes + tools.classes


def _after_load(_scene):
    # Fit once the window has its final size (not possible inside load_post).
    bpy.app.timers.register(lambda: canvas_view.fit_all_canvases(), first_interval=0.2)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    options_bar.register()
    canvas_frame.register()
    canvas_color.register()
    panels.register()
    panel_cache.register()
    canvas_sync.register()
    handlers.on_load(_after_load)


def unregister():
    canvas_sync.unregister()
    panel_cache.unregister()
    panels.unregister()
    canvas_color.unregister()
    canvas_frame.unregister()
    options_bar.unregister()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
