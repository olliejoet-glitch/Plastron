"""Layer stack data (ported from Ollie's CaraPainter, trimmed to 2D).

Material.plastron_stack holds the layer list. Index 0 = BOTTOM of the stack;
the UI draws it reversed. Groups are a flat list + parent_uid: a group's
children sit directly BELOW the group entry. The node trees that draw the
stack are compiled from this data (compiler.py), never edited by hand.
"""

import uuid

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)

# Photoshop order (Dissolve omitted).
BLEND_MODES = [
    ("NORMAL", "Normal", ""),
    ("DARKEN", "Darken", ""), ("MULTIPLY", "Multiply", ""), ("COLOR_BURN", "Colour Burn", ""),
    ("LINEAR_BURN", "Linear Burn", ""), ("DARKER_COLOR", "Darker Colour", ""),
    ("LIGHTEN", "Lighten", ""), ("SCREEN", "Screen", ""), ("COLOR_DODGE", "Colour Dodge", ""),
    ("LINEAR_DODGE", "Linear Dodge (Add)", ""), ("LIGHTER_COLOR", "Lighter Colour", ""),
    ("OVERLAY", "Overlay", ""), ("SOFT_LIGHT", "Soft Light", ""), ("HARD_LIGHT", "Hard Light", ""),
    ("VIVID_LIGHT", "Vivid Light", ""), ("LINEAR_LIGHT", "Linear Light", ""),
    ("PIN_LIGHT", "Pin Light", ""), ("HARD_MIX", "Hard Mix", ""),
    ("DIFFERENCE", "Difference", ""), ("EXCLUSION", "Exclusion", ""), ("SUBTRACT", "Subtract", ""),
    ("DIVIDE", "Divide", ""),
    ("HUE", "Hue", ""), ("SATURATION", "Saturation", ""), ("COLOR", "Colour", ""),
    ("LUMINOSITY", "Luminosity", "Photoshop luminosity (Rec.601 luma), not HSV value"),
]
BLEND_MODES = [(i, n, d, k) for k, (i, n, d) in enumerate(BLEND_MODES)]

LAYER_TYPES = [
    ("FILL", "Fill", "Flat colour or image", 'SNAP_FACE', 0),
    ("PAINT", "Paint", "Painted pixels", 'BRUSH_DATA', 1),
    ("ADJUST", "Adjustment", "Adjusts everything below it", 'MODIFIER', 2),
    ("GROUP", "Group", "Group of layers", 'FILE_FOLDER', 5),
]

ADJUST_KINDS = [("HUE_SAT", "Hue/Saturation", ""), ("LEVELS", "Levels", ""),
                ("BRIGHT_CONTRAST", "Brightness/Contrast", ""), ("CURVES", "Curves", "")]

MASK_SOURCES = [
    ("PAINT", "Paint", "Paint the mask: white shows the layer, black hides it", 'BRUSH_DATA', 3),
    ("IMAGE", "Image", "Any greyscale image", 'IMAGE_DATA', 2),
]
MASK_OPS = [
    ("MULTIPLY", "Multiply", "Keep only where both are white"),
    ("ADD", "Add", "Add to the mask"),
    ("SUBTRACT", "Subtract", "Cut out of the mask"),
    ("MAX", "Max (Lighten)", ""),
    ("MIN", "Min (Darken)", ""),
    ("OVERLAY", "Overlay", ""),
]

_suspend = 0   # >0 while bulk-editing so update callbacks don't recompile


class suspended:
    def __enter__(self):
        global _suspend
        _suspend += 1

    def __exit__(self, *a):
        global _suspend
        _suspend -= 1


def _tree_get(self):
    return bpy.data.node_groups.get(self.node_tree_name) if self.node_tree_name else None


def _tree_set(self, tree):
    self.node_tree_name = tree.name if tree is not None else ""


def _structural(self, context):
    if not _suspend:
        from .compiler import compile_stack
        compile_stack(self.id_data)
        from . import events
        events.changed(self.id_data)


