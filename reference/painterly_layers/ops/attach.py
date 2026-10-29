"""Attach / detach a layer stack to a material (ARCHITECTURE §4).

Attach swaps the base-colour image node for the stack group (recording every link it touches),
parks the original image node in a frame, and inserts a View Switch before the Material Output
(scene attribute pl_base_view: 0 = your shader, 1 = flat stack colour). Detach reverses it.
"""
import bpy

from .. import props
from ..compiler import compile_stack
from . import keylight

FRAME = "PL Original"
STACK_NODE = "PL Stack"
SWITCH = "PL View Switch"
SWITCH_ATTR = "PL View Attr"
SWITCH_EMIT = "PL View Emission"
BASE_VIEW = "pl_base_view"


def _downstream_hits(node, pred, seen=None):
    seen = seen if seen is not None else set()
    if node.name in seen:
        return False
    seen.add(node.name)
    for out in node.outputs:
        for link in out.links:
            if pred(link):
                return True
            if _downstream_hits(link.to_node, pred, seen):
                return True
    return False


def find_base_image_node(tree):
    """Colour image node that doesn't feed a normal input. Prefer one reaching the output."""
    cands = []
    for n in tree.nodes:
        if n.type != 'TEX_IMAGE' or n.image is None or not any(o.is_linked for o in n.outputs):
            continue
        if n.image.colorspace_settings.name in ('Non-Color', 'Raw'):
            continue
        feeds_normal = _downstream_hits(n, lambda l: l.to_node.type in ('NORMAL_MAP', 'BUMP')
                                        or l.to_socket.name == 'Normal')
        if feeds_normal:
            continue
        reaches_out = _downstream_hits(n, lambda l: l.to_node.type == 'OUTPUT_MATERIAL')
        cands.append((not reaches_out, -n.image.size[0], n))
    cands.sort(key=lambda c: c[:2])
    return cands[0][2] if cands else None


def find_normal_image(tree):
    for n in tree.nodes:
        if n.type == 'NORMAL_MAP':
            link = n.inputs["Color"].links[0] if n.inputs["Color"].is_linked else None
            if link and link.from_node.type == 'TEX_IMAGE' and link.from_node.image:
                return link.from_node.image
    return None


