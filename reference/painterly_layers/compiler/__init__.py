"""Stack compiler: PropertyGroup data -> node trees (ARCHITECTURE §2).

compile_stack(): structural rebuild of the stack chain (+ any layer trees whose signature
changed). push_layer(): value-only update of one layer's instance sockets — no recompile.
"""
import bpy

from . import blend_lib, layers as layer_trees
from .nodes import NB, NotSynced, iface

STACK_PREFIX = ".PL Stack "
_retired = set()   # names of replaced trees, deleted once no material preview is rendering (§55)


def retire(tree):
    """Never edit or delete a compiled tree in place: Blender's material preview renders in a
    thread and copies these trees while it runs (0.20.2 crashed rebuilding them under it)."""
    tree["pl_retired"] = True
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
        if t is None or not t.get("pl_retired"):
            _retired.discard(name)          # gone, or the name now belongs to a live tree
        elif t.users == 0:
            bpy.data.node_groups.remove(t)
            _retired.discard(name)
    return not _retired


def _collect_timer():
    try:
        done = collect()
    except Exception as e:   # (never let the timer die)
        print("CaraPainter: tree cleanup:", e)
        done = True
    return None if done else 0.5


def children(stack, parent_uid):
    return [l for l in stack.layers if l.parent_uid == parent_uid]


def _instance_name(layer):
    return "L." + layer.uid


def compile_stack(mat):
    stack = mat.pl_stack
    if not stack.enabled:
        return
    blend_lib.ensure_all()
    try:
        for layer in stack.layers:
            layer.ensure_uid()
            tree = layer.node_tree
            if tree is None or tree.get("pl_sig") != layer_trees.signature(layer, stack):
                layer_trees.build(layer, stack)
    except (NotSynced, KeyError) as e:
        if bpy.app.background or not _may_retry(mat.name, e):
            raise
        return

    # a FRESH stack tree too (§55), built completely, THEN swapped into the material's node(s);
    # same interface in the same order -> same socket identifiers, so the links survive
    old_tree = stack.node_tree
    tree = bpy.data.node_groups.new(STACK_PREFIX + mat.name, 'ShaderNodeTree')
    iface(tree, 'OUTPUT', "Color", 'NodeSocketColor')
    iface(tree, 'OUTPUT', "Alpha", 'NodeSocketFloat')
    try:
        _fill_stack_tree(mat, stack, tree)
    except (NotSynced, KeyError) as e:
        # a new node's sockets weren't synced yet (Blender skips the node update on the main
        # thread while its material-preview thread is updating): drop the unused half-built
        # tree, try again soon. Headless (no previews) any such error is a real bug: raise.
        bpy.data.node_groups.remove(tree)
        if bpy.app.background or not _may_retry(mat.name, e):
            raise
        return
    stack.node_tree = tree
    if old_tree is not None:
        for n in (mat.node_tree.nodes if mat.node_tree else ()):
            if n.type == 'GROUP' and n.node_tree == old_tree:
                n.node_tree = tree
        retire(old_tree)
    for layer in stack.layers:
        push_layer(mat, layer, _tree=tree)
    from ..ops.attach import repair_links
    repair_links(mat)
    _tries.pop(mat.name, None)   # a full rebuild went through


_retry = set()
_tries = {}


def _may_retry(name, err):
    """Retry a rebuild that met an unsynced node; give up (and report) after many quiet tries."""
    n = _tries.get(name, 0) + 1
    _tries[name] = n
    if n > 25:
        _tries.pop(name, None)
        print(f"CaraPainter: rebuilding '{name}' keeps failing: {err!r}")
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
                if name not in _retry:
                    _tries.pop(name, None)       # it went through
            except Exception as e:
                print("CaraPainter: rebuild retry:", e)
    return 0.2 if _retry else None


