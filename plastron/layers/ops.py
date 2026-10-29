"""Layer stack operators. They act on the material on the canvas
(paint_target.active_material())."""

import bpy
from bpy.props import EnumProperty

from . import paint_target, props, stack


def current():
    mat = paint_target.active_material()
    return mat if mat is not None and mat.plastron_stack.enabled else None


class _StackOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return current() is not None


class _ActiveOp(_StackOp):
    @classmethod
    def poll(cls, context):
        mat = current()
        return mat is not None and mat.plastron_stack.active is not None


NAMES = {"FILL": "Fill", "PAINT": "Layer", "GROUP": "Group"}


class PLASTRON_OT_layer_add(_StackOp, bpy.types.Operator):
    """Add a layer above the active one"""
    bl_idname = "plastron.layer_add"
    bl_label = "Add Layer"
    layer_type: EnumProperty(items=props.LAYER_TYPES, default="PAINT", options={'SKIP_SAVE'})
    fill_source: EnumProperty(items=[("COLOR", "Colour", ""), ("IMAGE", "Image", "")],
                              default="COLOR", options={'SKIP_SAVE'})
    adjust_kind: EnumProperty(items=props.ADJUST_KINDS, default="HUE_SAT", options={'SKIP_SAVE'})

    def execute(self, context):
        mat = current()
        kw = {"name": NAMES.get(self.layer_type, "Layer")}
        if self.layer_type == "PAINT":
            n = sum(1 for l in mat.plastron_stack.layers if l.layer_type == "PAINT") + 1
            kw["name"] = f"Layer {n}"
        elif self.layer_type == "ADJUST":
            kw.update(adjust_kind=self.adjust_kind,
                      name=dict((a, b) for a, b, _ in props.ADJUST_KINDS)[self.adjust_kind])
        elif self.layer_type == "FILL":
            kw["fill_source"] = self.fill_source
        stack.add_layer(mat, self.layer_type, **kw)
        return {'FINISHED'}


class PLASTRON_OT_layer_remove(_ActiveOp, bpy.types.Operator):
    """Delete the active layer (a group with its contents)"""
    bl_idname = "plastron.layer_remove"
    bl_label = "Delete Layer"

    def execute(self, context):
        mat = current()
        stack.remove_layer(mat, mat.plastron_stack.active.uid)
        return {'FINISHED'}


class PLASTRON_OT_layer_move(_ActiveOp, bpy.types.Operator):
    """Move the active layer up or down (into and out of groups)"""
    bl_idname = "plastron.layer_move"
    bl_label = "Move Layer"
    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    def execute(self, context):
        mat = current()
        moved = stack.move_layer(mat, mat.plastron_stack.active.uid, 1 if self.direction == "UP" else -1)
        return {'FINISHED'} if moved else {'CANCELLED'}


class PLASTRON_OT_layer_duplicate(_ActiveOp, bpy.types.Operator):
    """Duplicate the active layer (its pixels are copied)"""
    bl_idname = "plastron.layer_duplicate"
    bl_label = "Duplicate Layer"

    def execute(self, context):
        mat = current()
        stack.duplicate_layer(mat, mat.plastron_stack.active.uid)
        return {'FINISHED'}


class PLASTRON_OT_layer_group(_ActiveOp, bpy.types.Operator):
    """Put the active layer into a new group"""
    bl_idname = "plastron.layer_group"
    bl_label = "Group Layer"

    def execute(self, context):
        mat = current()
        stack.group_layer(mat, mat.plastron_stack.active.uid)
        return {'FINISHED'}


class PLASTRON_OT_layer_ungroup(_ActiveOp, bpy.types.Operator):
    """Remove the active group, keeping its layers"""
    bl_idname = "plastron.layer_ungroup"
    bl_label = "Ungroup"

    @classmethod
    def poll(cls, context):
        mat = current()
        return mat is not None and mat.plastron_stack.active is not None and \
            mat.plastron_stack.active.layer_type == "GROUP"

    def execute(self, context):
        mat = current()
        stack.ungroup(mat, mat.plastron_stack.active.uid)
        return {'FINISHED'}


class PLASTRON_OT_mask_add(_ActiveOp, bpy.types.Operator):
    """Add a mask to the active layer"""
    bl_idname = "plastron.mask_add"
    bl_label = "Add Mask"
    source: EnumProperty(items=props.MASK_SOURCES, default="PAINT", options={'SKIP_SAVE'})

    def execute(self, context):
        mat = current()
        stack.add_mask(mat, mat.plastron_stack.active.uid, self.source)
        return {'FINISHED'}


class PLASTRON_OT_mask_remove(_ActiveOp, bpy.types.Operator):
    """Delete the active mask"""
    bl_idname = "plastron.mask_remove"
    bl_label = "Delete Mask"

    def execute(self, context):
        mat = current()
        stack.remove_mask(mat, mat.plastron_stack.active.uid)
        return {'FINISHED'}


class PLASTRON_MT_layer_add(bpy.types.Menu):
    bl_label = "Add Layer"

    def draw(self, context):
        lay = self.layout
        lay.operator("plastron.layer_add", text="Paint Layer", icon='BRUSH_DATA').layer_type = "PAINT"
        op = lay.operator("plastron.layer_add", text="Fill: Colour", icon='COLOR')
        op.layer_type, op.fill_source = "FILL", "COLOR"
        op = lay.operator("plastron.layer_add", text="Fill: Image", icon='IMAGE_DATA')
        op.layer_type, op.fill_source = "FILL", "IMAGE"
        lay.separator()
        for kind, label, _d in props.ADJUST_KINDS:
            op = lay.operator("plastron.layer_add", text=label, icon='MODIFIER')
            op.layer_type, op.adjust_kind = "ADJUST", kind
        lay.separator()
        lay.operator("plastron.layer_add", text="Group", icon='FILE_FOLDER').layer_type = "GROUP"


classes = (
    PLASTRON_OT_layer_add, PLASTRON_OT_layer_remove, PLASTRON_OT_layer_move,
    PLASTRON_OT_layer_duplicate, PLASTRON_OT_layer_group, PLASTRON_OT_layer_ungroup,
    PLASTRON_OT_mask_add, PLASTRON_OT_mask_remove, PLASTRON_MT_layer_add,
)
