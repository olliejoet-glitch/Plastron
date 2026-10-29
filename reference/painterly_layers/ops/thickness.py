"""Thickness map for Subsurface translucency (§36): baked once with Cycles.

An Ambient Occlusion node in Inside mode (only this object) fires rays INTO the surface: in thin
parts they hit the far side within the distance (occluded), in thick parts they don't. So
thinness = 1 - inside AO. Distance = Thickness Range x the model's size. Stored as a packed 8-bit
Non-Color image (2048), sampled by Subsurface layers in Translucency mode.
"""
import time

import bpy
import numpy as np

from . import attach as att
from .bake import _bake_into, _new_image
from .layers import _StackOp, get_stack


def bake_thickness(context, mat, ob, res=None, samples=24):
    st = mat.pl_stack
    sc = context.scene
    res = res or st.resolution
    tree = mat.node_tree
    saved = (sc.render.engine, sc.cycles.samples, ob.mode)
    sel = [o for o in context.view_layer.objects if o.select_get()]
    active = context.view_layer.objects.active
    out_prev = att.active_output(tree)
    nodes = []
    try:
        if ob.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in sel:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        sc.render.engine = 'CYCLES'
        sc.cycles.samples = samples
        ao = tree.nodes.new('ShaderNodeAmbientOcclusion')
        ao.inside = True
        ao.only_local = True
        ao.samples = 16
        ao.inputs["Distance"].default_value = max(st.thickness_range * ob.dimensions.length, 1e-4)
        emit = tree.nodes.new('ShaderNodeEmission')
        out = tree.nodes.new('ShaderNodeOutputMaterial')
        nodes = [ao, emit, out]
        tree.links.new(ao.outputs["AO"], emit.inputs["Color"])
        tree.links.new(emit.outputs[0], out.inputs["Surface"])
        out.is_active_output = True
        raw = _new_image("PL thickness raw", res)
        _bake_into(context, ob, tree, raw, 'EMIT')
        px = np.empty(res * res * 4, np.float32)
        raw.pixels.foreach_get(px)
        bpy.data.images.remove(raw)
    finally:
        for n in nodes:
            tree.nodes.remove(n)
        if out_prev is not None:
            out_prev.is_active_output = True
        sc.render.engine, sc.cycles.samples = saved[0], saved[1]
        ob.select_set(False)
        for o in sel:
            o.select_set(True)
        context.view_layer.objects.active = active
        if saved[2] != 'OBJECT':
            bpy.ops.object.mode_set(mode=saved[2])
    thin = 1.0 - np.clip(px.reshape(res, res, 4)[..., 0], 0.0, 1.0)
    name = f"PL Thickness · {mat.name}"
    old = bpy.data.images.get(name)
    if old is not None:
        old.name = name + " (old)"
    img = bpy.data.images.new(name, res, res, alpha=False)
    img.colorspace_settings.name = "Non-Color"      # before the pixels (else it regenerates)
    rgba = np.ones((res, res, 4), np.float32)
    rgba[..., :3] = thin[..., None]
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    img.pack()
    img["pl_owned"] = True
    st.thickness_image = img
    if old is not None and old.users == 0:
        bpy.data.images.remove(old)
    return img


class PL_OT_bake_thickness(_StackOp, bpy.types.Operator):
    bl_idname = "pl.bake_thickness"
    bl_label = "Bake Thickness"
    bl_description = ("Bake the model's thickness once (Cycles, about a minute) so Subsurface "
                      "Translucency knows which parts are thin enough to glow. Packed in the file")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat, stack = get_stack(context)
        ob = context.active_object
        if ob is None or ob.type != 'MESH':
            self.report({'ERROR'}, "Select the model")
            return {'CANCELLED'}
        t0 = time.time()
        bake_thickness(context, mat, ob)
        self.report({'INFO'}, f"Thickness baked in {time.time() - t0:.0f} s")
        return {'FINISHED'}


classes = (PL_OT_bake_thickness,)
