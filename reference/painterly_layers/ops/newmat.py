"""'New CaraPainter Material' (§41): a ready-to-paint material in one click, no shader editor.

The material is just: a base-texture image node -> emission -> output (which attach() turns
into the layer stack + view switch), then hybrid lighting adds the pinned Lighting group and its
own output. Import Base Texture / Import Normal Map fill it from the panel. The object's previous
material stays in the file (the new one goes into the active slot).
"""

import bpy
import numpy as np
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

from . import attach as att
from . import hybrid as hy

BASE_NODE = "PL Base Texture"


def _placeholder(name):
    img = bpy.data.images.new(name, 8, 8, alpha=False)
    img.pixels.foreach_set(np.full(8 * 8 * 4, 0.5, np.float32))
    img.update()
    img.pack()
    img["pl_owned"] = True
    return img


def new_material(context, ob):
    mat = bpy.data.materials.new(f"CaraPainter · {ob.name}")
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new('ShaderNodeOutputMaterial')
    out.location = (600, 0)
    base = tree.nodes.new('ShaderNodeTexImage')
    base.name = base.label = BASE_NODE
    base.image = _placeholder(f"CaraPainter Base · {ob.name}")
    base.location = (-300, 0)
    emit = tree.nodes.new('ShaderNodeEmission')
    emit.location = (200, 0)
    tree.links.new(base.outputs["Color"], emit.inputs["Color"])
    tree.links.new(emit.outputs[0], out.inputs["Surface"])
    if len(ob.material_slots) == 0:
        ob.data.materials.append(mat)
    else:
        ob.material_slots[ob.active_material_index].material = mat
    att.attach(mat, context.scene, base_node=base)
    st = mat.pl_stack
    st.layers[0].name = "Base"
    hy.enable(mat)
    for area in context.screen.areas if context.screen else ():
        if area.type == 'VIEW_3D':
            sh = area.spaces.active.shading
            if sh.type == 'SOLID':
                sh.type = 'MATERIAL'
            sh.use_scene_lights = sh.use_scene_world = True
    return mat


def _load(path, non_color=False):
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    if img.packed_file is None:
        img.pack()          # SheepIt renders without your texture folders
    return img


def base_layer(st):
    return st.layers[0] if len(st.layers) else None


class PL_OT_new_material(bpy.types.Operator):
    bl_idname = "pl.new_material"
    bl_label = "New CaraPainter Material"
    bl_description = ("Give the selected object a new, ready-to-paint CaraPainter material (layer stack + "
                      "painterly lighting). Then import its base texture and normal map from the panel. "
                      "Its previous material stays in the file")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH'

    def execute(self, context):
        mat = new_material(context, context.active_object)
        self.report({'INFO'}, f"{mat.name}: now import the base texture and normal map")
        return {'FINISHED'}


class PL_OT_import_base(bpy.types.Operator, ImportHelper):
    bl_idname = "pl.import_base"
    bl_label = "Import Base Texture"
    bl_description = "Load the base colour texture (packed into the file)"
    bl_options = {'REGISTER', 'UNDO'}
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.exr;*.webp;*.bmp",
                                options={'HIDDEN'})

    def execute(self, context):
        from .layers import get_stack
        mat, st = get_stack(context)
        layer = base_layer(st)
        if layer is None:
            return {'CANCELLED'}
        img = _load(self.filepath)
        layer.fill_source = "IMAGE"
        layer.fill_image = img
        layer.name = f"Base ({img.name})"
        node = mat.node_tree.nodes.get(st.attach.base_node)
        if node is not None and node.type == 'TEX_IMAGE':
            node.image = img          # the shader's own base image (used if the stack is detached)
        self.report({'INFO'}, f"Base texture: {img.name} ({img.size[0]} x {img.size[1]})")
        return {'FINISHED'}


class PL_OT_import_normal(bpy.types.Operator, ImportHelper):
    bl_idname = "pl.import_normal"
    bl_label = "Import Normal Map"
    bl_description = ("Load the normal map (set to Non-Color, packed). Light layers, masks and the Form View "
                      "use it; its height / curvature analysis runs in the background")
    bl_options = {'REGISTER', 'UNDO'}
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.exr;*.webp;*.bmp",
                                options={'HIDDEN'})

    def execute(self, context):
        from ..analysis import cache
        from ..compiler import compile_stack
        from .layers import get_stack
        mat, st = get_stack(context)
        img = _load(self.filepath, non_color=True)
        st.normal_image = img
        compile_stack(mat)
        if not bpy.app.background:
            cache.start(mat)
        self.report({'INFO'}, f"Normal map: {img.name} (analysing in the background)")
        return {'FINISHED'}


def draw_textures(layout, st):
    box = layout.box()
    layer = base_layer(st)
    row = box.row(align=True)
    img = layer.fill_image if layer is not None and layer.fill_source == "IMAGE" else None
    row.label(text=f"Base: {img.name if img and not img.get('pl_owned') else 'none yet'}", icon='TEXTURE')
    row.operator("pl.import_base", text="Import…", icon='IMPORT')
    row = box.row(align=True)
    n = st.normal_image
    row.label(text=f"Normal: {n.name if n else 'none yet'}", icon='NORMALS_FACE')
    row.operator("pl.import_normal", text="Import…", icon='IMPORT')


classes = (PL_OT_new_material, PL_OT_import_base, PL_OT_import_normal)
