"""Brush presets (Pencil, Ink, Marker, Soft shading...): a Blender texture
brush plus size, opacity, pressure and smoothing. The presets themselves are
JSON files in plastron/presets/brushes/ (see its README); the store is
core/presets.py. Picked from the options bar.
"""

import bpy

from ...config.tools import BRUSH_LIBRARY
from ...core import presets
from .tools import CONTEXT_MODE, PAINT_MODE, drawing_object

KIND = "brushes"


def _owners(context):
    ip = context.tool_settings.image_paint
    ups = ip.unified_paint_settings
    brush = ip.brush
    return (ups if ups.use_unified_size else brush), (ups if ups.use_unified_strength else brush), brush


def apply(context, preset):
    obj = drawing_object(context)
    if obj is not None and obj.mode != PAINT_MODE:
        bpy.ops.object.mode_set(mode=PAINT_MODE)
    asset = preset.get("asset")      # saved presets name the exact brush asset
    if asset:
        bpy.ops.brush.asset_activate(asset_library_type=asset[0], asset_library_identifier=asset[1],
                                     relative_asset_identifier=asset[2])
    else:
        bpy.ops.brush.asset_activate(asset_library_type='ESSENTIALS',
                                     relative_asset_identifier=BRUSH_LIBRARY + preset["base"])
    if context.workspace.tools.from_space_view3d_mode(CONTEXT_MODE, create=False).idname != "builtin.brush":
        bpy.ops.wm.tool_set_by_id(name="builtin.brush", space_type='VIEW_3D')
    size_owner, strength_owner, brush = _owners(context)
    size_owner.size = int(preset.get("size", size_owner.size))
    strength_owner.strength = float(preset.get("opacity", strength_owner.strength))
    brush.use_pressure_size = bool(preset.get("pressure_size", brush.use_pressure_size))
    brush.use_pressure_strength = bool(preset.get("pressure_opacity", brush.use_pressure_strength))
    brush.use_smooth_stroke = bool(preset.get("smooth", brush.use_smooth_stroke))
    brush.smooth_stroke_radius = int(preset.get("smooth_radius", brush.smooth_stroke_radius))
    brush.spacing = int(preset.get("spacing", brush.spacing))
    context.window_manager["plastron_brush_preset"] = preset["name"]


def capture(context):
    ip = context.tool_settings.image_paint
    ref = ip.brush_asset_reference
    size_owner, strength_owner, brush = _owners(context)
    return {
        "base": brush.name,
        "asset": [ref.asset_library_type, ref.asset_library_identifier, ref.relative_asset_identifier],
        "size": size_owner.size, "opacity": round(strength_owner.strength, 3),
        "pressure_size": brush.use_pressure_size, "pressure_opacity": brush.use_pressure_strength,
        "smooth": brush.use_smooth_stroke, "smooth_radius": brush.smooth_stroke_radius,
        "spacing": brush.spacing,
    }


def current_name(context):
    """The preset last picked, while its brush is still the one in use."""
    name = context.window_manager.get("plastron_brush_preset", "")
    preset = presets.get(KIND, name) if name else None
    brush = context.tool_settings.image_paint.brush
    if preset is None or brush is None or brush.name != preset.get("base"):
        return ""
    return name


class PLASTRON_MT_brush_presets(bpy.types.Menu):
    bl_label = "Brush Presets"

    def draw(self, context):
        presets.draw_menu(self.layout, KIND)


classes = (PLASTRON_MT_brush_presets,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    presets.register_kind(KIND, apply, capture)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
