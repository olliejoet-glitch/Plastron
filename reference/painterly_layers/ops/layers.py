"""Layer list operators: add, remove, move, duplicate, group/ungroup, select."""
import math

import bpy
from bpy.props import EnumProperty, StringProperty

from ..props import LIGHT_TYPES

from .. import props
from ..compiler import compile_stack, layers as layer_trees


# ----------------------------------------------------------------------------- helpers

def get_stack(context):
    ob = context.object
    mat = ob.active_material if ob else None
    if mat is None or not mat.pl_stack.enabled:
        return None, None
    return mat, mat.pl_stack


def depth(stack, layer):
    d, p = 0, layer.parent_uid
    while p:
        d += 1
        g = stack.by_uid(p)
        p = g.parent_uid if g else ""
    return d


def subtree_uids(stack, layer):
    """uids of a layer and (for groups) all its descendants."""
    out = [layer.uid]
    if layer.layer_type == "GROUP":
        for l in stack.layers:
            if l.parent_uid == layer.uid:
                out += subtree_uids(stack, l)
    return out


def _tree(stack):
    """Nested [(uid, [children...]), ...] bottom->top, from the flat list."""
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


def reorder(stack, uid_order):
    """Reorder the collection to match uid_order (bottom -> top). Keeps the active layer."""
    active_uid = stack.active.uid if stack.active else ""
    with props.suspended():
        for target, uid in enumerate(uid_order):
            cur = next(i for i, l in enumerate(stack.layers) if l.uid == uid)
            if cur != target:
                stack.layers.move(cur, target)
        stack.active_index = next((i for i, l in enumerate(stack.layers) if l.uid == active_uid), 0)


def pinned_group(stack):
    return next((l for l in stack.layers if l.pinned_top and l.layer_type == "GROUP" and not l.parent_uid), None)


def _inside(stack, layer, group_uid):
    p = layer.parent_uid
    while p:
        if p == group_uid:
            return True
        g = stack.by_uid(p)
        p = g.parent_uid if g else ""
    return False


def keep_pinned_on_top(stack):
    """The pinned group (hybrid Lighting) always stays the top of the stack."""
    g = pinned_group(stack)
    if g is None:
        return
    nodes = _tree(stack)
    i = next(k for k, (u, _) in enumerate(nodes) if u == g.uid)
    if i != len(nodes) - 1:
        nodes.append(nodes.pop(i))
        reorder(stack, _flatten(nodes))


def index_of(stack, uid):
    return next((i for i, l in enumerate(stack.layers) if l.uid == uid), -1)


def new_paint_image(name, res):
    """Transparent RGBA image, packed. (A GENERATED image can't be packed until it has real
    pixels, so write them once.)"""
    import numpy as np
    img = bpy.data.images.new(name, res, res, alpha=True)
    img.pixels.foreach_set(np.zeros(res * res * 4, np.float32))
    img.update()
    img["pl_owned"] = True
    img.pack()
    return img


def sync_paint_target(context, mat):
    """Point Texture Paint at the active layer's image (Single Image mode -> deterministic)."""
    stack = mat.pl_stack
    layer = stack.active
    if layer is None or context is None or context.scene is None:
        return
    img = layer.paint_image if layer.layer_type == "PAINT" else None
    m = layer.active_mask
    if layer.paint_target == "MASK" and m is not None:
        img = m.correction if m.source == "DEPTH" else m.image  # T: paint the mask itself
    if stack.outline_paint and stack.outline_mask is not None:
        img = stack.outline_mask   # Paint Outline (§48) wins until it's switched off
    ip = context.scene.tool_settings.image_paint
    ip.mode = 'IMAGE'
    # nothing paintable selected (fill, adjustment, light layer): paint NOTHING rather than let
    # Blender fall back to some image in the material (it picked the normal map)
    ip.canvas = img


