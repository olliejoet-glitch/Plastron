"""Onion skin settings: on/off (options bar) and strength (Canvas panel).

canvas_sync shows the panels; this module only holds the choice, remembered
via core.user_settings.
"""

import bpy

from ...config import tools as tools_cfg
from ...core import user_settings


def enabled():
    return bool(user_settings.get("onion_skin", tools_cfg.ONION_SKIN_ON))


def opacity():
    return float(user_settings.get("onion_skin_opacity", tools_cfg.ONION_SKIN_OPACITY))


def _changed():
    from . import canvas_sync
    canvas_sync.invalidate(bpy.context.scene)


def _set_enabled(_self, value):
    user_settings.set("onion_skin", bool(value))
    _changed()


def _set_opacity(_self, value):
    user_settings.set("onion_skin_opacity", float(value))
    _changed()


def register():
    wm = bpy.types.WindowManager
    wm.plastron_onion = bpy.props.BoolProperty(
        name="Onion Skin", description="Show the panels before and after this one, faintly",
        get=lambda _self: enabled(), set=_set_enabled)
    wm.plastron_onion_opacity = bpy.props.FloatProperty(
        name="Onion Skin", min=0.0, max=1.0, subtype='FACTOR',
        get=lambda _self: opacity(), set=_set_opacity)


def unregister():
    del bpy.types.WindowManager.plastron_onion
    del bpy.types.WindowManager.plastron_onion_opacity
