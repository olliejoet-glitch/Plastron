"""Data model (ARCHITECTURE §3). Source of truth; node trees are compiled from this.

Material.pl_stack holds the layer list. Index 0 = BOTTOM of the stack; the UI draws it reversed.
Groups are a flat list + parent_uid: a group's children sit directly BELOW the group entry.
"""
import math
import uuid

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)

# Photoshop order (Dissolve omitted). Identifier -> (UI name, short label for the layer row)
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
    ("PAINT", "Paint", "Image painted with Texture Paint", 'BRUSH_DATA', 1),
    ("ADJUST", "Adjustment", "Adjusts everything below it", 'MODIFIER', 2),
    ("NORMAL_LIGHT", "Normal Light", "Diffuse light from the normal map and key light", 'LIGHT_SUN', 3),
    ("SPEC_LIGHT", "Specular Light", "Highlight from key light and camera", 'SHADING_RENDERED', 4),
    ("GROUP", "Group", "Group of layers", 'FILE_FOLDER', 5),
    ("RIM_LIGHT", "Rim Light", "Fresnel: surfaces turning edge-on to the camera light up (optionally "
                               "coloured by a stylised sky/ground reflection gradient)", 'LIGHT_HEMI', 6),
    ("SSS_LIGHT", "Subsurface", "Stylised subsurface scattering: a glow where light turns into shadow, "
                                "or thin parts glowing when back-lit", 'SHADING_RENDERED', 7),
]
LIGHT_TYPES = ("NORMAL_LIGHT", "SPEC_LIGHT", "RIM_LIGHT", "SSS_LIGHT")

_suspend = 0  # >0 while bulk-editing (duplicate, load) so update callbacks don't recompile


class suspended:
    def __enter__(self):
        global _suspend
        _suspend += 1

    def __exit__(self, *a):
        global _suspend
        _suspend -= 1


def _tree_get(self):
    if self.node_tree_name:
        return bpy.data.node_groups.get(self.node_tree_name)
    raw = self.get("node_tree")   # a pre-0.20.3 pointer not migrated yet (see migrate_tree_pointers)
    return raw if isinstance(raw, bpy.types.NodeTree) else None


def _tree_set(self, tree):
    self.node_tree_name = tree.name if tree is not None else ""
    if "node_tree" in self.keys():
        del self["node_tree"]


def _structural(self, context):
    if _suspend:
        return
    from .compiler import compile_stack
    compile_stack(self.id_data)


def _outline_paint(self, context):
    if _suspend:
        return
    from .compiler import compile_stack
    from .ops.layers import sync_paint_target
    compile_stack(self.id_data)
    sync_paint_target(context, self.id_data)


def _value(self, context):
    if _suspend:
        return
    from .compiler import push_layer
    push_layer(self.id_data, self)


def _mask_value(self, context):
    if _suspend:
        return
    from .compiler import push_mask
    push_mask(self.id_data, self)


_selecting = 0   # >0 while a selection op sets the active layer (keep the multi-selection)


def _active_changed(self, context):
    if _suspend:
        return
    # (also the update of a layer's paint target / active mask: then self is a PL_Layer)
    if not _selecting and isinstance(self, PL_Stack):   # changing the active layer any other way selects just it
        act = self.active
        for l in self.layers:
            if l.selected != (act is not None and l.uid == act.uid):
                l.selected = act is not None and l.uid == act.uid
    from .ops.layers import sync_paint_target
    sync_paint_target(context, self.id_data)
    if self.id_data.pl_stack.mask_view:  # View Mask follows the active layer
        from .compiler import compile_stack
        compile_stack(self.id_data)


