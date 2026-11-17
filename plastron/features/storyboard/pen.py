"""Which way Windows hands the pen to Blender (Ollie: "weird banding" in
strokes: their darkness follows pen pressure exactly, so the steps came in
with the pressure). Blender's own setting isn't kept (its preferences
aren't saved), so the choice lives in Plastron's settings and is put back
at every start. Choices: config/tools.py TABLET_APIS.
"""

import bpy

from ...config import tools as cfg
from ...core import user_settings

SETTING = "tablet_api"


def current():
    ids = [i for i, _l, _d in cfg.TABLET_APIS]
    v = user_settings.get(SETTING, ids[0])
    return v if v in ids else ids[0]


def apply():
    inputs = bpy.context.preferences.inputs
    if inputs.tablet_api != current():
        inputs.tablet_api = current()


def _get(_self):
    return [i for i, _l, _d in cfg.TABLET_APIS].index(current())


def _set(_self, index):
    user_settings.set(SETTING, cfg.TABLET_APIS[index][0])
    user_settings.save()                         # (rare: written at once)
    apply()


def register():
    bpy.types.WindowManager.plastron_tablet_api = bpy.props.EnumProperty(
        name="Pen", description="How Windows passes the pen (and its pressure) to Plastron",
        items=[(i, label, desc) for i, label, desc in cfg.TABLET_APIS], get=_get, set=_set)
    apply()


def unregister():
    del bpy.types.WindowManager.plastron_tablet_api
