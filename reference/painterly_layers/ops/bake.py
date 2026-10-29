"""Baked mode (ARCHITECTURE §9): bake the stack to an image with Cycles, swap it in with identical
links, switch back to live in one click, export PNG.

Cycles can't evaluate Shader to RGB, so Cast Shadow masks first bake the direct diffuse light of
a white surface (Cycles DIFFUSE, direct only: same scale as EEVEE's Shader to RGB) that the
bake-variant of the stack samples instead. Highlights use the scene camera's position.
(Cycles' own SHADOW bake returns 1.0 everywhere in 5.2, so it isn't used.)
"""
import math

import bpy
from ..props import LIGHT_TYPES
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, StringProperty
from mathutils import Vector

from ..compiler import compile_stack
from ..compiler import layers as layer_trees
from . import attach as att
from .layers import get_stack

BAKED_NODE = att.BAKED_NODE


def _uses_shadow(st):
    return any(m.source == "SHADOW" for l in st.layers for m in l.masks) or any(
        l.layer_type in LIGHT_TYPES and l.include_cast_shadow and (
            l.light_polarity == "SHADOW" or (l.layer_type == "SSS_LIGHT" and l.sss_mode == "GLOW"))
        for l in st.layers) or any(layer_trees.blocked_light(l) for l in st.layers)


def _new_image(name, res, float_buffer=True):
    img = bpy.data.images.get(name)
    if img is not None and tuple(img.size) != (res, res):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(name, res, res, alpha=False, float_buffer=float_buffer)
    return img


def _bake_into(context, ob, tree, image, bake_type, pass_filter=None):
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.image = image
    prev_active = tree.nodes.active
    tree.nodes.active = tex
    try:
        kw = {"pass_filter": pass_filter} if pass_filter else {}
        bpy.ops.object.bake(type=bake_type, margin=16, use_clear=True, **kw)
    finally:
        tree.nodes.remove(tex)
        tree.nodes.active = prev_active


def bake(context, mat, ob, res=None, direction=None):
    st = mat.pl_stack
    sc = context.scene
    tree = mat.node_tree
    res = res or st.resolution
    if direction is not None and sc.pl_key_light is not None:  # option: set the light first
        light = sc.pl_key_light
        mw = Vector(direction).normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
        mw.translation = light.matrix_world.translation
        light.matrix_world = mw
        context.view_layer.update()
    saved = (sc.render.engine, sc.cycles.samples, ob.mode)
    sel = [o for o in context.view_layer.objects if o.select_get()]
    active = context.view_layer.objects.active
    out_prev = att.active_output(tree)
    tmp_out = tmp_emit = None
    try:
        if ob.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in sel:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        sc.render.engine = 'CYCLES'
        sc.cycles.samples = 16
        if _uses_shadow(st):
            shadow = _new_image(f"PL Light · {mat.name}", res)
            shadow.colorspace_settings.name = "Non-Color"
            white = tree.nodes.new('ShaderNodeBsdfDiffuse')
            white.inputs["Color"].default_value = (1, 1, 1, 1)
            light_out = tree.nodes.new('ShaderNodeOutputMaterial')
            tree.links.new(white.outputs[0], light_out.inputs["Surface"])
            light_out.is_active_output = True
            try:
                _bake_into(context, ob, tree, shadow, 'DIFFUSE', pass_filter={'DIRECT'})
            finally:
                tree.nodes.remove(light_out)
                tree.nodes.remove(white)
                if out_prev is not None:
                    out_prev.is_active_output = True
            from ..imgpack import pack_float
            pack_float(shadow)   # (compressed half-float EXR, §60)
            st.bake_shadow_image = shadow
        st.bake_variant = True  # recompiles: shadow image, camera-based highlights
        tmp_emit = tree.nodes.new('ShaderNodeEmission')
        tmp_out = tree.nodes.new('ShaderNodeOutputMaterial')
        stack_node = next(n for n in tree.nodes if n.type == 'GROUP' and n.node_tree == st.node_tree)
        tree.links.new(stack_node.outputs["Color"], tmp_emit.inputs["Color"])
        tree.links.new(tmp_emit.outputs[0], tmp_out.inputs["Surface"])
        tmp_out.is_active_output = True
        baked = _new_image(f"PL Baked · {mat.name}", res)
        _bake_into(context, ob, tree, baked, 'EMIT')
        from ..imgpack import pack_float
        pack_float(baked)   # (compressed half-float EXR, §60)
        st.baked_image = baked
    finally:
        for n in (tmp_out, tmp_emit):
            if n is not None:
                tree.nodes.remove(n)
        if out_prev is not None:
            out_prev.is_active_output = True
        st.bake_variant = False
        sc.render.engine, sc.cycles.samples = saved[0], saved[1]
        ob.select_set(False)
        for o in sel:
            o.select_set(True)
        context.view_layer.objects.active = active
        if saved[2] != 'OBJECT':
            bpy.ops.object.mode_set(mode=saved[2])
    return st.baked_image


