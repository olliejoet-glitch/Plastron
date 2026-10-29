"""Stack compiler: layer data -> node trees (ported from CaraPainter's compiler).

compile_stack(): structural rebuild of the stack (+ any layer trees whose
signature changed). push_layer(): value-only update (opacity, colours...) of
one layer's sockets, no recompile. The material shows the stack unlit
(emission) with its transparency, faded by the object's colour alpha (used
for onion skins).
"""

import bpy

from . import blend_lib, layer_trees
from .nodes import NB, NotSynced, iface

STACK_PREFIX = ".PLASTRON Stack "
STACK_NODE = "PLASTRON_STACK"
_retired = set()


def retire(tree):
    """Never edit or delete a compiled tree in place: Blender's material preview
    renders in a thread and copies these trees while it runs (CaraPainter §55)."""
    tree["plastron_retired"] = True
    _retired.add(tree.name)
    if bpy.app.background:
        collect()
    elif not bpy.app.timers.is_registered(_collect_timer):
        bpy.app.timers.register(_collect_timer, first_interval=0.5)


def collect():
    if not bpy.app.background and bpy.app.is_job_running('RENDER_PREVIEW'):
        return False
    for name in list(_retired):
        t = bpy.data.node_groups.get(name)
        if t is None or not t.get("plastron_retired"):
            _retired.discard(name)
        elif t.users == 0:
            bpy.data.node_groups.remove(t)
            _retired.discard(name)
    return not _retired


def _collect_timer():
    try:
        done = collect()
    except Exception as e:
        print("Plastron layers: tree cleanup:", e)
        done = True
    return None if done else 0.5


def children(stack, parent_uid):
    return [l for l in stack.layers if l.parent_uid == parent_uid]


def _instance_name(layer):
    return "L." + layer.uid


def ensure_material(mat):
    """Give a material Plastron's output: stack -> unlit colour + transparency."""
    mat.use_nodes = True
    mat.surface_render_method = 'BLENDED'
    mat.use_backface_culling = False
    nt = mat.node_tree
    if nt.nodes.get(STACK_NODE) is not None:
        return
    nt.nodes.clear()
    nb = NB(nt)
    stack_node = nb.node('ShaderNodeGroup', name=STACK_NODE)
    obj = nb.node('ShaderNodeObjectInfo')
    em = nb.node('ShaderNodeEmission')
    tr = nb.node('ShaderNodeBsdfTransparent')
    mix = nb.node('ShaderNodeMixShader')
    out = nb.node('ShaderNodeOutputMaterial')
    mat["plastron_nodes"] = {"obj": obj.name, "em": em.name, "mix": mix.name}
    nb.feed(mix.inputs[1], tr.outputs[0])
    nb.feed(mix.inputs[2], em.outputs[0])
    nb.feed(out.inputs["Surface"], mix.outputs[0])
    _wire_output(mat)


def _wire_output(mat):
    nt = mat.node_tree
    stack_node = nt.nodes.get(STACK_NODE)
    names = mat.get("plastron_nodes")
    if stack_node is None or stack_node.node_tree is None or names is None:
        return
    if stack_node.outputs.get("Color") is None:
        raise NotSynced(stack_node.node_tree.name)
    nb = NB(nt)
    em, mix, obj = nt.nodes[names["em"]], nt.nodes[names["mix"]], nt.nodes[names["obj"]]
    nb.feed(em.inputs["Color"], stack_node.outputs["Color"])
    nb.feed(mix.inputs[0], nb.mul(stack_node.outputs["Alpha"], obj.outputs["Alpha"]))


