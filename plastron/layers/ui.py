"""Photoshop-style layers panel (tools area). Adapted from CaraPainter's
ui/panel.py, trimmed to 2D."""

import bpy

from . import layer_trees, props, stack as stack_ops
from .ops import current

TYPE_ICON = {i[0]: i[3] for i in props.LAYER_TYPES}
SHORT = {"NORMAL": "", "MULTIPLY": "Mul", "SCREEN": "Scr", "OVERLAY": "Ovl", "SOFT_LIGHT": "Soft",
         "HARD_LIGHT": "Hard", "DARKEN": "Dark", "LIGHTEN": "Lite", "COLOR_DODGE": "Dodge",
         "COLOR_BURN": "Burn", "LINEAR_DODGE": "Add", "LINEAR_BURN": "LBurn", "LUMINOSITY": "Lum",
         "COLOR": "Col", "HUE": "Hue", "SATURATION": "Sat", "DIFFERENCE": "Diff",
         "EXCLUSION": "Excl", "SUBTRACT": "Sub", "DIVIDE": "Div", "VIVID_LIGHT": "Vivid",
         "LINEAR_LIGHT": "LinL", "PIN_LIGHT": "Pin", "HARD_MIX": "HMix",
         "DARKER_COLOR": "DarkC", "LIGHTER_COLOR": "LiteC"}


class _Tools:
    # Shown in the tools area (Properties' Tool tab draws the "Tool" category).
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"