MASK_SOURCES = [
    ("DEPTH", "Depth", "Height from the normal map: low = grooves and pits, high = raised forms", 'MOD_DISPLACE', 0),
    ("CURVATURE", "Curvature", "Edges (convex) or cavities from the normal map", 'SPHERECURVE', 1),
    ("IMAGE", "Image", "Any greyscale image, e.g. an AO or curvature map exported from Substance", 'IMAGE_DATA', 2),
    ("PAINT", "Paint", "Paint the mask directly: white shows the layer, black hides it", 'BRUSH_DATA', 3),
    ("SHADOW", "Cast Shadow", "Where the key light reaches (cast shadows from other parts / objects "
                              "are black). Invert for the shadows", 'LIGHT_SUN', 4),
    ("TERMINATOR", "Light Side", "The side of the form facing the key light (white) vs turned away",
     'SHADING_SOLID', 5),
    ("HEIGHT", "Height Blend", "Show the layer where its height is above the height beneath it "
                               "(the creature's depth + the heights of the layers below): fills the "
                               "low areas first, like Substance height blending", 'IMAGE_ZDEPTH', 6),
    ("NOISE", "Noise", "Procedural noise (clouds or cells) fixed to the model, even when it is posed",
     'FORCE_TURBULENCE', 7),
]
MASK_OPS = [
    ("MULTIPLY", "Multiply", "Keep only where both are white"),
    ("ADD", "Add", "Add to the mask"),
    ("SUBTRACT", "Subtract", "Cut out of the mask"),
    ("MAX", "Max (Lighten)", ""),
    ("MIN", "Min (Darken)", ""),
    ("OVERLAY", "Overlay", ""),
]


class PL_Mask(bpy.types.PropertyGroup):
    uid: StringProperty()
    name: StringProperty(default="Mask")
    source: EnumProperty(name="Source", items=MASK_SOURCES, default="DEPTH", update=_structural)
    op: EnumProperty(name="Combine", items=MASK_OPS, default="MULTIPLY", update=_structural)
    visible: BoolProperty(default=True, update=_mask_value)
    opacity: FloatProperty(name="Opacity", default=1.0, min=0, max=1, subtype='FACTOR', update=_mask_value)
    threshold: FloatProperty(name="Threshold", default=0.5, min=0, max=1, update=_mask_value,
                             description="Depth: where the cut sits (low = only the deepest parts)")
    softness: FloatProperty(name="Softness", default=0.08, min=0, max=0.5, update=_mask_value)
    invert: BoolProperty(name="Invert", default=False, update=_mask_value,
                         description="Depth: off = the raised parts, on = the low parts")
    detail: FloatProperty(name="Detail Size", default=0.35, min=0, max=1, subtype='FACTOR', update=_mask_value,
                          description="Size of the forms the mask follows: small = fine scales and grooves, "
                                      "large = broad plates")
    curvature_kind: EnumProperty(name="Kind", items=[("CONVEX", "Edges", ""), ("CAVITY", "Cavities", "")],
                                 default="CONVEX", update=_mask_value)
    image: PointerProperty(name="Image", type=bpy.types.Image, update=_mask_value)
    correction: PointerProperty(name="Correction", type=bpy.types.Image, update=_structural,
                                description="Paint white to push depth up, black to push it down")
    correction_strength: FloatProperty(name="Correction Strength", default=0.5, min=0, max=1,
                                       subtype='FACTOR', update=_mask_value)
    noise_type: EnumProperty(name="Pattern", items=[("NOISE", "Clouds", "Soft cloudy noise"),
                                                    ("CELLS", "Cells", "Cell pattern (dark centres, light edges)")],
                             default="NOISE", update=_structural)
    noise_scale: FloatProperty(name="Scale", default=6.0, min=0.1, max=400, soft_max=100, update=_mask_value,
                               description="How many blobs fit across the model (Ctrl+D drag)")
    noise_detail: FloatProperty(name="Detail", default=2.0, min=0, max=15, update=_mask_value)
    noise_roughness: FloatProperty(name="Roughness", default=0.5, min=0, max=1, subtype='FACTOR',
                                   update=_mask_value)
    noise_distortion: FloatProperty(name="Distortion", default=0.0, min=0, max=20, update=_mask_value)
    noise_seed: FloatProperty(name="Seed", default=0.0, min=0, max=1000, update=_mask_value,
                              description="Change for a different pattern")

    def ensure_uid(self):
        if not self.uid:
            self.uid = uuid.uuid4().hex[:10]
        return self.uid