def set_mode(mat, mode):
    """Swap the stack group and the baked image node (same links, recorded at attach)."""
    st = mat.pl_stack
    tree = mat.node_tree
    if mode == "BAKED":
        if st.baked_image is None:
            raise RuntimeError("bake first")
        node = tree.nodes.get(BAKED_NODE)
        if node is None:
            node = tree.nodes.new('ShaderNodeTexImage')
            node.name = node.label = BAKED_NODE
            g = tree.nodes.get(att.STACK_NODE)
            node.location = (g.location[0], g.location[1] + 300) if g else (0, 0)
        node.image = st.baked_image
        st.mode = "BAKED"
    else:
        st.mode = "LIVE"
    att.repair_links(mat, force=True)


def export_png(image, path, sixteen=True):
    """Write the baked image as PNG in display (sRGB) values, no view transform."""
    sc = bpy.context.scene
    s = sc.render.image_settings
    saved = (s.file_format, s.color_depth, s.color_mode, getattr(s, "color_management", None),
             getattr(s, "media_type", None))
    try:
        if hasattr(s, "media_type"):
            s.media_type = 'IMAGE'  # scenes set up for video output only list FFMPEG otherwise
        s.file_format = 'PNG'
        s.color_mode = 'RGB'
        s.color_depth = '16' if sixteen else '8'
        if hasattr(s, "color_management"):
            s.color_management = 'OVERRIDE'
            s.view_settings.view_transform = 'Standard'
            s.view_settings.look = 'None'
            s.view_settings.exposure = 0.0
            s.view_settings.gamma = 1.0
        image.save_render(bpy.path.abspath(path), scene=sc)
    finally:
        if saved[4] is not None:
            s.media_type = saved[4]
        s.file_format, s.color_depth, s.color_mode = saved[0], saved[1], saved[2]
        if saved[3] is not None:
            s.color_management = saved[3]


class PL_OT_bake(bpy.types.Operator):
    bl_idname = "pl.bake"
    bl_label = "Bake Layers"
    bl_description = ("Bake the layer stack to an image at the current light direction (Cycles; "
                      "can take a while). Switch Live / Baked afterwards")
    bl_options = {'REGISTER', 'UNDO'}
    set_direction: BoolProperty(name="Set Light Direction First", default=False)
    direction: FloatVectorProperty(name="Direction", subtype='DIRECTION', size=3, default=(0.4, -0.5, 0.75))
    switch: BoolProperty(name="Switch to Baked", default=True)

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None and context.object is not None

    def invoke(self, context, event):
        light = context.scene.pl_key_light
        if light is not None:
            self.direction = light.matrix_world.to_quaternion() @ Vector((0, 0, 1))
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "set_direction")
        if self.set_direction:
            lay.prop(self, "direction", text="")
        lay.prop(self, "switch")

    def execute(self, context):
        mat, st = get_stack(context)
        if st.mode == "BAKED":
            set_mode(mat, "LIVE")
        bake(context, mat, context.object, direction=self.direction if self.set_direction else None)
        if self.switch:
            set_mode(mat, "BAKED")
        self.report({'INFO'}, f"Baked to '{st.baked_image.name}'")
        return {'FINISHED'}


class PL_OT_bake_mode(bpy.types.Operator):
    bl_idname = "pl.bake_mode"
    bl_label = "Live / Baked"
    bl_description = "Switch between the live layers and the baked image (same links)"
    bl_options = {'REGISTER', 'UNDO'}
    mode: EnumProperty(items=[("LIVE", "Live", ""), ("BAKED", "Baked", "")])

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None

    def execute(self, context):
        mat, st = get_stack(context)
        try:
            set_mode(mat, self.mode)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


class PL_OT_export_png(bpy.types.Operator):
    bl_idname = "pl.export_png"
    bl_label = "Export PNG"
    bl_description = "Save the baked base colour as a PNG"
    filepath: StringProperty(subtype='FILE_PATH')
    sixteen: BoolProperty(name="16 bit", default=True)
    filter_glob: StringProperty(default="*.png", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        st = get_stack(context)[1]
        return st is not None and st.baked_image is not None

    def invoke(self, context, event):
        mat, st = get_stack(context)
        self.filepath = bpy.path.ensure_ext(f"//{bpy.path.clean_name(mat.name)}_basecolor", ".png")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        mat, st = get_stack(context)
        export_png(st.baked_image, self.filepath, self.sixteen)
        self.report({'INFO'}, f"Saved {self.filepath}")
        return {'FINISHED'}


classes = (PL_OT_bake, PL_OT_bake_mode, PL_OT_export_png)
