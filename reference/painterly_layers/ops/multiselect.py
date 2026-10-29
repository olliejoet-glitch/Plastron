"""Photoshop-style layer selection (§33): click / Ctrl+click / Shift+click, drag the selected
layers up and down the stack, delete / group / merge the selection (Ctrl+E).

Blender's list widget has no multi-select (and uses Ctrl+click / double-click on a row for
renaming), so each row's name is a button running pl.layer_click, which reads the modifiers.
Double-click renames.
"""
import time

import bpy
import numpy as np
from bpy.props import BoolProperty, IntProperty, StringProperty

from .. import props
from ..compiler import compile_stack
from .layers import (_StackOp, _flatten, _tree, add_layer, get_stack, index_of, keep_pinned_on_top,
                     move_layer, new_paint_image, remove_layer, reorder, subtree_uids, sync_paint_target)

from ..props import LIGHT_TYPES as LIGHTS


# ----------------------------------------------------------------------------- selection model

def selected_uids(stack):
    """Selected layers (the active one always counts), bottom -> top."""
    act = stack.active
    return [l.uid for l in stack.layers if l.selected or (act is not None and l.uid == act.uid)]


def roots(stack, uids):
    """Selected layers whose ancestors aren't selected (a selected group carries its children)."""
    sel = set(uids)
    out = []
    for uid in uids:
        l = stack.by_uid(uid)
        p, inside = l.parent_uid, False
        while p:
            if p in sel:
                inside = True
                break
            g = stack.by_uid(p)
            p = g.parent_uid if g else ""
        if not inside:
            out.append(uid)
    return out


def set_selection(stack, uids, active_uid):
    with props.suspended():
        keep = set(uids) | {active_uid}
        for l in stack.layers:
            l.selected = l.uid in keep
    props._selecting += 1
    try:
        stack.active_index = index_of(stack, active_uid)   # (not suspended: syncs the paint canvas)
    finally:
        props._selecting -= 1


def display_order(stack):
    """uids top -> bottom as the list shows them (collapsed groups' children excluded)."""
    by = {l.uid: l for l in stack.layers}
    out = []
    for l in reversed(list(stack.layers)):
        p, show = l.parent_uid, True
        while p and p in by:
            if not by[p].expanded:
                show = False
                break
            p = by[p].parent_uid
        if show:
            out.append(l.uid)
    return out


# ----------------------------------------------------------------------------- moving

def move_selection(mat, direction, compile=True):
    """Move every selected root one step (+1 up / -1 down), as a block. False at the edge."""
    stack = mat.pl_stack
    rs = roots(stack, selected_uids(stack))
    order = _flatten(_tree(stack))
    rs.sort(key=lambda u: order.index(u), reverse=direction > 0)   # leading layer first
    if any(stack.by_uid(u).pinned_top for u in rs):
        return False
    moved = False
    for uid in rs:
        if move_layer(mat, stack.by_uid(uid), direction, compile=False):
            moved = True
        else:
            break
    if compile and moved:
        compile_stack(mat)
    return moved


# ----------------------------------------------------------------------------- merging

def mergeable(stack, uids):
    """(ok, reason). Light layers react to the light: merging would freeze it."""
    for uid in uids:
        for u in subtree_uids(stack, stack.by_uid(uid)):
            l = stack.by_uid(u)
            if l.layer_type in LIGHTS:
                return False, f"'{l.name}' is a light layer (it reacts to the light): hide or delete it first"
            if l.pinned_top or l.hybrid_owned:
                return False, "the Lighting group can't be merged"

    return True, ""