class PLASTRON_UL_layers(bpy.types.UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        by_uid = {l.uid: l for l in items}
        flags = []
        for l in items:
            show, p = True, l.parent_uid
            while p and p in by_uid:
                if not by_uid[p].expanded:
                    show = False
                    break
                p = by_uid[p].parent_uid
            flags.append(self.bitflag_filter_item if show else 0)
        n = len(items)
        return flags, [n - 1 - i for i in range(n)]   # top of the stack drawn first

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        d = stack_ops.depth(data, item)
        if d:
            row.separator(factor=1.6 * d)
        row.prop(item, "visible", text="", emboss=False, icon='HIDE_OFF' if item.visible else 'HIDE_ON')
        if item.layer_type == "GROUP":
            row.prop(item, "expanded", text="", emboss=False,
                     icon='DISCLOSURE_TRI_DOWN' if item.expanded else 'DISCLOSURE_TRI_RIGHT')
        img = item.paint_image if item.layer_type == "PAINT" else (
            item.fill_image if item.layer_type == "FILL" and item.fill_source == "IMAGE" else None)
        if img is not None:
            row.label(text="", icon_value=layout.icon(img))
        elif item.layer_type == "FILL" and item.fill_source == "COLOR":
            sub = row.row()
            sub.scale_x = 0.35
            sub.prop(item, "fill_color", text="")
        else:
            row.label(text="", icon=TYPE_ICON[item.layer_type])
        row.prop(item, "name", text="", emboss=False)
        if len(item.masks):
            row.label(text="", icon='MOD_MASK')
        info = SHORT.get(item.blend_mode, "") if item.layer_type != "GROUP" or item.group_mode == "ISOLATED" else ""
        if item.opacity < 0.999:
            info = (info + " " if info else "") + f"{item.opacity * 100:.0f}%"
        if info:
            r = row.row()
            r.alignment = 'RIGHT'
            r.enabled = False
            r.label(text=info)
        if item.layer_type != "GROUP":
            row.prop(item, "locked", text="", emboss=False, icon='LOCKED' if item.locked else 'UNLOCKED')


class PLASTRON_UL_masks(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        row.prop(item, "visible", text="", emboss=False, icon='HIDE_OFF' if item.visible else 'HIDE_ON')
        if item.image is not None:
            row.label(text="", icon_value=layout.icon(item.image))
        row.prop(item, "name", text="", emboss=False)
        if index > 0 and item.op != "MULTIPLY":
            sub = row.row()
            sub.enabled = False
            sub.label(text=item.op.title())


class PLASTRON_PT_layers(_Tools, bpy.types.Panel):
    bl_label = "Layers"
    bl_idname = "PLASTRON_PT_layers"

    @classmethod
    def poll(cls, context):
        return current() is not None

    def draw(self, context):
        lay = self.layout
        st = current().plastron_stack
        act = st.active
        top = lay.row(align=True)
        if act is not None:
            if act.layer_type == "GROUP" and act.group_mode == "PASS_THROUGH":
                top.prop(act, "group_mode", text="")
            else:
                top.prop(act, "blend_mode", text="")
            top.prop(act, "opacity", text="Opacity", slider=True)
        row = lay.row()
        row.template_list("PLASTRON_UL_layers", "", st, "layers", st, "active_index", rows=6)
        col = row.column(align=True)
        col.menu("PLASTRON_MT_layer_add", text="", icon='ADD')
        col.operator("plastron.layer_remove", text="", icon='REMOVE')
        col.separator()
        col.operator("plastron.layer_move", text="", icon='TRIA_UP').direction = "UP"
        col.operator("plastron.layer_move", text="", icon='TRIA_DOWN').direction = "DOWN"
        col.separator()
        col.operator("plastron.layer_duplicate", text="", icon='DUPLICATE')
        col.operator("plastron.layer_group", text="", icon='FILE_FOLDER')


class PLASTRON_PT_layer_props(_Tools, bpy.types.Panel):
    bl_label = "Layer"
    bl_parent_id = "PLASTRON_PT_layers"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        mat = current()
        return mat is not None and mat.plastron_stack.active is not None

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        lay.use_property_decorate = False
        l = current().plastron_stack.active
        t = l.layer_type
        head, body = lay.panel("plastron_layer_colour", default_closed=True)
        head.label(text="Hue / Saturation / Curve" + ("  •" if layer_trees.colour_adjusted(l) else ""))
        if body:
            body.prop(l, "la_hue", slider=True)
            body.prop(l, "la_saturation", slider=True)
            body.prop(l, "la_value", slider=True)
            body.prop(l, "la_curve")
            n = l.node_tree.nodes.get(layer_trees.LA_CURVE) if l.la_curve and l.node_tree else None
            if n is not None:
                body.use_property_split = False
                body.template_curve_mapping(n, "mapping", type='COLOR')
        if t == "FILL":
            lay.prop(l, "fill_source", expand=True)
            if l.fill_source == "COLOR":
                lay.prop(l, "fill_color")
            else:
                lay.template_ID(l, "fill_image", open="image.open")
                lay.prop(l, "tex_scale")
                lay.prop(l, "tex_rotation")
                lay.prop(l, "tex_offset")
                lay.prop(l, "tile_break", slider=True)
                if l.tile_break > 0:
                    lay.prop(l, "tile_break_size")
        elif t == "ADJUST":
            lay.prop(l, "adjust_kind")
            k = l.adjust_kind
            if k == "HUE_SAT":
                for p in ("hs_hue", "hs_saturation", "hs_lightness"):
                    lay.prop(l, p, slider=True)
            elif k == "LEVELS":
                for p in ("lv_in_black", "lv_in_white", "lv_gamma", "lv_out_black", "lv_out_white"):
                    lay.prop(l, p)
            elif k == "BRIGHT_CONTRAST":
                lay.prop(l, "bc_brightness", slider=True)
                lay.prop(l, "bc_contrast", slider=True)
            else:
                n = l.node_tree.nodes.get("ADJ.curves") if l.node_tree else None
                if n is not None:
                    lay.use_property_split = False
                    lay.template_curve_mapping(n, "mapping", type='COLOR')
        elif t == "GROUP":
            lay.prop(l, "group_mode")


class PLASTRON_PT_masks(_Tools, bpy.types.Panel):
    bl_label = "Masks"
    bl_parent_id = "PLASTRON_PT_layers"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        mat = current()
        return mat is not None and mat.plastron_stack.active is not None

    def draw(self, context):
        lay = self.layout
        l = current().plastron_stack.active
        row = lay.row()
        row.template_list("PLASTRON_UL_masks", "", l, "masks", l, "active_mask_index", rows=2)
        col = row.column(align=True)
        op = col.operator("plastron.mask_add", text="", icon='ADD')
        op.source = "PAINT"
        col.operator("plastron.mask_remove", text="", icon='REMOVE')
        m = l.active_mask
        if m is None:
            lay.label(text="Add a mask to hide parts of the layer")
            return
        lay.prop(l, "paint_target", expand=True)
        col = lay.column()
        col.use_property_split = True
        col.prop(m, "source")
        if m.source == "IMAGE":
            col.template_ID(m, "image", open="image.open")
            col.prop(m, "threshold", slider=True)
            col.prop(m, "softness", slider=True)
        col.prop(m, "op")
        col.prop(m, "opacity", slider=True)
        col.prop(m, "invert")


class PLASTRON_PT_blend_if(_Tools, bpy.types.Panel):
    bl_label = "Blend If"
    bl_parent_id = "PLASTRON_PT_layers"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        mat = current()
        act = mat.plastron_stack.active if mat else None
        return act is not None and act.layer_type != "GROUP"

    def draw_header(self, context):
        self.layout.prop(current().plastron_stack.active, "blend_if", text="")

    def draw(self, context):
        lay = self.layout
        l = current().plastron_stack.active
        lay.enabled = l.blend_if
        lay.prop(l, "blend_if_channel", expand=True)
        for which, label in (("this", "This Layer"), ("under", "Underlying Layer")):
            n = l.node_tree.nodes.get(f"BI.{which}.{l.blend_if_channel}") if l.node_tree else None
            if n is not None:
                lay.label(text=label)
                lay.template_color_ramp(n, "color_ramp")


classes = (PLASTRON_UL_layers, PLASTRON_UL_masks, PLASTRON_PT_layers, PLASTRON_PT_layer_props,
           PLASTRON_PT_masks, PLASTRON_PT_blend_if)