SPEC_MAX_ANGLE = math.pi / 4   # Size 1 = highlight radius of 45 deg (between normal and half-vector)


def _cast_shadow_layer(layer):
    """A Shadow layer with Include Cast Shadows: its side turned away is pinned to shadow, so its
    Size slider only spans the side facing the light (§47)."""
    return layer.layer_type == "NORMAL_LIGHT" and layer.include_cast_shadow


def size_from_threshold(layer):
    """Threshold (N.L, or the specular value) -> 0..1 Size with even visible steps: the light /
    shadow edge moves equal angles across the form, a highlight's radius grows evenly."""
    t = layer.light_threshold
    if layer.layer_type == "SSS_LIGHT":   # value 0..1 (glow / translucency strength): Size = how much shows
        return max(0.0, min(1.0, 1.0 - t))
    if layer.layer_type == "RIM_LIGHT":   # value = 1 - N.V: Size = how far the rim reaches in, by angle
        c = max(-1.0, min(1.0, 1.0 - t))
        return 1.0 - math.acos(c) / (math.pi / 2) if c >= 0 else 1.0
    if layer.layer_type == "SPEC_LIGHT":
        if t <= 0:
            return 1.0
        c = min(1.0, t ** (1.0 / max(layer.spec_tightness, 1.0)))
        return min(1.0, math.acos(c) / SPEC_MAX_ANGLE)
    if layer.light_polarity == "SHADOW":
        if _cast_shadow_layer(layer):   # the side turned away is always shadow: 0 = just that
            return math.asin(max(0.0, min(1.0, t))) / (math.pi / 2)
        t = -t
    return math.acos(max(-1.0, min(1.0, t))) / math.pi


def threshold_from_size(layer, u):
    u = max(0.0, min(1.0, u))
    if layer.layer_type == "SSS_LIGHT":
        return 1.0 - u
    if layer.layer_type == "RIM_LIGHT":
        return 1.0 - math.cos((1.0 - u) * math.pi / 2)
    if layer.layer_type == "SPEC_LIGHT":
        return math.cos(u * SPEC_MAX_ANGLE) ** max(layer.spec_tightness, 1.0)
    if layer.light_polarity == "SHADOW" and _cast_shadow_layer(layer):
        return math.sin(u * math.pi / 2)   # §47: 0 = the side turned away .. 1 = everywhere, even angles
    t = math.cos(u * math.pi)
    return -t if layer.light_polarity == "SHADOW" else t


def _get_size(self):
    return size_from_threshold(self)


def _set_size(self, u):
    self.light_threshold = threshold_from_size(self, u)


def _get_tight(self):
    return self.get("spec_tightness", 40.0)   # same ID-property key as the old plain property


def _set_tight(self, v):
    if _suspend:   # creating / copying a layer: store as given (its threshold is set separately)
        self["spec_tightness"] = max(1.0, min(512.0, v))
        return
    u = size_from_threshold(self) if self.layer_type == "SPEC_LIGHT" else None
    self["spec_tightness"] = max(1.0, min(512.0, v))
    if u is not None:
        self.light_threshold = threshold_from_size(self, u)   # keep the Size; also pushes values
    else:
        _value(self, None)