def _fill_stack_tree(mat, stack, tree):
    nb = NB(tree)
    go = nb.node('NodeGroupOutput')
    shared = {}

    def key():
        """The stack's one Key Light helper (direction + strength at this point, §59)."""
        if "key" not in shared:
            geo = nb.node('ShaderNodeNewGeometry')
            shared["key"] = nb.group(blend_lib.key_light_group(), Position=geo.outputs["Position"])
        return shared["key"]

    def provide(name):
        """What the stack computes ONCE for every layer that asks (§54, §59)."""
        if name not in shared:
            if name == "Cast":
                shared[name] = layer_trees.cast_test(nb, stack, "STACK.shadow", kl=key())
            elif name == "KeyDir":
                shared[name] = key().outputs["Direction"]
            elif name.startswith("NLev"):
                if "levels" not in shared:
                    shared["levels"] = layer_trees.normal_levels(nb, stack)
                lv = shared["levels"]
                k = int(name[4:])
                shared[name] = lv[k] if k < len(lv) else lv[0]
            else:
                return None
        return shared[name]

    def chain(parent_uid, under, under_a, under_h):
        for layer in children(stack, parent_uid):
            node = nb.node('ShaderNodeGroup', name=_instance_name(layer), node_tree=layer.node_tree)
            if node.inputs.get("Under") is None:
                raise NotSynced(layer.node_tree.name)
            for k, v in (("Under", under), ("UnderA", under_a), ("UnderH", under_h)):
                nb.feed(node.inputs[k], v)
            node.label = layer.name
            for name in layer_trees.shared_names(layer.node_tree):
                if node.inputs.get(name) is not None:
                    src = provide(name)
                    if src is not None:
                        nb.feed(node.inputs[name], src)
            if layer.layer_type == "GROUP":
                # heights are physical: even an isolated group's content sits on what's beneath
                if layer.group_mode == "PASS_THROUGH":
                    c, a, h = chain(layer.uid, under, under_a, under_h)
                else:
                    c, a, h = chain(layer.uid, (0, 0, 0, 1), 0.0, under_h)
                nb.feed(node.inputs["Content"], c)
                nb.feed(node.inputs["ContentA"], a)
                nb.feed(node.inputs["ContentH"], h)
            under, under_a, under_h = node.outputs["Out"], node.outputs["OutA"], node.outputs["OutH"]
        return under, under_a, under_h

    # height at the bottom of the stack = the creature's own (normal-derived) height
    # (only when something compares heights: no sampler spent otherwise)
    base_h = 0.5
    if stack.height_image is not None and any(m.source == "HEIGHT" for l in stack.layers for m in l.masks):
        hd = nb.node('ShaderNodeValue', name="BASE.hdetail")
        hd.outputs[0].default_value = stack.height_detail
        base_h = layer_trees.depth(nb, stack, hd.outputs[0], "BASE.height")
    col, alpha, _h = chain("", (0, 0, 0, 1), 0.0, base_h)
    act = stack.active
    if stack.mask_view and act is not None and tree.nodes.get(_instance_name(act)) is not None:
        # View Mask: the active layer's mask in greyscale (already display values)
        m = tree.nodes[_instance_name(act)].outputs["Mask"]
        col = nb.comb(m, m, m)
        if stack.blend_space == "SRGB":
            col = nb.group(blend_lib.to_linear_group(), Color=col).outputs[0]
        alpha = 1.0
    elif stack.blend_space == "SRGB" and isinstance(col, bpy.types.NodeSocket):
        col = nb.group(blend_lib.to_linear_group(), Color=col).outputs[0]
    if stack.outline_paint and stack.outline_mask is not None and not stack.mask_view:
        # Paint Outline (§48): green where a line is forced, red where it's removed, grey = as is
        om = nb.node('ShaderNodeTexImage', name="OUTLINE.mask", interpolation='Linear')
        om.image = stack.outline_mask
        nb.feed(om.inputs[0], layer_trees._uv(nb, stack))
        k = nb.mul(nb.sub(nb.sep(om.outputs["Color"])[0], 0.5), 2.0)
        col = nb.mixc(nb.mul(nb.clamp(k), 0.65), col, (0.05, 0.9, 0.1, 1.0))
        col = nb.mixc(nb.mul(nb.clamp(nb.mul(k, -1.0)), 0.65), col, (0.9, 0.05, 0.05, 1.0))
    nb.feed(go.inputs["Color"], col)
    nb.feed(go.inputs["Alpha"], alpha)


def push_layer(mat, layer, _tree=None):
    stack = mat.pl_stack
    tree = _tree or stack.node_tree
    if tree is None:
        return
    node = tree.nodes.get(_instance_name(layer))
    if node is None or layer.node_tree is None or \
            layer.node_tree.get("pl_sig") != layer_trees.signature(layer, stack):
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
    if layer.layer_type == "FILL":   # Box projection blend lives on the image nodes
        for n in layer.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.projection == 'BOX' and abs(n.projection_blend - layer.box_blend) > 1e-6:
                n.projection_blend = layer.box_blend


def push_mask(mat, mask):
    """Value change on a mask element: push to the layer that owns it."""
    for layer in mat.pl_stack.layers:
        if any(m.uid == mask.uid for m in layer.masks):
            push_layer(mat, layer)
            return


def material_images(mat):
    """Unique images a material samples (EEVEE allows 32 samplers per material, 2 reserved)."""
    seen, out = set(), []

    def walk(tree):
        if tree is None or tree.name in seen:
            return
        seen.add(tree.name)
        for n in tree.nodes:
            if n.type in ('TEX_IMAGE', 'TEX_ENVIRONMENT') and n.image and n.image not in out \
                    and any(o.is_linked for o in n.outputs):
                out.append(n.image)
            elif n.type == 'GROUP':
                walk(n.node_tree)

    walk(mat.node_tree)
    return out


SAMPLER_BUDGET = 30