def active_output(tree):
    outs = [n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL']
    for n in outs:
        if n.is_active_output:
            return n
    return outs[0] if outs else None


def attach(mat, scene, base_node=None):
    stack = mat.pl_stack
    tree = mat.node_tree
    base = base_node or find_base_image_node(tree)
    if base is None:
        raise RuntimeError("No base-colour image node found")
    rec = stack.attach
    rec.links.clear()
    rec.base_node = base.name
    rec.base_location = base.location

    with props.suspended():
        stack.normal_image = find_normal_image(tree)
        uvs = [n for n in tree.nodes if n.type == 'NORMAL_MAP' and n.uv_map]
        stack.uv_map = uvs[0].uv_map if uvs else ""
        stack.enabled = True
    if len(stack.layers):  # re-attaching after a detach: keep the existing layers
        compile_stack(mat)
    else:
        _add_base_layer(mat, base)

    group = tree.nodes.new('ShaderNodeGroup')
    group.name = group.label = STACK_NODE
    group.node_tree = stack.node_tree
    group.location = base.location
    group.width = 200
    for out in base.outputs:
        target = group.outputs["Color"] if out.name == "Color" else group.outputs["Alpha"]
        for link in list(out.links):
            r = rec.links.add()
            r.from_socket = out.identifier
            r.to_node = link.to_node.name
            r.to_socket = link.to_socket.identifier
            tree.links.new(target, link.to_socket)  # replaces the old link on that input

    frame = tree.nodes.get(FRAME) or tree.nodes.new('NodeFrame')
    frame.name = frame.label = FRAME
    base.parent = frame
    base.location = (base.location[0], base.location[1] - 400)

    _insert_view_switch(mat, group)
    if BASE_VIEW not in scene:
        scene[BASE_VIEW] = 0.0
    if scene.pl_key_light is not None:
        keylight.setup_key_light_drivers(scene)  # (re)create the drivers (position, strength, camera)
    else:
        keylight.auto_detect(scene)
    if stack.normal_image is not None and not bpy.app.background:
        from ..analysis import cache
        cache.start(mat)  # height/curvature for depth masks, in the background
    from . import outline
    outline.add_for_material(mat, scene)   # a scene with an outline outlines this creature too
    return group


def _add_base_layer(mat, base):
    stack = mat.pl_stack
    with props.suspended():
        layer = stack.layers.add()
        layer.ensure_uid()
        layer.name = f"Base ({base.image.name})"
        layer.layer_type = "FILL"
        layer.fill_source = "IMAGE"
        layer.fill_image = base.image
        stack.active_index = 0
    compile_stack(mat)


def _insert_view_switch(mat, group):
    tree = mat.node_tree
    rec = mat.pl_stack.attach
    out = active_output(tree)
    if out is None or not out.inputs["Surface"].is_linked:
        rec.output_node = ""
        return
    link = out.inputs["Surface"].links[0]
    rec.output_node = out.name
    rec.surface_from_node = link.from_node.name
    rec.surface_from_socket = link.from_socket.identifier
    attr = tree.nodes.new('ShaderNodeAttribute')
    attr.name = attr.label = SWITCH_ATTR
    attr.attribute_type = 'VIEW_LAYER'
    attr.attribute_name = BASE_VIEW
    emit = tree.nodes.new('ShaderNodeEmission')
    emit.name = emit.label = SWITCH_EMIT
    mix = tree.nodes.new('ShaderNodeMixShader')
    mix.name = mix.label = SWITCH
    x, y = out.location
    attr.location, emit.location, mix.location = (x - 200, y + 200), (x - 200, y - 150), (x, y + 150)
    out.location = (x + 200, y)
    tree.links.new(attr.outputs["Fac"], mix.inputs[0])
    tree.links.new(link.from_socket, mix.inputs[1])
    tree.links.new(group.outputs["Color"], emit.inputs["Color"])
    tree.links.new(emit.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], out.inputs["Surface"])


BAKED_NODE = "PL Baked"
EMITTERS = ("PL View Emission", "PL Hybrid Emission")


def source_node(mat):
    """What feeds the material: the live stack group, or the baked image node in Baked mode."""
    tree = mat.node_tree
    if tree is None:
        return None
    if mat.pl_stack.mode == "BAKED":
        return tree.nodes.get(BAKED_NODE)
    return tree.nodes.get(STACK_NODE)


def repair_links(mat, force=False):
    """(Re)create the links from the stack (or the baked image) to every input the base-colour
    image used to feed, from the attach record. force=True rewires even if already linked
    (Live <-> Baked switch); otherwise only heals missing links (files saved with 0.1.0)."""
    tree = mat.node_tree
    src_node = source_node(mat)
    if src_node is None:
        return 0
    fixed = 0
    targets = []
    for r in mat.pl_stack.attach.links:
        to = tree.nodes.get(r.to_node)
        dst = next((s for s in to.inputs if s.identifier == r.to_socket), None) if to else None
        targets.append((dst, "Color" if r.from_socket == "Color" else "Alpha"))
    for name in EMITTERS:
        emit = tree.nodes.get(name)
        if emit is not None:
            targets.append((emit.inputs["Color"], "Color"))
    form = tree.nodes.get("PL Form BSDF")
    if form is not None:
        targets.append((form.inputs.get("Base Color") or form.inputs["Color"], "Color"))   # (Diffuse since 0.23)
    for dst, out_name in targets:
        src = src_node.outputs.get(out_name)
        if dst is None or src is None:
            continue
        if force or not (dst.is_linked and dst.links[0].from_node == src_node):
            tree.links.new(src, dst)
            fixed += 1
    return fixed