# NOTE: never hold a PL_Layer reference across layers.add()/remove()/move(): Blender may move
# collection items in memory, so the old reference then points at a different layer.
# Work with uids and re-fetch with stack.by_uid().

def add_layer(mat, layer_type, **kw):
    """Add above the active layer (inside it if it is a group). Returns the new layer."""
    stack = mat.pl_stack
    act = stack.active
    pin = pinned_group(stack)
    is_light = layer_type in LIGHT_TYPES
    if act is not None and pin is not None and (
            _inside(stack, act, pin.uid) or (act.uid == pin.uid and not is_light)):
        # active layer is inside the pinned Lighting group: new layers go right below that group,
        # so the main shadow keeps sitting over every texture / detail layer
        below = min(index_of(stack, u) for u in subtree_uids(stack, pin))
        act = stack.layers[below - 1] if below > 0 else None
        if act is not None and act.parent_uid:  # a child of some other group: climb to its root
            while act.parent_uid:
                act = stack.by_uid(act.parent_uid)
    act_uid = act.uid if act else None
    act_group = act is not None and act.layer_type == "GROUP"
    act_parent = act.parent_uid if act else ""
    insert_bottom = act is None and pin is not None
    with props.suspended():
        layer = stack.layers.add()
        uid = layer.ensure_uid()
        layer.layer_type = layer_type
        for k, v in kw.items():
            setattr(layer, k, v)
        if act_uid is None:
            parent, target = "", (0 if insert_bottom else len(stack.layers) - 1)
        elif act_group:
            parent, target = act_uid, index_of(stack, act_uid)  # top of the group's children
        else:
            parent, target = act_parent, index_of(stack, act_uid) + 1
        layer.parent_uid = parent
        stack.layers.move(len(stack.layers) - 1, target)
        stack.active_index = target
        layer = stack.by_uid(uid)
        if layer_type == "PAINT" and layer.paint_image is None:
            layer.paint_image = new_paint_image(f"{mat.name} · {layer.name}", stack.resolution)
    keep_pinned_on_top(stack)
    stack.active_index = index_of(stack, uid)
    compile_stack(mat)
    sync_paint_target(bpy.context, mat)
    return stack.by_uid(uid)


def remove_layer(mat, layer):
    stack = mat.pl_stack
    uids = subtree_uids(stack, layer)
    with props.suspended():
        for uid in uids:
            i = index_of(stack, uid)
            tree = stack.layers[i].node_tree
            stack.layers.remove(i)
            if tree is not None:
                from ..compiler import retire
                retire(tree)   # (deleted once no material preview is rendering, §55)
        stack.active_index = min(stack.active_index, max(len(stack.layers) - 1, 0))
    compile_stack(mat)


def copy_layer_props(src, dst):
    for p in src.bl_rna.properties:
        k = p.identifier
        if k in ("rna_type", "uid", "node_tree", "light_size") or p.is_readonly:  # (size = derived)
            continue
        setattr(dst, k, getattr(src, k))


def duplicate_layer(mat, layer):
    stack = mat.pl_stack
    root_uid, root_name = layer.uid, layer.name
    order = _flatten(_tree(stack))
    uids = subtree_uids(stack, layer)
    mapping = {}
    with props.suspended():
        for uid in uids:
            new = stack.layers.add()
            src = stack.by_uid(uid)  # fetch after add()
            copy_layer_props(src, new)
            new.uid = ""
            new_uid = new.ensure_uid()
            mapping[uid] = new_uid
            if src.node_tree is not None:  # keeps Blend If ramps / curves
                new.node_tree = src.node_tree.copy()
                new.node_tree.name = layer_trees.TREE_PREFIX + new_uid
            if src.layer_type == "PAINT" and src.paint_image is not None:
                img = src.paint_image.copy()
                img["pl_owned"] = True
                new.paint_image = img
        for new_uid in mapping.values():
            new = stack.by_uid(new_uid)
            if new.parent_uid in mapping:
                new.parent_uid = mapping[new.parent_uid]
        stack.by_uid(mapping[root_uid]).name = root_name + " copy"
    # place the copy block right above the original block
    block_new = [mapping[u] for u in order if u in mapping]
    pos = order.index(root_uid) + 1
    reorder(stack, order[:pos] + block_new + order[pos:])
    with props.suspended():
        for new_uid in mapping.values():
            stack.by_uid(new_uid).pinned_top = False  # only one pinned group
    keep_pinned_on_top(stack)
    stack.active_index = index_of(stack, mapping[root_uid])
    compile_stack(mat)
    return stack.by_uid(mapping[root_uid])