class PL_Layer(bpy.types.PropertyGroup):
    uid: StringProperty()
    name: StringProperty(default="Layer")
    layer_type: EnumProperty(items=LAYER_TYPES, default="FILL", update=_structural)
    parent_uid: StringProperty()
    expanded: BoolProperty(default=True, description="Show the layers in this group")
    selected: BoolProperty(default=False)   # multi-selection (the active layer always counts)
    # --- built-in colour adjustments on every layer (§40): live once moved off the defaults
    la_hue: FloatProperty(name="Hue", default=0, min=-180, max=180, update=_value)
    la_saturation: FloatProperty(name="Saturation", default=1, min=0, max=2, update=_value)
    la_value: FloatProperty(name="Value", default=1, min=0, max=2, update=_value)
    la_curve: BoolProperty(name="Curve", default=False, update=_structural,
                           description="A curve graph on this layer's colour (combined and R / G / B), "
                                       "like Photoshop's Curves")

    visible: BoolProperty(default=True, update=_value, description="Show / hide layer (V)")
    opacity: FloatProperty(name="Opacity", default=1.0, min=0.0, max=1.0, subtype='FACTOR',
                           update=_value)
    blend_mode: EnumProperty(name="Blend Mode", items=BLEND_MODES, default="NORMAL",
                             update=_structural)
    group_mode: EnumProperty(name="Group Mode", items=[
        ("PASS_THROUGH", "Pass Through", "Children blend straight into the layers below"),
        ("ISOLATED", "Normal (isolated)", "Children are composited first, then blended as one"),
    ], default="PASS_THROUGH", update=_structural)

    # --- fill
    fill_source: EnumProperty(name="Source", items=[("COLOR", "Colour", ""), ("IMAGE", "Image", "")],
                              default="COLOR", update=_structural)
    fill_color: FloatVectorProperty(name="Colour", subtype='COLOR_GAMMA', size=3, min=0, max=1,
                                    default=(0.5, 0.5, 0.5), update=_value)
    fill_image: PointerProperty(name="Image", type=bpy.types.Image, update=_value)
    lib_set: StringProperty(name="Library Texture")   # library set key the fill came from (display)
    projection: EnumProperty(name="Projection", items=[
        ("UV", "UV", "Use the UV map"),
        ("BOX", "Box", "Project from the sides (triplanar): no UV seams or stretching; fixed to the "
                       "rest pose, so it doesn't swim when the creature is posed")],
        default="UV", update=_structural)
    box_blend: FloatProperty(name="Blend", default=0.25, min=0, max=1, subtype='FACTOR', update=_value,
                             description="Box projection: how softly the sides blend into each other")
    tex_scale: FloatProperty(name="Scale", default=1.0, min=0.01, max=200, soft_max=40, update=_value,
                             description="Repeats across the UV square (UV) or across the model (Box)")
    tex_rotation: FloatProperty(name="Rotation", default=0.0, subtype='ANGLE', update=_value)
    tex_offset: FloatVectorProperty(name="Offset", size=2, default=(0.0, 0.0), update=_value)
    tile_break: FloatProperty(name="Tiling Break", default=0.0, min=0, max=1, subtype='FACTOR', update=_value,
                              description="Blend in a rotated, shifted copy in random patches so the "
                                          "repeats don't show")
    tile_break_size: FloatProperty(name="Patch Size", default=2.0, min=0.1, max=50, update=_value,
                                   description="Tiling break: size of the patches, in tiles")
    # --- paint
    paint_image: PointerProperty(name="Image", type=bpy.types.Image, update=_value)
    # --- adjustment
    adjust_kind: EnumProperty(name="Adjustment", items=[
        ("HUE_SAT", "Hue/Saturation", ""), ("LEVELS", "Levels", ""),
        ("BRIGHT_CONTRAST", "Brightness/Contrast", ""), ("CURVES", "Curves", ""),
    ], default="HUE_SAT", update=_structural)
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
    # --- light layers (Phase 1 basics; painterly controls arrive in Phase 3)
    light_color: FloatVectorProperty(name="Colour", subtype='COLOR_GAMMA', size=3, min=0, max=1,
                                     default=(1.0, 0.85, 0.6), update=_value)
    light_threshold: FloatProperty(name="Threshold", default=0.2, min=-1, max=1, update=_value)
    light_softness: FloatProperty(name="Softness", default=0.15, min=0, max=1, update=_value)
    light_size: FloatProperty(name="Size", min=0, max=1, subtype='FACTOR', get=_get_size, set=_set_size,
                              description="How much of the form the light / shadow / highlight covers, in even "
                                          "steps (Shift+F drags it)")
    light_bands: IntProperty(name="Bands", default=0, min=0, max=12, update=_value,
                             description="Posterise into this many steps (0 = smooth)")
    spec_tightness: FloatProperty(name="Tightness", default=40, min=1, max=512, get=_get_tight, set=_set_tight,
                                  description="Highlight falloff (Size stays the same)")
    light_override: BoolProperty(name="Override Direction", default=False, update=_value,
                                 description="Use this layer's own direction instead of the key light")
    light_dir: FloatVectorProperty(name="Direction", subtype='DIRECTION', size=3,
                                   default=(0.4, -0.5, 0.75), update=_value)
    form_size: FloatProperty(name="Form Size", default=0.0, min=0, max=1, subtype='FACTOR', update=_value,
                             description="Blur the normals before lighting: small = every scale, large = broad "
                                         "planes. Stack light layers at different sizes (F drags it)")
    normal_strength: FloatProperty(name="Normal Strength", default=1.0, min=0, max=10, update=_value,
                                   description="How much the normal map shapes the light (0 = mesh only)")
    light_polarity: EnumProperty(name="Polarity", items=[
        ("LIGHT", "Light", "Colour where the light falls"),
        ("SHADOW", "Shadow", "Colour where it doesn't: the shadow side (with Details: the dark side of "
                             "every small form)")], default="LIGHT", update=_structural)
    terminator_color: FloatVectorProperty(name="Terminator Colour", subtype='COLOR_GAMMA', size=3, min=0, max=1,
                                          default=(0.02, 0.02, 0.03), update=_value,
                                          description="Colour of the band where light turns into shadow")
    terminator_width: FloatProperty(name="Terminator Width", default=0.0, min=0, max=1, update=_value,
                                    description="Width of the terminator band (0 = none)")
    sss_mode: EnumProperty(name="Mode", items=[
        ("GLOW", "Glow", "Light bleeding past the terminator: a coloured band where light turns into "
                         "shadow (and along cast-shadow edges with Include Cast Shadows)"),
        ("TRANSLUCENT", "Translucency", "Thin parts (toes, webbing, shell edges) glow when the light is "
                                        "behind them. Needs the baked thickness map")],
        default="GLOW", update=_structural)
    sss_width: FloatProperty(name="Glow Width", default=0.35, min=0.01, max=1.0, update=_value,
                             description="How far the glow reaches into the shadow side")
    sss_distortion: FloatProperty(name="Distortion", default=0.3, min=0, max=1, update=_value,
                                  description="Translucency: how much the surface bends the light passing "
                                              "through (higher = softer, wider glow)")
    sss_power: FloatProperty(name="Focus", default=3.0, min=0.5, max=32, update=_value,
                             description="Translucency: how tightly the glow gathers around the light "
                                         "behind the model")
    rim_reflect: BoolProperty(name="Reflection Gradient", default=False, update=_structural,
                              description="Rim light: colour it by which way the surface reflects (a "
                                          "stylised sky above / ground below gradient), for a glossy sheen")
    include_cast_shadow: BoolProperty(name="Include Cast Shadows", default=False, update=_structural,
                                      description="Shadow mode: also shade where other parts block the key light")
    light_cast_shadow: BoolProperty(name="Blocked by Cast Shadows", default=True, update=_structural,
                                    description="Light mode: no light where other parts block the key light "
                                                "(normal-map bumps inside a cast shadow stay dark)")
    pinned_top: BoolProperty(default=False)  # group that always stays on top (hybrid lighting)
    height_source: EnumProperty(name="Height", items=[
        ("NONE", "None", "The layer doesn't change the height (Height Blend masks still compare against "
                         "Level)"),
        ("FLAT", "Flat", "The layer is a flat surface at Level (e.g. a coat of paint or mud)"),
        ("IMAGE", "Image", "A height map, e.g. the texture's displacement map (white = high)"),
        ("LUMINANCE", "Brightness", "The layer's own brightness (light = high)")],
        default="NONE", update=_structural,
        description="The layer's height, for Height Blend masks on the layers above (and its own)")
    height_image: PointerProperty(name="Height Map", type=bpy.types.Image, update=_structural)
    height_level: FloatProperty(name="Level", default=0.5, min=0, max=1, update=_value,
                                description="Height of the layer (0.5 = the creature's average surface)")
    height_strength: FloatProperty(name="Height Contrast", default=1.0, min=0, max=4, update=_value,
                                   description="How much the height map / brightness raises and lowers it")
    light_ramp: BoolProperty(name="Light Ramp", default=False, update=_structural,
                             description="A colour ramp on how much sun reaches each point (0 = in shadow or "
                                         "turned away, 1 = facing the sun): set its colours and transparency; a "
                                         "terminator is just a dark stop near the shadow end (§52)")
    light_ramp_start: StringProperty(default="", options={'HIDDEN'},
                                     description="The stops a NEW Light Ramp starts with (compiler/layers."
                                                 "LIGHT_RAMP_STARTS); once built, the ramp keeps your edits")
    use_ramp: BoolProperty(name="Colour Ramp", default=False, update=_structural,
                           description="Map the light to a colour ramp (colours and transparency along it)")
    breakup: EnumProperty(name="Edge Breakup", items=[
        ("NONE", "None", ""), ("NOISE", "Noise", "Procedural noise on the surface"),
        ("IMAGE", "Stroke Image", "Your own brush-stroke / texture image")], default="NONE", update=_structural)
    breakup_image: PointerProperty(name="Stroke Image", type=bpy.types.Image, update=_value)
    breakup_strength: FloatProperty(name="Strength", default=0.3, min=0, max=2, update=_value)
    breakup_scale: FloatProperty(name="Scale", default=8.0, min=0.01, max=500, update=_value)
    hybrid_owned: BoolProperty(default=False)  # starter layers made by the hybrid conversion
    blend_if: BoolProperty(name="Blend If", default=False, update=_structural,
                           description="Use the Blend If ramps (off: they cost nothing; dragging a "
                                       "stop turns this on)")
    # --- UI only
    blend_if_channel: EnumProperty(name="Channel", items=[
        ("GREY", "Grey", ""), ("R", "Red", ""), ("G", "Green", ""), ("B", "Blue", "")])

    masks: CollectionProperty(type=PL_Mask)
    active_mask_index: IntProperty(default=0)
    paint_target: EnumProperty(items=[("LAYER", "Layer", "Paint the layer"),
                                      ("MASK", "Mask", "Paint the active mask (depth masks: their correction)")],
                               default="LAYER", update=_active_changed)

    # the private compiled tree ".PL L <uid>", by NAME (§55): an ID pointer here is an ID property
    # of the material, which Blender's threaded material-preview render follows to the ORIGINAL
    # tree while we rebuild it on the main thread -> crash
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