def compile_stack(mat):
    stack = mat.plastron_stack
    if not stack.enabled:
        return
    blend_lib.ensure_all()
    ensure_material(mat)
    try:
        for layer in stack.layers:
            layer.ensure_uid()
            tree = layer.node_tree
            if tree is None or tree.get("plastron_sig") != layer_trees.signature(layer, stack):
                layer_trees.build(layer, stack)
    except (NotSynced, KeyError) as e:
        if bpy.app.background or not _may_retry(mat.name, e):
            raise
        return

    old_tree = stack.node_tree
    tree = bpy.data.node_groups.new(STACK_PREFIX + mat.name, 'ShaderNodeTree')
    iface(tree, 'OUTPUT', "Color", 'NodeSocketColor')
    iface(tree, 'OUTPUT', "Alpha", 'NodeSocketFloat')
    try:
        _fill_stack_tree(stack, tree)
    except (NotSynced, KeyError) as e:
        bpy.data.node_groups.remove(tree)
        if bpy.app.background or not _may_retry(mat.name, e):
            raise
        return
    stack.node_tree = tree
    stack_node = mat.node_tree.nodes.get(STACK_NODE)
    first = stack_node.node_tree is None
    stack_node.node_tree = tree
    if first or (old_tree is None):
        _wire_output(mat)
    if old_tree is not None:
        retire(old_tree)
    for layer in stack.layers:
        push_layer(mat, layer, _tree=tree)
    _tries.pop(mat.name, None)


_retry = set()
_tries = {}


def _may_retry(name, err):
    n = _tries.get(name, 0) + 1
    _tries[name] = n
    if n > 25:
        _tries.pop(name, None)
        print(f"Plastron layers: rebuilding '{name}' keeps failing: {err!r}")
        return False
    _retry.add(name)
    if not bpy.app.timers.is_registered(_retry_timer):
        bpy.app.timers.register(_retry_timer, first_interval=0.2)
    return True


def _retry_timer():
    if bpy.app.is_job_running('RENDER_PREVIEW'):
        return 0.2
    for name in list(_retry):
        _retry.discard(name)
        mat = bpy.data.materials.get(name)
        if mat is not None:
            try:
                compile_stack(mat)
            except Exception as e:
                print("Plastron layers: rebuild retry:", e)
    return 0.2 if _retry else None


def _fill_stack_tree(stack, tree):
    nb = NB(tree)
    go = nb.node('NodeGroupOutput')

    def chain(parent_uid, under, under_a):
        for layer in children(stack, parent_uid):
            node = nb.node('ShaderNodeGroup', name=_instance_name(layer), node_tree=layer.node_tree)
            if node.inputs.get("Under") is None:
                raise NotSynced(layer.node_tree.name)
            nb.feed(node.inputs["Under"], under)
            nb.feed(node.inputs["UnderA"], under_a)
            node.label = layer.name
            if layer.layer_type == "GROUP":
                if layer.group_mode == "PASS_THROUGH":
                    c, a = chain(layer.uid, under, under_a)
                else:
                    c, a = chain(layer.uid, (0, 0, 0, 1), 0.0)
                nb.feed(node.inputs["Content"], c)
                nb.feed(node.inputs["ContentA"], a)
            under, under_a = node.outputs["Out"], node.outputs["OutA"]
        return under, under_a

    col, alpha = chain("", (0, 0, 0, 1), 0.0)
    if stack.blend_space == "SRGB" and isinstance(col, bpy.types.NodeSocket):
        col = nb.group(blend_lib.to_linear_group(), Color=col).outputs[0]
    nb.feed(go.inputs["Color"], col)
    nb.feed(go.inputs["Alpha"], alpha)


def push_layer(mat, layer, _tree=None):
    stack = mat.plastron_stack
    tree = _tree or stack.node_tree
    if tree is None:
        return
    node = tree.nodes.get(_instance_name(layer))
    if node is None or layer.node_tree is None or \
            layer.node_tree.get("plastron_sig") != layer_trees.signature(layer, stack):
        if _tree is None:
            compile_stack(mat)
        return
    node.label = layer.name
    for k, v in layer_trees.values(layer, stack).items():
        sock = node.inputs.get(k)
        if sock is not None:
            sock.default_value = v
    for name, img in layer_trees.images(layer, stack).items():
        n = layer.node_tree.nodes.get(name)
        if n is not None and n.image != img:
            n.image = img


def push_mask(mat, mask):
    for layer in mat.plastron_stack.layers:
        if any(m.uid == mask.uid for m in layer.masks):
            push_layer(mat, layer)
            return
