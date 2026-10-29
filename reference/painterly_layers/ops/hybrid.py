"""Hybrid conversion (ARCHITECTURE §7.4): lighting moves into painterly layers.

On: a Material Output of ours becomes the active one, showing the stack (whose light layers and
Cast Shadow / Light Side masks now do the lighting). The first time, starter layers mirror the
user's passes (shadow ramp + Darken, ambient Screen, highlight Color Dodge), reading colours and
strengths from those nodes when they exist. Off: the user's own output is active again and the
starter layers are hidden. Nothing of the user's is changed or deleted, so it is fully reversible.
"""
import bpy

from .. import props
from ..compiler import compile_stack
from .attach import STACK_NODE, active_output
from .layers import add_layer, get_stack
from .masks import add_mask

HYBRID_OUT = "PL Hybrid Output"
HYBRID_EMIT = "PL Hybrid Emission"


def _enc(c):
    return tuple(x * 12.92 if x < 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055 for x in c[:3])


def _ramp_colour(tree, name, index, default):
    n = tree.nodes.get(name)
    if n is None or n.type != 'VALTORGB':
        return default
    els = n.color_ramp.elements
    return _enc(tuple(els[index].color)) if len(els) else default


def _factor(tree, name, default):
    n = tree.nodes.get(name)
    if n is None or n.type != 'MIX' or n.inputs[0].is_linked:
        return default
    return float(n.inputs[0].default_value)


def _ramp_stop(tree, name, pos, default):
    """Colour of the ramp stop nearest `pos` (0..1)."""
    n = tree.nodes.get(name)
    if n is None or n.type != 'VALTORGB' or not len(n.color_ramp.elements):
        return default
    e = min(n.color_ramp.elements, key=lambda e: abs(e.position - pos))
    return _enc(tuple(e.color))


def _ramp_stop_linear(tree, name, pos, default):
    """Scene-linear colour of the ramp stop nearest `pos` (ramp colours are linear)."""
    n = tree.nodes.get(name)
    if n is None or n.type != 'VALTORGB' or not len(n.color_ramp.elements):
        return tuple(default)
    return tuple(min(n.color_ramp.elements, key=lambda e: abs(e.position - pos)).color[:3])


def _starter_layers(mat):
    """A pinned 'Lighting' group on top of the stack: main shadow (over every texture/detail,
    like the old Darken), ambient shine (Screen), highlight (Color Dodge)."""
    tree = mat.node_tree
    st = mat.pl_stack
    st.active_index = len(st.layers) - 1
    group = add_layer(mat, "GROUP", name="Lighting (hybrid)")
    g_uid = group.uid
    with props.suspended():
        st.by_uid(g_uid).pinned_top = True
        st.by_uid(g_uid).hybrid_owned = True
        st.by_uid(g_uid).expanded = True

    def inside(layer_type, **kw):
        st.active_index = next(i for i, l in enumerate(st.layers) if l.uid == g_uid)
        return add_layer(mat, layer_type, **kw).uid

    # the main shadow: a Light Ramp (§52) in the colours of the old shadow ramp
    from ..compiler.layers import LIGHT_RAMP, LIGHT_RAMP_DEFAULT, set_ramp
    shadow_col = _ramp_stop_linear(tree, "Color Ramp.004", 0.0, LIGHT_RAMP_DEFAULT[0][1][:3])
    term_col = _ramp_stop_linear(tree, "Color Ramp.004", 0.636, LIGHT_RAMP_DEFAULT[1][1][:3])
    sh = inside("NORMAL_LIGHT", name="Shadow (hybrid)", light_ramp=True, include_cast_shadow=True,
                blend_mode="NORMAL", form_size=0.35, opacity=_factor(tree, "Mix", 1.0))
    compile_stack(mat)
    rn = st.by_uid(sh).node_tree.nodes.get(LIGHT_RAMP)
    if rn is not None:
        set_ramp(rn.color_ramp, [(0.0, (*shadow_col, 1.0)), (0.04, (*term_col, 1.0)),
                                 (0.1, (1.0, 1.0, 1.0, 0.0)), (1.0, (1.0, 1.0, 1.0, 0.0))])
    uids = [sh]
    uids.append(inside("NORMAL_LIGHT", name="Ambient Shine (hybrid)", blend_mode="SCREEN",
                       light_color=_ramp_colour(tree, "Color Ramp.002", -1, (0.86, 0.95, 1.0)),
                       light_threshold=0.35, light_softness=0.05, form_size=0.35,
                       opacity=_factor(tree, "Mix.001", 0.35)))
    hi = inside("SPEC_LIGHT", name="Highlight (hybrid)", blend_mode="COLOR_DODGE",
                light_color=_ramp_colour(tree, "Color Ramp.003", -1, (0.8, 1.0, 0.98)),
                light_threshold=0.5, light_softness=0.1, spec_tightness=60,
                opacity=_factor(tree, "Mix.002", 0.47))
    uids.append(hi)
    # highlights only where the key light really arrives: cast shadow AND light side (user spec)
    add_mask(mat, st.by_uid(hi), "SHADOW", threshold=0.5, softness=0.25)
    add_mask(mat, st.by_uid(hi), "TERMINATOR", threshold=0.5, softness=0.04, op="MULTIPLY")
    with props.suspended():
        for u in uids:
            st.by_uid(u).hybrid_owned = True
    compile_stack(mat)