def detach(mat):
    from .formview import remove_nodes
    from .outline import remove as remove_outline
    from .shadowdata import remove as remove_shadow_data
    remove_shadow_data(mat)
    remove_nodes(mat)
    remove_outline(mat.pl_stack)
    stack = mat.pl_stack
    tree = mat.node_tree
    rec = stack.attach
    base = tree.nodes.get(rec.base_node)
    group = tree.nodes.get(STACK_NODE)
    if base is not None:
        base.parent = None
        base.location = rec.base_location
        for r in rec.links:
            to = tree.nodes.get(r.to_node)
            if to is None:
                continue
            dst = next((s for s in to.inputs if s.identifier == r.to_socket), None)
            src = next((s for s in base.outputs if s.identifier == r.from_socket), None)
            if dst is not None and src is not None:
                tree.links.new(src, dst)
    out = tree.nodes.get(rec.output_node) if rec.output_node else None
    src_node = tree.nodes.get(rec.surface_from_node) if rec.surface_from_node else None
    if out is not None and src_node is not None:
        src = next((s for s in src_node.outputs if s.identifier == rec.surface_from_socket), None)
        if src is not None:
            tree.links.new(src, out.inputs["Surface"])
        out.location = (out.location[0] - 200, out.location[1])
    if stack.hybrid:
        prev = tree.nodes.get(stack.hybrid_prev_output)
        if prev is not None:
            prev.is_active_output = True
        stack.hybrid = False
    stack.mode = "LIVE"
    for name in (SWITCH, SWITCH_ATTR, SWITCH_EMIT, STACK_NODE, FRAME, BAKED_NODE,
                 "PL Hybrid Output", "PL Hybrid Emission"):
        n = tree.nodes.get(name)
        if n is not None:
            tree.nodes.remove(n)
    stack.enabled = False


def _material(context):
    ob = context.object
    return ob.active_material if ob else None


class PL_OT_attach(bpy.types.Operator):
    bl_idname = "pl.attach"
    bl_label = "Attach Layer Stack"
    bl_description = ("Swap this material's base-colour image for a layer stack. "
                      "Only that node's links change; detach restores them")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        mat = _material(context)
        return mat is not None and mat.node_tree is not None and not mat.pl_stack.enabled

    def execute(self, context):
        mat = _material(context)
        try:
            attach(mat, context.scene)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        sc = context.scene
        if sc.pl_key_light is None and any(o.type == 'LIGHT' for o in sc.objects) and not bpy.app.background:
            from .modal_util import chain
            chain(context, "pl.key_light_choose")  # no single sun: ask which light is the key
        self.report({'INFO'}, f"Layer stack attached to '{mat.name}'")
        return {'FINISHED'}


class PL_OT_detach(bpy.types.Operator):
    bl_idname = "pl.detach"
    bl_label = "Detach Layer Stack"
    bl_description = "Restore the original base-colour image node and its links (layers are kept)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        mat = _material(context)
        return mat is not None and mat.pl_stack.enabled

    def execute(self, context):
        detach(_material(context))
        return {'FINISHED'}


DATA_SPACES = ("Non-Color", "Raw", "Generic Data", "Linear Rec.709", "Linear CIE-XYZ E")


def normal_colorspace_wrong(stack):
    """A normal map read as sRGB gets gamma-decoded: bent normals, visible UV seams."""
    n = stack.normal_image
    return n is not None and n.colorspace_settings.name == "sRGB"


class PL_OT_fix_normal_colorspace(bpy.types.Operator):
    bl_idname = "pl.fix_normal_colorspace"
    bl_label = "Set Normal Map to Non-Color"
    bl_description = ("The normal map is read as sRGB colour, which bends the normals and shows UV seams "
                      "(in your own shader too). Set the image to Non-Color (Ctrl+Z undoes it)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        mat = getattr(context.object, "active_material", None) if context.object else None
        return mat is not None and normal_colorspace_wrong(mat.pl_stack)

    def execute(self, context):
        img = context.object.active_material.pl_stack.normal_image
        img.colorspace_settings.name = "Non-Color"
        self.report({'INFO'}, f"{img.name}: sRGB -> Non-Color")
        return {'FINISHED'}


classes = (PL_OT_attach, PL_OT_detach, PL_OT_fix_normal_colorspace)
