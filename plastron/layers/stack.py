"""Editing a layer stack: add, remove, move, duplicate, group, copy.

NOTE: never hold a layer reference across layers.add()/remove()/move():
Blender may move collection items in memory. Work with uids and re-fetch
with stack.by_uid(). (From CaraPainter's ops/layers.py.)
"""

import bpy
import numpy as np

from . import events, paint_target, props
from .compiler import compile_stack, retire


def new_image(name, width, height, grey=False):
    """Transparent (or black, for masks) RGBA image, packed into the project."""
    img = bpy.data.images.new(name, width, height, alpha=True)
    px = np.zeros(width * height * 4, np.float32)
    if grey:
        px[3::4] = 1.0
    img.pixels.foreach_set(px)
    img.update()
    img["plastron_owned"] = True
    img.pack()
    return img


def init(mat, width, height, first_layer="Sketch"):
    """Turn a material into an empty layer stack with one paint layer."""
    st = mat.plastron_stack
    with props.suspended():
        st.enabled = True
        st.width, st.height = width, height
    if first_layer:
        add_layer(mat, "PAINT", name=first_layer)
    else:
        compile_stack(mat)


def subtree_uids(stack, layer):
    out = [layer.uid]
    if layer.layer_type == "GROUP":
        for l in stack.layers:
            if l.parent_uid == layer.uid:
                out += subtree_uids(stack, l)
    return out


def depth(stack, layer):
    d, p = 0, layer.parent_uid
    while p:
        d += 1
        g = stack.by_uid(p)
        p = g.parent_uid if g else ""
    return d


def _tree(stack):
    def build(parent):
        return [(l.uid, build(l.uid) if l.layer_type == "GROUP" else [])
                for l in stack.layers if l.parent_uid == parent]
    return build("")


def _flatten(nodes):
    out = []
    for uid, kids in nodes:
        out += _flatten(kids)
        out.append(uid)
    return out


def index_of(stack, uid):
    return next((i for i, l in enumerate(stack.layers) if l.uid == uid), -1)


def reorder(stack, uid_order):
    active_uid = stack.active.uid if stack.active else ""
    with props.suspended():
        for target, uid in enumerate(uid_order):
            cur = index_of(stack, uid)
            if cur != target:
                stack.layers.move(cur, target)
        stack.active_index = max(index_of(stack, active_uid), 0)


def _done(mat, uid=None):
    stack = mat.plastron_stack
    if uid is not None:
        with props.suspended():
            stack.active_index = index_of(stack, uid)
    compile_stack(mat)
    paint_target.sync(mat)
    events.changed(mat)


def add_layer(mat, layer_type, **kw):
    """Add above the active layer (inside it if it's a group). Returns the uid."""
    stack = mat.plastron_stack
    act = stack.active
    act_uid = act.uid if act else None
    act_group = act is not None and act.layer_type == "GROUP"
    act_parent = act.parent_uid if act else ""
    with props.suspended():
        layer = stack.layers.add()
        uid = layer.ensure_uid()
        layer.layer_type = layer_type
        for k, v in kw.items():
            setattr(layer, k, v)
        if act_uid is None:
            parent, target = "", len(stack.layers) - 1
        elif act_group:
            parent, target = act_uid, index_of(stack, act_uid)
        else:
            parent, target = act_parent, index_of(stack, act_uid) + 1
        layer.parent_uid = parent
        stack.layers.move(len(stack.layers) - 1, target)
        layer = stack.by_uid(uid)
        if layer_type == "PAINT" and layer.paint_image is None:
            layer.paint_image = new_image(f"{mat.name} · {layer.name}", stack.width, stack.height)
    _done(mat, uid)
    return uid


def remove_layer(mat, uid):
    stack = mat.plastron_stack
    with props.suspended():
        for u in subtree_uids(stack, stack.by_uid(uid)):
            i = index_of(stack, u)
            tree = stack.layers[i].node_tree
            stack.layers.remove(i)
            if tree is not None:
                retire(tree)
        stack.active_index = min(stack.active_index, max(len(stack.layers) - 1, 0))
    _done(mat)


def _copy_layer_props(src, dst):
    for p in src.bl_rna.properties:
        k = p.identifier
        if k in ("rna_type", "uid", "node_tree_name", "masks") or p.is_readonly:
            continue
        setattr(dst, k, getattr(src, k))
    for m in src.masks:
        nm = dst.masks.add()
        for p in m.bl_rna.properties:
            if p.identifier not in ("rna_type",) and not p.is_readonly:
                setattr(nm, p.identifier, getattr(m, p.identifier))
        nm.uid = ""
        nm.ensure_uid()


def _copy_images(layer):
    """Give a copied layer its own copies of the images it paints into."""
    if layer.paint_image is not None and layer.paint_image.get("plastron_owned"):
        img = layer.paint_image.copy()
        img["plastron_owned"] = True
        layer.paint_image = img
    for m in layer.masks:
        if m.image is not None and m.image.get("plastron_owned"):
            img = m.image.copy()
            img["plastron_owned"] = True
            m.image = img