def enable(mat):
    st = mat.pl_stack
    tree = mat.node_tree
    group = tree.nodes.get(STACK_NODE)
    if group is None:
        raise RuntimeError("attach a layer stack first")
    prev = active_output(tree)
    out = tree.nodes.get(HYBRID_OUT)
    if out is None:
        out = tree.nodes.new('ShaderNodeOutputMaterial')
        out.name = out.label = HYBRID_OUT
        emit = tree.nodes.new('ShaderNodeEmission')
        emit.name = emit.label = HYBRID_EMIT
        x, y = group.location
        emit.location, out.location = (x + 300, y - 300), (x + 500, y - 300)
        tree.links.new(group.outputs["Color"], emit.inputs["Color"])
        tree.links.new(emit.outputs[0], out.inputs["Surface"])
    if prev is not None and prev != out:
        st.hybrid_prev_output = prev.name
    out.is_active_output = True
    st.hybrid_output = out.name
    st.hybrid = True
    from .layers import pinned_group, remove_layer
    if pinned_group(st) is None:
        # first time, or starter layers from 0.6.0 (no Lighting group yet): (re)build them
        for l in [l.uid for l in st.layers if l.hybrid_owned and not l.parent_uid]:
            remove_layer(mat, st.by_uid(l))
        _starter_layers(mat)
    else:
        for l in st.layers:
            if l.hybrid_owned:
                l.visible = True


def disable(mat):
    st = mat.pl_stack
    tree = mat.node_tree
    prev = tree.nodes.get(st.hybrid_prev_output)
    if prev is not None:
        prev.is_active_output = True
    for l in st.layers:
        if l.hybrid_owned:
            l.visible = False
    st.hybrid = False


class PL_OT_hybrid(bpy.types.Operator):
    bl_idname = "pl.hybrid_toggle"
    bl_label = "Hybrid Lighting"
    bl_description = ("Light the model with painterly layers instead of the shader's lighting passes "
                      "(adds starter layers copying them). Click again for the original setup")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None

    def execute(self, context):
        mat, st = get_stack(context)
        if not st.hybrid:  # hybrid lighting needs the scene's key light in Material Preview too
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.shading.use_scene_lights = True
                    area.spaces.active.shading.use_scene_world = True
        try:
            disable(mat) if st.hybrid else enable(mat)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (PL_OT_hybrid,)