def _srgb_encode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def bake_selection(context, mat, ob, uids, res):
    """Composite of just these layers (over transparency) as straight RGBA, sRGB-encoded."""
    from . import attach as att
    from .bake import _bake_into, _new_image
    st = mat.pl_stack
    sc = context.scene
    keep = set()
    for uid in uids:
        keep.update(subtree_uids(st, st.by_uid(uid)))
        p = st.by_uid(uid).parent_uid
        while p:                              # the groups around them stay visible
            keep.add(p)
            p = st.by_uid(p).parent_uid
    vis = {l.uid: l.visible for l in st.layers}
    tree = mat.node_tree
    saved = (sc.render.engine, sc.cycles.samples, ob.mode, sc.get("pl_base_view", 0.0), sc.get("pl_form_view", 0.0))
    sel_objs = [o for o in context.view_layer.objects if o.select_get()]
    active = context.view_layer.objects.active
    out_prev = att.active_output(tree)
    nodes = []
    try:
        with props.suspended():
            for l in st.layers:
                if l.uid not in keep:
                    l.visible = False
        compile_stack(mat)
        sc["pl_base_view"] = sc["pl_form_view"] = 0.0
        if ob.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in sel_objs:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        sc.render.engine = 'CYCLES'
        sc.cycles.samples = 1                 # emission only: no noise
        stack_node = next(n for n in tree.nodes if n.type == 'GROUP' and n.node_tree == st.node_tree)
        emit = tree.nodes.new('ShaderNodeEmission')
        out = tree.nodes.new('ShaderNodeOutputMaterial')
        nodes = [emit, out]
        tree.links.new(emit.outputs[0], out.inputs["Surface"])
        out.is_active_output = True
        result = []
        for sock in ("Color", "Alpha"):
            tree.links.new(stack_node.outputs[sock], emit.inputs["Color"])
            img = _new_image(f"PL merge {sock}", res)
            _bake_into(context, ob, tree, img, 'EMIT')
            px = np.empty(res * res * 4, np.float32)
            img.pixels.foreach_get(px)
            result.append(px.reshape(res, res, 4))
            bpy.data.images.remove(img)
    finally:
        for n in nodes:
            tree.nodes.remove(n)
        if out_prev is not None:
            out_prev.is_active_output = True
        with props.suspended():
            for l in st.layers:
                l.visible = vis.get(l.uid, l.visible)
        sc.render.engine, sc.cycles.samples = saved[0], saved[1]
        sc["pl_base_view"], sc["pl_form_view"] = saved[3], saved[4]
        ob.select_set(False)
        for o in sel_objs:
            o.select_set(True)
        context.view_layer.objects.active = active
        if saved[2] != 'OBJECT':
            bpy.ops.object.mode_set(mode=saved[2])
    col, alpha = result
    rgba = np.empty_like(col)
    rgba[..., :3] = _srgb_encode(col[..., :3])   # stack colour is linear; paint images store sRGB
    rgba[..., 3] = np.clip(alpha[..., 0], 0.0, 1.0)
    return rgba


def merge(context, mat, ob, uids, down=False):
    """Replace the layers with one paint layer holding their composite (over transparency, like
    Photoshop: blend modes that acted on layers outside the merge can't be kept). Returns it."""
    st = mat.pl_stack
    rs = roots(st, uids)
    order = _flatten(_tree(st))
    rs.sort(key=lambda u: order.index(u))
    bottom, top = rs[0], rs[-1]
    name = st.by_uid(bottom if down else top).name   # PS: Merge Down keeps the lower layer's name
    # always the stack resolution (2048): a bigger texture (e.g. the 4096 Base) just drops to it
    rgba = bake_selection(context, mat, ob, rs, st.resolution)
    img = new_paint_image(f"{mat.name} · {name}", st.resolution)
    img.pixels.foreach_set(rgba.ravel().astype(np.float32))
    img.update()
    img.pack()
    st.active_index = index_of(st, bottom)
    parent = st.by_uid(bottom).parent_uid
    new_uid = add_layer(mat, "PAINT", name=name, paint_image=img).uid
    with props.suspended():
        st.by_uid(new_uid).parent_uid = parent
    for uid in rs:
        if st.by_uid(uid) is not None:
            remove_layer(mat, st.by_uid(uid))
    set_selection(st, [new_uid], new_uid)
    compile_stack(mat)
    sync_paint_target(context, mat)
    return st.by_uid(new_uid)


# ----------------------------------------------------------------------------- operators

_last_click = {"uid": "", "t": 0.0}