def _value(self, context):
    if not _suspend:
        from .compiler import push_layer
        push_layer(self.id_data, self)
        from . import events
        events.changed(self.id_data)


def _mask_value(self, context):
    if not _suspend:
        from .compiler import push_mask
        push_mask(self.id_data, self)
        from . import events
        events.changed(self.id_data)


def _target_changed(self, context):
    """Active layer / paint target / lock changed: aim the brush again."""
    if _suspend:
        return
    from .paint_target import sync
    sync(self.id_data)


class PLASTRON_PG_mask(bpy.types.PropertyGroup):
    uid: StringProperty()
    name: StringProperty(default="Mask")
    source: EnumProperty(name="Source", items=MASK_SOURCES, default="PAINT", update=_structural)
    op: EnumProperty(name="Combine", items=MASK_OPS, default="MULTIPLY", update=_structural)
    visible: BoolProperty(default=True, update=_mask_value)
    opacity: FloatProperty(name="Opacity", default=1.0, min=0, max=1, subtype='FACTOR', update=_mask_value)
    threshold: FloatProperty(name="Threshold", default=0.5, min=0, max=1, update=_mask_value)
    softness: FloatProperty(name="Softness", default=0.5, min=0, max=0.5, update=_mask_value)
    invert: BoolProperty(name="Invert", default=False, update=_mask_value)
    image: PointerProperty(name="Image", type=bpy.types.Image, update=_mask_value)

    def ensure_uid(self):
        if not self.uid:
            self.uid = uuid.uuid4().hex[:10]
        return self.uid