class PL_LinkRecord(bpy.types.PropertyGroup):
    from_socket: StringProperty()   # identifier on the replaced node
    to_node: StringProperty()
    to_socket: StringProperty()     # identifier


class PL_AttachRecord(bpy.types.PropertyGroup):
    base_node: StringProperty()
    base_location: FloatVectorProperty(size=2)
    links: CollectionProperty(type=PL_LinkRecord)
    output_node: StringProperty()
    surface_from_node: StringProperty()
    surface_from_socket: StringProperty()


def _outline(self, context):
    from .ops import outline
    outline.apply(self.id_data)


class PL_Outline(bpy.types.PropertyGroup):
    """Scene.pl_outline: the silhouette outline's settings (pushed into the outline modifiers, §44)."""
    show: BoolProperty(name="Show Outline", default=True, update=_outline)
    color: FloatVectorProperty(name="Colour", subtype='COLOR', size=3, min=0, max=1,
                               default=(0.01, 0.01, 0.012), update=_outline)
    width: FloatProperty(name="Width", default=3.0, min=0.1, max=60, soft_max=12, update=_outline,
                         description="Line width in pixels of a 1080-line image (it scales with the image "
                                     "and keeps its on-screen size at any distance)")
    include: PointerProperty(type=bpy.types.Collection, name="Include", update=_outline,
                             description="Other objects that are part of the creature (eyes, claws, teeth): "
                                         "outlined together with it and hiding its lines")
    light: FloatProperty(name="Light Strength", default=1.0, min=0, max=1, subtype='FACTOR', update=_outline,
                         description="The outline where the key light falls (0 = none there)")
    shadow: FloatProperty(name="Shadow Strength", default=0.0, min=0, max=1, subtype='FACTOR', update=_outline,
                          description="The outline in shadow, incl. cast shadows (0 = none there)")
    sketch: BoolProperty(name="Sketchy", default=False, update=_outline,
                         description="Hand-drawn look: wobbling, overlapping strokes of varying width")
    strokes: IntProperty(name="Strokes", default=2, min=1, max=3, update=_outline,
                         description="Overlapping strokes, like repeated pencil passes")
    wobble: FloatProperty(name="Wobble", default=0.3, min=0, max=1, update=_outline)
    width_var: FloatProperty(name="Width Variation", default=0.6, min=0, max=1, update=_outline,
                             description="Thick-and-thin, tapering lines")
    scale: FloatProperty(name="Scale", default=6.0, min=0.5, max=100, update=_outline,
                         description="Size of the wobbles (higher = shorter, busier strokes)")
    seed: IntProperty(name="Seed", default=0, min=0, max=1000, update=_outline)