class PL_OT_layer_click(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_click"
    bl_label = "Select Layer"
    bl_description = "Click: select · Ctrl+click: add / remove · Shift+click: range · double-click: rename"
    bl_options = {'REGISTER', 'UNDO'}
    uid: StringProperty(options={'SKIP_SAVE'})
    extend: BoolProperty(options={'SKIP_SAVE'})
    range: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        now = time.time()
        if (not event.ctrl and not event.shift and _last_click["uid"] == self.uid
                and now - _last_click["t"] < 0.4):
            _last_click["uid"] = ""
            return bpy.ops.pl.layer_rename('INVOKE_DEFAULT', uid=self.uid)
        _last_click.update(uid=self.uid, t=now)
        self.extend, self.range = event.ctrl, event.shift
        return self.execute(context)

    def execute(self, context):
        mat, stack = get_stack(context)
        if stack.by_uid(self.uid) is None:
            return {'CANCELLED'}
        sel = selected_uids(stack)
        act = stack.active.uid if stack.active else self.uid
        if self.range:
            vis = display_order(stack)
            a, b = sorted((vis.index(act) if act in vis else 0, vis.index(self.uid)))
            set_selection(stack, sel + vis[a:b + 1], self.uid)
        elif self.extend:
            if self.uid in sel and len(sel) > 1:
                rest = [u for u in sel if u != self.uid]
                set_selection(stack, rest, act if act != self.uid else rest[-1])
            else:
                set_selection(stack, sel + [self.uid], self.uid)
        else:
            set_selection(stack, [self.uid], self.uid)
        return {'FINISHED'}


class PL_OT_layer_rename(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_rename"
    bl_label = "Rename Layer"
    bl_options = {'REGISTER', 'UNDO'}
    uid: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    name: StringProperty(name="Name", options={'SKIP_SAVE'})

    def invoke(self, context, event):
        mat, stack = get_stack(context)
        self.name = stack.by_uid(self.uid).name
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        mat, stack = get_stack(context)
        l = stack.by_uid(self.uid)
        if l is None:
            return {'CANCELLED'}
        l.name = self.name
        return {'FINISHED'}


class PL_OT_layer_drag(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_drag"
    bl_label = "Drag Layers"
    bl_description = ("Drag the selected layers: click the grip, move the mouse up / down (they move as "
                      "you go, into and out of groups), click to drop. Right-click / Esc cancels")
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    uid: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        mat, stack = get_stack(context)
        if self.uid and self.uid not in selected_uids(stack):
            set_selection(stack, [self.uid], self.uid)
        self.mat_name = mat.name
        self.y0 = event.mouse_y
        self.steps = 0
        self.row_h = 20.0 * context.preferences.system.ui_scale
        self.snapshot = ([l.uid for l in stack.layers], {l.uid: l.parent_uid for l in stack.layers})
        context.window.cursor_modal_set('MOVE_Y')
        context.window_manager.modal_handler_add(self)
        if context.area:
            context.area.header_text_set("Dragging layers: move up / down · click to drop · Esc cancels")
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        context.window.cursor_modal_restore()
        for area in context.screen.areas:
            area.header_text_set(None)
            area.tag_redraw()

    def modal(self, context, event):
        mat = bpy.data.materials[self.mat_name]
        if event.type == 'MOUSEMOVE':
            target = int(round((event.mouse_y - self.y0) / self.row_h))   # up the list = up the stack
            moved = False
            while self.steps != target:
                d = 1 if target > self.steps else -1
                if not move_selection(mat, d, compile=False):
                    self.y0 += (target - self.steps) * self.row_h   # at the edge: re-anchor
                    break
                self.steps += d
                moved = True
            if moved:
                compile_stack(mat)
            for area in context.screen.areas:
                area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'RET', 'SPACE'} and event.value == 'PRESS':
            self._finish(context)
            return {'FINISHED'}
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            st = mat.pl_stack
            order, parents = self.snapshot
            with props.suspended():
                for l in st.layers:
                    l.parent_uid = parents.get(l.uid, l.parent_uid)
            reorder(st, order)
            compile_stack(mat)
            self._finish(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class _Merge:   # shared by the button and the Object Mode hotkey (never subclass a registered op)
    bl_label = "Merge Layers"
    bl_description = ("Ctrl+E: merge the selected layers into one paint layer (one selected: merge down "
                      "into the layer below). Masks, opacity, blend modes and adjustments are applied")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat, stack = get_stack(context)
        ob = context.active_object
        sel = roots(stack, selected_uids(stack))
        down = len(sel) == 1
        if down:                      # Merge Down: with the layer just below (same parent)
            l = stack.by_uid(sel[0])
            sibs = [x.uid for x in stack.layers if x.parent_uid == l.parent_uid]
            i = sibs.index(l.uid)
            if i == 0:
                self.report({'WARNING'}, "Nothing below to merge into")
                return {'CANCELLED'}
            sel = [sibs[i - 1], l.uid]
        ok, why = mergeable(stack, sel)
        if not ok:
            self.report({'WARNING'}, "Can't merge: " + why)
            return {'CANCELLED'}
        new = merge(context, mat, ob, sel, down=down)
        self.report({'INFO'}, f"Merged {len(sel)} layers into '{new.name}'")
        return {'FINISHED'}


class PL_OT_layer_merge(_Merge, _StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_merge"


class _InCaraPainter:
    # hotkey variants: only in the CaraPainter workspace, over a 3D View (viewport or its sidebar)
    @classmethod
    def poll(cls, context):
        from .view import in_painterly
        return (in_painterly(context) and context.area is not None and context.area.type == 'VIEW_3D'
                and get_stack(context)[1] is not None)


class PL_OT_layer_merge_key(_InCaraPainter, _Merge, _StackOp, bpy.types.Operator):
    """Ctrl+E in Object Mode: only in the CaraPainter workspace."""
    bl_idname = "pl.layer_merge_key"


class PL_OT_layer_group_key(_InCaraPainter, _StackOp, bpy.types.Operator):
    """Ctrl+G in Object Mode: only in the CaraPainter workspace (else Blender's own Ctrl+G)."""
    bl_idname = "pl.layer_group_key"
    bl_label = "Group Layers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return bpy.ops.pl.layer_group()


class PL_OT_layer_select_all(_StackOp, bpy.types.Operator):
    bl_idname = "pl.layer_select_all"
    bl_label = "Select All Layers"
    bl_options = {'REGISTER', 'UNDO'}
    deselect: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        mat, stack = get_stack(context)
        act = stack.active.uid if stack.active else ""
        set_selection(stack, [] if self.deselect else [l.uid for l in stack.layers], act)
        return {'FINISHED'}


def group_selection(mat):
    """Ctrl+G with several layers: one new group holding them, where the top one was."""
    from .layers import group_layer
    stack = mat.pl_stack
    rs = roots(stack, selected_uids(stack))
    order = _flatten(_tree(stack))
    rs.sort(key=lambda u: order.index(u))
    g = group_layer(mat, stack.by_uid(rs[-1]))
    g_uid = g.uid
    with props.suspended():
        for uid in rs[:-1]:
            stack.by_uid(uid).parent_uid = g_uid
    order = _flatten(_tree(stack))
    block = [u for u in order if u in set().union(*(subtree_uids(stack, stack.by_uid(r)) for r in rs))]
    # put the whole block (bottom -> top) right below the group, which stays where the top layer was
    gi = order.index(g_uid)
    above = [u for u in order[gi + 1:] if u not in block]
    below = [u for u in order[:gi] if u not in block]
    reorder(stack, below + block + [g_uid] + above)
    keep_pinned_on_top(stack)
    set_selection(stack, [g_uid], g_uid)
    compile_stack(mat)
    return stack.by_uid(g_uid)


classes = (PL_OT_layer_click, PL_OT_layer_rename, PL_OT_layer_drag, PL_OT_layer_merge, PL_OT_layer_merge_key,
           PL_OT_layer_group_key, PL_OT_layer_select_all)
