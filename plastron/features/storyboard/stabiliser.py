"""Stabiliser: Off / Slight / Max (options bar). One choice for every brush,
remembered between sessions.

Each mode's values start as config/tools.py STABILISER; the ▾ next to the
switch opens a pop-up to adjust them in the app (remembered too, Reset goes
back to config's values).

Steadying (averaging recent pen positions) is a unified paint setting, so it
holds for every brush at once; the lazy-mouse part lives on each brush, so
it's set again whenever a tool, preset or the mode changes.
"""

import bpy

from ...config import tools as cfg
from ...core import user_settings

SETTING = "stabiliser"
VALUES = "stabiliser_values"          # user_settings: {mode: {field: value}}
FIELDS = ("steady", "lazy", "radius", "strength")


def modes():
    return {row[0]: row for row in cfg.STABILISER}


def current():
    mode = user_settings.get(SETTING, cfg.STABILISER_DEFAULT)
    return mode if mode in modes() else cfg.STABILISER_DEFAULT


def values(mode):
    """{steady, lazy, radius, strength} for a mode: config's, with any changes
    made in the app on top."""
    row = modes()[mode]
    out = dict(zip(FIELDS, row[2:]))
    out.update((user_settings.get(VALUES) or {}).get(mode, {}))
    return out


def apply(context=None):
    """Put the current mode on the paint settings and the active brush."""
    context = context or bpy.context
    scene = context.scene
    if scene is None:
        return
    v = values(current())
    ip = scene.tool_settings.image_paint
    ups = ip.unified_paint_settings
    if not ups.use_unified_input_samples:
        ups.use_unified_input_samples = True
    if ups.input_samples != int(v["steady"]):
        ups.input_samples = int(v["steady"])
    brush = ip.brush
    if brush is not None:
        if brush.use_smooth_stroke != bool(v["lazy"]):
            brush.use_smooth_stroke = bool(v["lazy"])
        if v["lazy"]:
            brush.smooth_stroke_radius = int(v["radius"])
            brush.smooth_stroke_factor = float(v["strength"])


def _get(_self):
    return list(modes()).index(current())


def _set(_self, index):
    user_settings.set(SETTING, cfg.STABILISER[index][0])
    apply()


def _value_prop(mode, field):
    """A WindowManager property showing / changing one value of one mode."""
    def get(_self):
        return values(mode)[field]

    def set(_self, value):
        saved = dict(user_settings.get(VALUES) or {})
        changed = dict(saved.get(mode, {}))
        changed[field] = value
        saved[mode] = changed
        user_settings.set(VALUES, saved)
        if current() == mode:
            apply()
    label = {"steady": "Steady", "lazy": "Trailing smoothing", "radius": "Radius",
             "strength": "Strength"}[field]
    tips = {"steady": "Average this many recent pen positions (1 = off). No dead zone",
            "lazy": "The stroke trails behind the pen, for very smooth curves",
            "radius": "How far behind the pen the stroke trails, in screen pixels (Blender's minimum is 10)",
            "strength": "How strongly the stroke is pulled back"}[field]
    if field == "steady":
        return bpy.props.IntProperty(name=label, description=tips, min=1, max=64, get=get, set=set)
    if field == "lazy":
        return bpy.props.BoolProperty(name=label, description=tips, get=get, set=set)
    if field == "radius":
        return bpy.props.IntProperty(name=label, description=tips, min=10, max=200,
                                     subtype='PIXEL', get=get, set=set)
    return bpy.props.FloatProperty(name=label, description=tips, min=0.5, max=0.99,
                                   step=1, precision=2, get=get, set=set)


def prop_name(mode, field):
    return f"plastron_stab_{mode.lower()}_{field}"


def tunable_modes():
    """Modes with something to tune (Off is just off)."""
    return [m for m in modes() if m != "OFF"]


class PLASTRON_OT_stabiliser_reset(bpy.types.Operator):
    """Put every stabiliser mode back to its standard values"""
    bl_idname = "plastron.stabiliser_reset"
    bl_label = "Reset"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        user_settings.set(VALUES, {})
        apply(context)
        return {'FINISHED'}


class PLASTRON_PT_stabiliser(bpy.types.Panel):
    """The values behind Slight and Max (options bar ▾)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Stabiliser"
    bl_ui_units_x = 11

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        wm = context.window_manager
        for mode in tunable_modes():
            box = layout.box()
            box.label(text=modes()[mode][1])
            for field in FIELDS:
                if field in ("radius", "strength") and not values(mode)["lazy"]:
                    continue
                box.prop(wm, prop_name(mode, field))
        layout.operator("plastron.stabiliser_reset", icon='LOOP_BACK')


classes = (PLASTRON_OT_stabiliser_reset, PLASTRON_PT_stabiliser)


def register():
    wm = bpy.types.WindowManager
    wm.plastron_stabiliser = bpy.props.EnumProperty(
        name="Stabiliser", description="How much your strokes are steadied",
        items=[(row[0], row[1], f"{row[1]} stabilising") for row in cfg.STABILISER],
        get=_get, set=_set)
    for mode in tunable_modes():
        for field in FIELDS:
            setattr(wm, prop_name(mode, field), _value_prop(mode, field))
    for cls in classes:
        bpy.utils.register_class(cls)
    from ...core import handlers
    handlers.on_load(lambda scene: apply())


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for mode in tunable_modes():
        for field in FIELDS:
            delattr(bpy.types.WindowManager, prop_name(mode, field))
    del bpy.types.WindowManager.plastron_stabiliser