class PLASTRON_PG_layer(bpy.types.PropertyGroup):
    uid: StringProperty()
    name: StringProperty(default="Layer")
    layer_type: EnumProperty(items=LAYER_TYPES, default="PAINT", update=_structural)
    parent_uid: StringProperty()
    expanded: BoolProperty(default=True, description="Show the layers in this group")
    # built-in colour adjustments on every layer
    la_hue: FloatProperty(name="Hue", default=0, min=-180, max=180, update=_value)
    la_saturation: FloatProperty(name="Saturation", default=1, min=0, max=2, update=_value)
    la_value: FloatProperty(name="Value", default=1, min=0, max=2, update=_value)
    la_curve: BoolProperty(name="Curve", default=False, update=_structural,
                           description="A curve graph on this layer's colour, like Photoshop's Curves")

    visible: BoolProperty(default=True, update=_value, description="Show / hide layer")
    locked: BoolProperty(default=False, update=_target_changed,
                         description="Lock the layer so it can't be painted on")
    opacity: FloatProperty(name="Opacity", default=1.0, min=0.0, max=1.0, subtype='FACTOR', update=_value)
    blend_mode: EnumProperty(name="Blend Mode", items=BLEND_MODES, default="NORMAL", update=_structural)
    group_mode: EnumProperty(name="Group Mode", items=[
        ("PASS_THROUGH", "Pass Through", "Children blend straight into the layers below"),
        ("ISOLATED", "Normal (isolated)", "Children are composited first, then blended as one"),
    ], default="PASS_THROUGH", update=_structural)

    # fill
    fill_source: EnumProperty(name="Source", items=[("COLOR", "Colour", ""), ("IMAGE", "Image", "")],
                              default="COLOR", update=_structural)
    fill_color: FloatVectorProperty(name="Colour", subtype='COLOR_GAMMA', size=3, min=0, max=1,
                                    default=(0.5, 0.5, 0.5), update=_value)
    fill_image: PointerProperty(name="Image", type=bpy.types.Image, update=_value)
    tex_scale: FloatProperty(name="Scale", default=1.0, min=0.01, max=200, soft_max=40, update=_value,
                             description="How many times the image repeats across the canvas")
    tex_rotation: FloatProperty(name="Rotation", default=0.0, subtype='ANGLE', update=_value)
    tex_offset: FloatVectorProperty(name="Offset", size=2, default=(0.0, 0.0), update=_value)
    tile_break: FloatProperty(name="Tiling Break", default=0.0, min=0, max=1, subtype='FACTOR', update=_value,
                              description="Blend in a rotated, shifted copy in random patches so the "
                                          "repeats don't show")
    tile_break_size: FloatProperty(name="Patch Size", default=2.0, min=0.1, max=50, update=_value,
                                   description="Tiling break: size of the patches, in tiles")
    # paint
    paint_image: PointerProperty(name="Image", type=bpy.types.Image, update=_value)
    # adjustment
    adjust_kind: EnumProperty(name="Adjustment", items=ADJUST_KINDS, default="HUE_SAT", update=_structural)
    hs_hue: FloatProperty(name="Hue", default=0, min=-180, max=180, update=_value)
    hs_saturation: FloatProperty(name="Saturation", default=0, min=-100, max=100, update=_value)
    hs_lightness: FloatProperty(name="Lightness", default=0, min=-100, max=100, update=_value)
    lv_in_black: FloatProperty(name="Input Black", default=0, min=0, max=255, update=_value)
    lv_in_white: FloatProperty(name="Input White", default=255, min=0, max=255, update=_value)
    lv_gamma: FloatProperty(name="Gamma", default=1.0, min=0.1, max=9.99, update=_value)
    lv_out_black: FloatProperty(name="Output Black", default=0, min=0, max=255, update=_value)
    lv_out_white: FloatProperty(name="Output White", default=255, min=0, max=255, update=_value)
    bc_brightness: FloatProperty(name="Brightness", default=0, min=-150, max=150, update=_value)
    bc_contrast: FloatProperty(name="Contrast", default=0, min=-100, max=100, update=_value)
    # Blend If (Photoshop's layer style sliders)
    blend_if: BoolProperty(name="Blend If", default=False, update=_structural,
                           description="Use the Blend If ramps (off: they cost nothing)")
    blend_if_channel: EnumProperty(name="Channel", items=[
        ("GREY", "Grey", ""), ("R", "Red", ""), ("G", "Green", ""), ("B", "Blue", "")])

    masks: CollectionProperty(type=PLASTRON_PG_mask)
    active_mask_index: IntProperty(default=0, update=_target_changed)
    paint_target: EnumProperty(items=[("LAYER", "Layer", "Paint the layer"),
                                      ("MASK", "Mask", "Paint the active mask")],
                               default="LAYER", update=_target_changed)

    # the compiled tree, by NAME (an ID pointer here would be followed by Blender's
    # threaded material preview while the tree is rebuilt -> crash; CaraPainter §55)
    node_tree_name: StringProperty()
    node_tree = property(_tree_get, _tree_set)

    @property
    def active_mask(self):
        if 0 <= self.active_mask_index < len(self.masks):
            return self.masks[self.active_mask_index]
        return None

    def ensure_uid(self):
        if not self.uid:
            self.uid = uuid.uuid4().hex[:10]
        return self.uid


class PLASTRON_PG_stack(bpy.types.PropertyGroup):
    enabled: BoolProperty(default=False)
    layers: CollectionProperty(type=PLASTRON_PG_layer)
    active_index: IntProperty(default=0, update=_target_changed)
    blend_space: EnumProperty(name="Blend Space", items=[
        ("SRGB", "Photoshop (sRGB)", "Blend gamma-encoded values like Photoshop"),
        ("LINEAR", "Linear", "Blend scene-linear values like Blender's Mix node"),
    ], default="SRGB", update=_structural)
    width: IntProperty(default=2400, min=16)
    height: IntProperty(default=1350, min=16)
    node_tree_name: StringProperty()
    node_tree = property(_tree_get, _tree_set)

    @property
    def active(self):
        if 0 <= self.active_index < len(self.layers):
            return self.layers[self.active_index]
        return None

    def by_uid(self, uid):
        for layer in self.layers:
            if layer.uid == uid:
                return layer
        return None


classes = (PLASTRON_PG_mask, PLASTRON_PG_layer, PLASTRON_PG_stack)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Material.plastron_stack = PointerProperty(type=PLASTRON_PG_stack)


def unregister():
    del bpy.types.Material.plastron_stack
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