def _base_height(self, context):
    """Stack-level value: lives on a Value node in the stack tree (no recompile)."""
    tree = self.node_tree
    n = tree.nodes.get("BASE.hdetail") if tree is not None else None
    if n is not None:
        n.outputs[0].default_value = self.height_detail


class PL_Stack(bpy.types.PropertyGroup):
    version: IntProperty(default=1)
    enabled: BoolProperty(default=False)
    height_detail: FloatProperty(name="Creature Height Detail", default=0.35, min=0, max=1, subtype='FACTOR',
                                 update=_base_height,
                                 description="Height Blend: the creature's own height (from the normal map) "
                                             "at fine scales (0) or broad plates (1)")
    layers: CollectionProperty(type=PL_Layer)
    active_index: IntProperty(default=0, update=_active_changed)
    blend_space: EnumProperty(name="Blend Space", items=[
        ("SRGB", "Photoshop (sRGB)", "Blend gamma-encoded values like Photoshop"),
        ("LINEAR", "Linear", "Blend scene-linear values like Blender's Mix node"),
    ], default="SRGB", update=_structural)
    resolution: IntProperty(default=2048, min=64, max=16384)
    uv_map: StringProperty(name="UV Map", default="", update=_structural)
    normal_image: PointerProperty(name="Normal Map", type=bpy.types.Image, update=_structural)
    height_image: PointerProperty(type=bpy.types.Image, update=_structural)     # cached, analysis/
    curvature_image: PointerProperty(type=bpy.types.Image, update=_structural)  # cached, analysis/
    forms_a: PointerProperty(type=bpy.types.Image, update=_structural)          # cached, analysis/
    forms_b: PointerProperty(type=bpy.types.Image, update=_structural)          # cached, analysis/
    forms_c: PointerProperty(type=bpy.types.Image, update=_structural)          # cached, analysis/
    hybrid: BoolProperty(default=False)
    hybrid_output: StringProperty()      # our Material Output while hybrid is on
    hybrid_prev_output: StringProperty()  # the user's output to restore
    mode: EnumProperty(items=[("LIVE", "Live", "Layers are evaluated live (node groups)"),
                              ("BAKED", "Baked", "A baked image replaces the stack")], default="LIVE")
    baked_image: PointerProperty(type=bpy.types.Image)
    bake_variant: BoolProperty(default=False, update=_structural)   # compiling for a Cycles bake
    bake_shadow_image: PointerProperty(type=bpy.types.Image)        # Cycles shadow pass while baking
    thickness_image: PointerProperty(type=bpy.types.Image, update=_structural)   # translucency (§36)
    outline_object: PointerProperty(type=bpy.types.Object)   # §38 Line Art (removed when found)
    thickness_range: FloatProperty(name="Thickness Range", default=0.15, min=0.01, max=2.0,
                                   description="Translucency: how thick (as a share of the model's size) "
                                               "still lets light through. Bake again after changing it")
    mask_view: BoolProperty(name="View Mask", default=False, update=_structural,
                            description="Show the active layer's mask in greyscale instead of the colours")
    outline_mask: PointerProperty(type=bpy.types.Image, update=_structural)   # §48: where the outline goes
    outline_paint: BoolProperty(name="Paint Outline", default=False, update=_outline_paint,
                                description="Paint where the outline goes: white = always a line (even in "
                                            "shadow), black = never, grey = automatic")
    node_tree_name: StringProperty()   # the stack tree, by name (see PL_Layer.node_tree_name, §55)
    attach: PointerProperty(type=PL_AttachRecord)

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