def move_layer(mat, layer, direction, compile=True):
    """direction +1 = up (towards top), -1 = down. Crosses group boundaries like Photoshop."""
    stack = mat.pl_stack
    nodes = _tree(stack)

    def find(lst, uid, parent=None):
        for i, (u, kids) in enumerate(lst):
            if u == uid:
                return lst, i, parent
            r = find(kids, uid, (lst, i))
            if r:
                return r
        return None

    lst, i, parent = find(nodes, layer.uid)
    item = lst.pop(i)
    new_parent_uid = layer.parent_uid
    j = i if direction > 0 else i - 1          # neighbour index after the pop
    if 0 <= j < len(lst):
        nb_uid, nb_kids = lst[j]
        nb = stack.by_uid(nb_uid)
        if nb.layer_type == "GROUP" and nb.expanded:
            # enter the group: at its bottom when moving up, at its top when moving down
            nb_kids.insert(0, item) if direction > 0 else nb_kids.append(item)
            new_parent_uid = nb_uid
        else:
            lst.insert(j + 1 if direction > 0 else j, item)
    elif parent is not None:
        # leave the group: just above it (up) or just below it (down)
        plst, pi = parent
        group_uid = plst[pi][0]
        plst.insert(pi + 1 if direction > 0 else pi, item)
        new_parent_uid = stack.by_uid(group_uid).parent_uid
    else:
        return False  # already at the very top / bottom
    with props.suspended():
        layer.parent_uid = new_parent_uid
    reorder(stack, _flatten(nodes))
    keep_pinned_on_top(stack)
    if compile:
        compile_stack(mat)
    return True


def group_layer(mat, layer):
    stack = mat.pl_stack
    uid, parent = layer.uid, layer.parent_uid
    order = _flatten(_tree(stack))          # positions BEFORE reparenting
    block = subtree_uids(stack, layer)
    with props.suspended():
        g = stack.layers.add()
        g_uid = g.ensure_uid()
        g.layer_type = "GROUP"
        g.name = "Group"
        g.parent_uid = parent
        stack.by_uid(uid).parent_uid = g_uid
    order.insert(max(order.index(u) for u in block) + 1, g_uid)  # group sits right above
    reorder(stack, order)
    keep_pinned_on_top(stack)
    stack.active_index = index_of(stack, g_uid)
    compile_stack(mat)
    return stack.by_uid(g_uid)


def ungroup(mat, group):
    stack = mat.pl_stack
    g_uid, g_parent = group.uid, group.parent_uid
    with props.suspended():
        for l in stack.layers:
            if l.parent_uid == g_uid:
                l.parent_uid = g_parent
    remove_layer(mat, stack.by_uid(g_uid))


# ----------------------------------------------------------------------------- operators

class _StackOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None


ADJUST_ITEMS = [("HUE_SAT", "Hue/Saturation", ""), ("LEVELS", "Levels", ""),
                ("BRIGHT_CONTRAST", "Brightness/Contrast", ""), ("CURVES", "Curves", "")]


