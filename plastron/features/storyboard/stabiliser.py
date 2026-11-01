"""Stabiliser: Off / Slight / Max (options bar). One choice for every brush,
remembered between sessions; the modes' values are in config/tools.py.

Steadying (averaging recent pen positions) is a unified paint setting, so it
holds for every brush at once; the lazy-mouse part lives on each brush, so
it's set again whenever a tool, preset or the mode changes.
"""

import bpy

from ...config import tools as cfg
from ...core import user_settings

SETTING = "stabiliser"


def modes():
    return {row[0]: row for row in cfg.STABILISER}


def current():
    mode = user_settings.get(SETTING, cfg.STABILISER_DEFAULT)
    return mode if mode in modes() else cfg.STABILISER_DEFAULT


def apply(context=None):
    """Put the current mode on the paint settings and the active brush."""
    context = context or bpy.context
    scene = context.scene
    if scene is None:
        return
    _id, _label, steady, lazy, radius, strength = modes()[current()]
    ip = scene.tool_settings.image_paint
    ups = ip.unified_paint_settings
    if not ups.use_unified_input_samples:
        ups.use_unified_input_samples = True
    if ups.input_samples != steady:
        ups.input_samples = steady
    brush = ip.brush
    if brush is not None:
        if brush.use_smooth_stroke != lazy:
            brush.use_smooth_stroke = lazy
        if lazy:
            brush.smooth_stroke_radius = radius
            brush.smooth_stroke_factor = strength


def _get(_self):
    return list(modes()).index(current())


def _set(_self, index):
    user_settings.set(SETTING, cfg.STABILISER[index][0])
    apply()


def register():
    bpy.types.WindowManager.plastron_stabiliser = bpy.props.EnumProperty(
        name="Stabiliser", description="How much your strokes are steadied",
        items=[(row[0], row[1], f"{row[1]} stabilising") for row in cfg.STABILISER],
        get=_get, set=_set)
    from ...core import handlers
    handlers.on_load(lambda scene: apply())


def unregister():
    del bpy.types.WindowManager.plastron_stabiliser