def _key_light_changed(self, context):
    from .ops.keylight import setup_key_light_drivers
    setup_key_light_drivers(self)


classes = (PL_Mask, PL_Layer, PL_LinkRecord, PL_AttachRecord, PL_Stack, PL_Outline)


def _get_light_widget(self):
    from .ops.keylight import get_light_widget
    return get_light_widget(self)


def _set_light_widget(self, value):
    from .ops.keylight import set_light_widget
    set_light_widget(self, value)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.pl_sel_feather = FloatProperty(
        name="Feather", default=0.0, min=0.0, max=64.0, subtype='PIXEL',
        description="Soften the edge of new lasso selections (texture pixels)")
    bpy.types.Scene.pl_light_widget = FloatVectorProperty(
        name="Light Direction", subtype='DIRECTION', size=3,
        get=_get_light_widget, set=_set_light_widget,
        description="Drag to move the light. The bright spot shows where the light comes from, "
                    "as seen from the current view")
    bpy.types.Material.pl_stack = PointerProperty(type=PL_Stack)
    bpy.types.Scene.pl_outline = PointerProperty(type=PL_Outline)
    bpy.types.Scene.pl_key_light = PointerProperty(
        name="Key Light", type=bpy.types.Object, update=_key_light_changed,
        poll=lambda self, ob: ob.type == 'LIGHT',
        description="The scene's key light. Light layers in every material follow it")


def migrate_tree_pointers():
    """Files from before 0.20.3 hold the trees as ID pointers (raw ID properties now): keep the
    name, drop the pointer - so the material preview thread can't follow it (§55)."""
    n = 0
    for mat in bpy.data.materials:
        st = mat.pl_stack
        for holder in [st, *st.layers]:
            raw = holder.get("node_tree")
            if raw is not None or "node_tree" in holder.keys():
                if isinstance(raw, bpy.types.ID) and not holder.node_tree_name:
                    holder.node_tree_name = raw.name
                del holder["node_tree"]
                n += 1
    return n


def unregister():
    del bpy.types.Scene.pl_light_widget
    del bpy.types.Scene.pl_sel_feather
    del bpy.types.Scene.pl_key_light
    del bpy.types.Material.pl_stack
    del bpy.types.Scene.pl_outline
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