class PL_OT_layer_add(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_add"
    bl_label = "Add Layer"
    bl_description = "Add a layer above the active one"
    # SKIP_SAVE: Blender otherwise remembers the last call's values, so a plain "Normal Light"
    # after "Normal Shadow" came out as a shadow
    layer_type: EnumProperty(items=props.LAYER_TYPES, default="PAINT", options={'SKIP_SAVE'})
    adjust_kind: EnumProperty(items=ADJUST_ITEMS, default="HUE_SAT", options={'SKIP_SAVE'})
    fill_source: EnumProperty(items=[("COLOR", "Colour", ""), ("IMAGE", "Image", "")], default="COLOR",
                              options={'SKIP_SAVE'})
    preset: EnumProperty(items=[("NONE", "None", ""), ("SHADOW", "Normal Shadow", ""), ("RAMP", "Light Ramp", ""), ("LAMBERT", "Soft Highlight", ""),
                                ("SHEEN", "Reflection Sheen", ""), ("SSS_GLOW", "Subsurface Glow", ""),
                                ("SSS_TRANS", "Translucency", "")],
                         default="NONE", options={'SKIP_SAVE'})

    def execute(self, context):
        mat, stack = get_stack(context)
        names = {"FILL": "Fill", "PAINT": "Paint", "NORMAL_LIGHT": "Normal Light",
                 "SPEC_LIGHT": "Specular Light", "RIM_LIGHT": "Rim Light", "SSS_LIGHT": "Subsurface",
                 "GROUP": "Group"}
        kw = {"name": names.get(self.layer_type, "Layer")}
        if self.layer_type == "ADJUST":
            kw.update(adjust_kind=self.adjust_kind, name=dict((a, b) for a, b, _ in ADJUST_ITEMS)[self.adjust_kind])
        elif self.layer_type == "FILL":
            kw["fill_source"] = self.fill_source
        elif self.layer_type == "NORMAL_LIGHT":
            kw["blend_mode"] = "SCREEN"
        elif self.layer_type == "SPEC_LIGHT":
            kw.update(blend_mode="SCREEN", light_color=(1.0, 1.0, 0.95), light_threshold=0.5,
                      light_softness=0.1)
        elif self.layer_type == "RIM_LIGHT":   # Size 0.3: a band along the silhouette
            kw.update(blend_mode="SCREEN", light_color=(0.75, 0.85, 1.0),
                      light_threshold=1.0 - math.cos(0.7 * math.pi / 2), light_softness=0.08, form_size=0.2)
        elif self.layer_type == "SSS_LIGHT":
            kw.update(blend_mode="SCREEN", light_color=(0.85, 0.22, 0.12), light_threshold=0.35,
                      light_softness=0.35, form_size=0.3)
        if self.preset == "SSS_GLOW":
            kw.update(name="Subsurface Glow", sss_mode="GLOW", include_cast_shadow=True)
        elif self.preset == "SSS_TRANS":
            kw.update(name="Translucency", sss_mode="TRANSLUCENT", light_color=(1.0, 0.45, 0.2),
                      light_threshold=0.5, light_softness=0.5)
        if self.preset == "SHEEN":
            kw.update(name="Reflection Sheen", rim_reflect=True, blend_mode="SOFT_LIGHT", opacity=0.6,
                      light_threshold=1.0 - math.cos(0.35 * math.pi / 2), light_softness=0.2)
        if self.preset == "RAMP":
            kw.update(name="Light Ramp", light_ramp=True, include_cast_shadow=True, blend_mode="NORMAL")
        if self.preset == "LAMBERT":
            kw.update(name="Soft Highlight", light_ramp=True, light_ramp_start="LAMBERT",
                      include_cast_shadow=True, blend_mode="SCREEN", opacity=0.6)
        if self.preset == "SHADOW":
            kw.update(name="Shadow", light_polarity="SHADOW", blend_mode="MULTIPLY", light_threshold=0.0,
                      light_softness=0.05, light_color=(0.35, 0.38, 0.55), form_size=0.3)
        add_layer(mat, self.layer_type, **kw)
        return {'FINISHED'}


class PL_OT_layer_remove(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_remove"
    bl_label = "Delete Layer"
    bl_description = "Delete the selected layers (groups with their contents)"

    def execute(self, context):
        mat, stack = get_stack(context)
        if stack.active is None:
            return {'CANCELLED'}
        from .multiselect import roots, selected_uids
        for uid in roots(stack, selected_uids(stack)):
            if stack.by_uid(uid) is not None:
                remove_layer(mat, stack.by_uid(uid))
        return {'FINISHED'}


class PL_OT_layer_move(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_move"
    bl_label = "Move Layer"
    bl_description = "Move the selected layers up or down (into and out of groups)"
    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    def execute(self, context):
        mat, stack = get_stack(context)
        if stack.active is None:
            return {'CANCELLED'}
        from .multiselect import move_selection
        move_selection(mat, 1 if self.direction == "UP" else -1)
        return {'FINISHED'}


class PL_OT_layer_duplicate(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_duplicate"
    bl_label = "Duplicate Layer"
    bl_description = "Duplicate the active layer (paint images are copied)"

    def execute(self, context):
        mat, stack = get_stack(context)
        if stack.active is None:
            return {'CANCELLED'}
        duplicate_layer(mat, stack.active)
        return {'FINISHED'}


class PL_OT_layer_group(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_group"
    bl_label = "Group Layer"
    bl_description = "Put the selected layers into a new group (Ctrl+G)"

    def execute(self, context):
        mat, stack = get_stack(context)
        if stack.active is None:
            return {'CANCELLED'}
        from .multiselect import group_selection, roots, selected_uids
        if len(roots(stack, selected_uids(stack))) > 1:
            group_selection(mat)
        else:
            group_layer(mat, stack.active)
        return {'FINISHED'}


class PL_OT_layer_ungroup(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_ungroup"
    bl_label = "Ungroup"
    bl_description = "Remove the active group, keeping its layers"

    @classmethod
    def poll(cls, context):
        mat, stack = get_stack(context)
        return stack is not None and stack.active is not None and stack.active.layer_type == "GROUP"

    def execute(self, context):
        mat, stack = get_stack(context)
        ungroup(mat, stack.active)
        return {'FINISHED'}


class PL_OT_layer_toggle_visibility(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_toggle_visibility"
    bl_label = "Toggle Layer Visibility"
    bl_description = "Show / hide the active layer"

    def execute(self, context):
        mat, stack = get_stack(context)
        if stack.active is None:
            return {'CANCELLED'}
        stack.active.visible = not stack.active.visible
        return {'FINISHED'}


class PL_OT_layer_new_image(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_new_image"
    bl_label = "New Image"
    bl_description = "Give the active paint layer a fresh transparent image"

    def execute(self, context):
        mat, stack = get_stack(context)
        layer = stack.active
        if layer is None or layer.layer_type != "PAINT":
            return {'CANCELLED'}
        layer.paint_image = new_paint_image(f"{mat.name} · {layer.name}", stack.resolution)
        sync_paint_target(context, mat)
        return {'FINISHED'}


class PL_OT_layer_colour_reset(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_colour_reset"
    bl_label = "Reset Colour"
    bl_description = "Put Hue / Saturation / Value and Levels of the selected layers back to neutral"

    def execute(self, context):
        mat, stack = get_stack(context)
        from .multiselect import selected_uids
        for uid in selected_uids(stack):
            l = stack.by_uid(uid)
            with props.suspended():
                for k, d in layer_trees.LA_DEFAULTS:
                    setattr(l, k, d)
                l.la_curve = False   # (the curve's points go with its node)
        compile_stack(mat)
        return {'FINISHED'}


classes = (PL_OT_layer_colour_reset, PL_OT_layer_add, PL_OT_layer_remove, PL_OT_layer_move, PL_OT_layer_duplicate,
           PL_OT_layer_group, PL_OT_layer_ungroup, PL_OT_layer_toggle_visibility,
           PL_OT_layer_new_image)