def duplicate_layer(mat, uid):
    stack = mat.plastron_stack
    order = _flatten(_tree(stack))
    uids = subtree_uids(stack, stack.by_uid(uid))
    root_name = stack.by_uid(uid).name
    mapping = {}
    with props.suspended():
        for u in uids:
            new = stack.layers.add()
            src = stack.by_uid(u)
            _copy_layer_props(src, new)
            new.uid = ""
            mapping[u] = new.ensure_uid()
            _copy_images(new)
        for new_uid in mapping.values():
            new = stack.by_uid(new_uid)
            if new.parent_uid in mapping:
                new.parent_uid = mapping[new.parent_uid]
        stack.by_uid(mapping[uid]).name = root_name + " copy"
    block_new = [mapping[u] for u in order if u in mapping]
    pos = order.index(uid) + 1
    reorder(stack, order[:pos] + block_new + order[pos:])
    _done(mat, mapping[uid])
    return mapping[uid]


def move_layer(mat, uid, direction):
    """direction +1 = up (towards top), -1 = down. Crosses group boundaries like Photoshop."""
    stack = mat.plastron_stack
    layer = stack.by_uid(uid)
    nodes = _tree(stack)

    def find(lst, uid, parent=None):
        for i, (u, kids) in enumerate(lst):
            if u == uid:
                return lst, i, parent
            r = find(kids, uid, (lst, i))
            if r:
                return r
        return None

    lst, i, parent = find(nodes, uid)
    item = lst.pop(i)
    new_parent_uid = layer.parent_uid
    j = i if direction > 0 else i - 1
    if 0 <= j < len(lst):
        nb_uid, nb_kids = lst[j]
        nb = stack.by_uid(nb_uid)
        if nb.layer_type == "GROUP" and nb.expanded:
            nb_kids.insert(0, item) if direction > 0 else nb_kids.append(item)
            new_parent_uid = nb_uid
        else:
            lst.insert(j + 1 if direction > 0 else j, item)
    elif parent is not None:
        plst, pi = parent
        group_uid = plst[pi][0]
        plst.insert(pi + 1 if direction > 0 else pi, item)
        new_parent_uid = stack.by_uid(group_uid).parent_uid
    else:
        return False
    with props.suspended():
        stack.by_uid(uid).parent_uid = new_parent_uid
    reorder(stack, _flatten(nodes))
    _done(mat, uid)
    return True


def group_layer(mat, uid):
    stack = mat.plastron_stack
    parent = stack.by_uid(uid).parent_uid
    order = _flatten(_tree(stack))
    block = subtree_uids(stack, stack.by_uid(uid))
    with props.suspended():
        g = stack.layers.add()
        g_uid = g.ensure_uid()
        g.layer_type = "GROUP"
        g.name = "Group"
        g.parent_uid = parent
        stack.by_uid(uid).parent_uid = g_uid
    order.insert(max(order.index(u) for u in block) + 1, g_uid)
    reorder(stack, order)
    _done(mat, g_uid)
    return g_uid


def ungroup(mat, uid):
    stack = mat.plastron_stack
    group = stack.by_uid(uid)
    with props.suspended():
        for l in stack.layers:
            if l.parent_uid == uid:
                l.parent_uid = group.parent_uid
    remove_layer(mat, uid)


def add_mask(mat, uid, source="PAINT"):
    stack = mat.plastron_stack
    layer = stack.by_uid(uid)
    with props.suspended():
        m = layer.masks.add()
        m.ensure_uid()
        m.source = source
        m.name = "Mask"
        if source == "PAINT":
            img = new_image(f"{mat.name} · {layer.name} mask", stack.width, stack.height)
            px = np.ones(stack.width * stack.height * 4, np.float32)   # white: shows everything
            img.pixels.foreach_set(px)
            img.update()
            img.pack()
            m.image = img
        layer.active_mask_index = len(layer.masks) - 1
    _done(mat)


def remove_mask(mat, uid):
    layer = mat.plastron_stack.by_uid(uid)
    if layer.active_mask is None:
        return
    with props.suspended():
        layer.masks.remove(layer.active_mask_index)
        layer.active_mask_index = max(0, layer.active_mask_index - 1)
        if not layer.masks:
            layer.paint_target = "LAYER"
    _done(mat)


def copy_material(mat, name):
    """A full copy of a layer-stack material, with its own images and trees."""
    new = mat.copy()
    new.name = name
    st = new.plastron_stack
    with props.suspended():
        st.node_tree_name = ""
        for layer in st.layers:
            layer.node_tree_name = ""
            _copy_images(layer)
    compile_stack(new)   # fresh stack + layer trees (names cleared above)
    return new
