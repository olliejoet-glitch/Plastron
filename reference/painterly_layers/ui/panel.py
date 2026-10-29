"""Photoshop-style layer panel in the 3D viewport sidebar, tab "CaraPainter"."""
import bpy
from ..props import LIGHT_TYPES

from ..compiler import SAMPLER_BUDGET, material_images
from ..compiler import layers as layer_trees
from ..ops.layers import depth, get_stack
from ..ops.view import base_view_active

from ..props import LAYER_TYPES, MASK_SOURCES

TYPE_ICON = {i[0]: i[3] for i in LAYER_TYPES}


def _type_icon(layer):
    return TYPE_ICON[layer.layer_type]


SHORT = {"NORMAL": "", "MULTIPLY": "Mul", "SCREEN": "Scr", "OVERLAY": "Ovl", "SOFT_LIGHT": "Soft",
         "HARD_LIGHT": "Hard", "DARKEN": "Dark", "LIGHTEN": "Lite", "COLOR_DODGE": "Dodge",
         "COLOR_BURN": "Burn", "LINEAR_DODGE": "Add", "LINEAR_BURN": "LBurn", "LUMINOSITY": "Lum",
         "COLOR": "Col", "HUE": "Hue", "SATURATION": "Sat", "DIFFERENCE": "Diff",
         "EXCLUSION": "Excl", "SUBTRACT": "Sub", "DIVIDE": "Div", "VIVID_LIGHT": "Vivid",
         "LINEAR_LIGHT": "LinL", "PIN_LIGHT": "Pin", "HARD_MIX": "HMix",
         "DARKER_COLOR": "DarkC", "LIGHTER_COLOR": "LiteC"}


def ramp_swatch(layer):
    """The ramp stop that stands for a ramp layer's colour in the layer list: of its most opaque
    stops, the darkest for shadows (Light Ramp, Shadow polarity), the brightest for lights."""
    if layer.layer_type != "NORMAL_LIGHT" and layer.layer_type != "SPEC_LIGHT":
        return None
    name = layer_trees.LIGHT_RAMP if (layer.layer_type == "NORMAL_LIGHT" and layer.light_ramp) else (
        "LIGHT.ramp" if layer.use_ramp else None)
    tree = layer.node_tree if name else None
    node = tree.nodes.get(name) if tree is not None else None
    if node is None:
        return None
    els = list(node.color_ramp.elements)
    top = max(e.color[3] for e in els)
    solid = [e for e in els if e.color[3] >= top - 0.05]

    def lum(e):
        return 0.2126 * e.color[0] + 0.7152 * e.color[1] + 0.0722 * e.color[2]
    shadow = layer.light_polarity == "SHADOW" or (layer.light_ramp and len(solid) > 1)
    return (min if shadow else max)(solid, key=lum)


class PL_UL_layers(bpy.types.UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        n = len(items)
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
        return flags, [n - 1 - i for i in range(n)]  # top of the stack drawn first

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        stack = data
        row = layout.row(align=True)
        d = depth(stack, item)
        if d:
            row.separator(factor=1.6 * d)
        row.prop(item, "visible", text="", emboss=False,
                 icon='HIDE_OFF' if item.visible else 'HIDE_ON')
        if item.pinned_top:
            row.label(text="", icon='PINNED')
        if item.layer_type == "GROUP":
            row.prop(item, "expanded", text="", emboss=False,
                     icon='DISCLOSURE_TRI_DOWN' if item.expanded else 'DISCLOSURE_TRI_RIGHT')
        img = item.paint_image if item.layer_type == "PAINT" else (
            item.fill_image if item.layer_type == "FILL" and item.fill_source == "IMAGE" else None)
        if img is not None:
            row.label(text="", icon_value=layout.icon(img))
        elif item.layer_type == "FILL" and item.fill_source == "IMAGE":
            row.label(text="", icon='IMAGE_DATA')
        elif item.layer_type == "FILL":
            sub = row.row()
            sub.scale_x = 0.35
            sub.prop(item, "fill_color", text="")
        elif item.layer_type in LIGHT_TYPES:
            sub = row.row()
            sub.scale_x = 0.35
            stop = ramp_swatch(item)
            if stop is not None:   # (a ramp layer's colour IS its ramp: show / edit its main stop)
                sub.prop(stop, "color", text="")
            else:
                sub.prop(item, "light_color", text="")
        else:
            row.label(text="", icon=_type_icon(item))
        # the name is a button: Ctrl / Shift click multi-select, double-click renames (§33)
        act = stack.active
        sel = item.selected and not (act is not None and act.uid == item.uid)
        sub = row.row(align=True)
        sub.emboss = 'PULLDOWN_MENU'   # menu-item style: the name reads left-aligned, like Photoshop
        op = sub.operator("pl.layer_click", text=item.name, icon='CHECKMARK' if sel else 'NONE')
        op.uid = item.uid
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
        row.operator("pl.layer_drag", text="", icon='GRIP_V', emboss=False).uid = item.uid


class PL_UL_masks(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        row.prop(item, "visible", text="", emboss=False, icon='HIDE_OFF' if item.visible else 'HIDE_ON')
        icons = {s[0]: s[3] for s in MASK_SOURCES}
        if item.source == "PAINT" and item.image is not None:
            row.label(text="", icon_value=layout.icon(item.image))
        else:
            row.label(text="", icon=icons[item.source])
        row.prop(item, "name", text="", emboss=False)
        if index > 0 and item.op != "MULTIPLY":
            sub = row.row()
            sub.enabled = False
            sub.label(text=item.op.title())


class PL_MT_add_mask(bpy.types.Menu):
    bl_label = "Add Mask"

    def draw(self, context):
        for ident, name, desc, icon, _ in MASK_SOURCES:
            self.layout.operator("pl.mask_add", text=name, icon=icon).source = ident


class PL_MT_add_layer(bpy.types.Menu):
    bl_label = "Add Layer"

    def draw(self, context):
        lay = self.layout
        op = lay.operator("pl.layer_add", text="Paint", icon='BRUSH_DATA')
        op.layer_type = "PAINT"
        op = lay.operator("pl.layer_add", text="Fill Colour", icon='SNAP_FACE')
        op.layer_type, op.fill_source = "FILL", "COLOR"
        op = lay.operator("pl.layer_add", text="Fill Image", icon='IMAGE_DATA')
        op.layer_type, op.fill_source = "FILL", "IMAGE"
        lay.operator("pl.library_browse", text="Library Texture…", icon='TEXTURE').new_layer = True
        lay.separator()
        for kind, label in (("HUE_SAT", "Hue/Saturation"), ("LEVELS", "Levels"),
                            ("BRIGHT_CONTRAST", "Brightness/Contrast"), ("CURVES", "Curves")):
            op = lay.operator("pl.layer_add", text=label, icon='MODIFIER')
            op.layer_type, op.adjust_kind = "ADJUST", kind
        lay.separator()
        op = lay.operator("pl.layer_add", text="Light Ramp", icon='LIGHT_SUN')
        op.layer_type, op.preset = "NORMAL_LIGHT", "RAMP"
        op = lay.operator("pl.layer_add", text="Soft Highlight (Lambert)", icon='LIGHT_SUN')
        op.layer_type, op.preset = "NORMAL_LIGHT", "LAMBERT"
        op = lay.operator("pl.layer_add", text="Normal Light", icon='LIGHT_SUN')
        op.layer_type = "NORMAL_LIGHT"
        op = lay.operator("pl.layer_add", text="Normal Shadow", icon='LIGHT_SUN')
        op.layer_type, op.preset = "NORMAL_LIGHT", "SHADOW"
        op = lay.operator("pl.layer_add", text="Specular Light", icon='SHADING_RENDERED')
        op.layer_type = "SPEC_LIGHT"
        op = lay.operator("pl.layer_add", text="Rim Light (Fresnel)", icon='LIGHT_HEMI')
        op.layer_type = "RIM_LIGHT"
        op = lay.operator("pl.layer_add", text="Reflection Sheen", icon='LIGHT_HEMI')
        op.layer_type, op.preset = "RIM_LIGHT", "SHEEN"
        op = lay.operator("pl.layer_add", text="Subsurface Glow", icon='SHADING_RENDERED')
        op.layer_type, op.preset = "SSS_LIGHT", "SSS_GLOW"
        op = lay.operator("pl.layer_add", text="Translucency (thin parts)", icon='SHADING_RENDERED')
        op.layer_type, op.preset = "SSS_LIGHT", "SSS_TRANS"
        lay.separator()
        op = lay.operator("pl.layer_add", text="Group", icon='FILE_FOLDER')
        op.layer_type = "GROUP"


class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CaraPainter"


class PL_PT_layers(_Base, bpy.types.Panel):
    bl_label = "Layers"
    bl_idname = "PL_PT_layers"

    def draw(self, context):
        lay = self.layout
        ob = context.object
        mat = ob.active_material if ob else None
        if ob is None or ob.type != 'MESH':
            lay.label(text="Select the model")
            if not context.workspace.get("pl_painterly"):   # (works without a model too)
                lay.operator("pl.workspace_setup", icon='WORKSPACE')
            return
        if mat is None or not mat.pl_stack.enabled:
            row = lay.row()
            row.scale_y = 1.6
            row.operator("pl.new_material", icon='MATERIAL')
            if mat is not None:
                col = lay.column()
                col.label(text=f"or use the current material ({mat.name}):")
                col.operator("pl.attach", icon='LINKED')
            if not context.workspace.get("pl_painterly"):
                lay.operator("pl.workspace_setup", icon='WORKSPACE')
            return
        stack = mat.pl_stack
        if not context.workspace.get("pl_painterly"):   # (also once the material exists)
            lay.operator("pl.workspace_setup", icon='WORKSPACE')
        from ..ops.newmat import draw_textures
        draw_textures(lay, stack)
        # the light ball, always at hand (key light, or the active light layer's own direction)
        head, body = lay.panel("pl_light_ball", default_closed=False)
        head.label(text="Light", icon='LIGHT_SUN')
        if body:
            draw_light_sphere(body, context)
        act = stack.active
        top = lay.row(align=True)
        if act is not None:
            if act.layer_type == "GROUP" and act.group_mode == "PASS_THROUGH":
                top.prop(act, "group_mode", text="")
            else:
                top.prop(act, "blend_mode", text="")
            top.prop(act, "opacity", text="Opacity", slider=True)

        row = lay.row()
        row.template_list("PL_UL_layers", "", stack, "layers", stack, "active_index", rows=8)
        col = row.column(align=True)
        col.menu("PL_MT_add_layer", text="", icon='ADD')
        col.operator("pl.layer_remove", text="", icon='REMOVE')
        col.separator()
        col.operator("pl.layer_move", text="", icon='TRIA_UP').direction = "UP"
        col.operator("pl.layer_move", text="", icon='TRIA_DOWN').direction = "DOWN"
        col.separator()
        col.operator("pl.layer_duplicate", text="", icon='DUPLICATE')
        col.operator("pl.layer_group", text="", icon='FILE_FOLDER')
        col.operator("pl.layer_merge", text="", icon='AUTOMERGE_OFF')

        row = lay.row(align=True)
        on = base_view_active(context.scene)
        row.operator("pl.toggle_base_view", text="Flat (C)", icon='SHADING_SOLID', depress=on)
        from ..ops.formview import form_view_active
        row.operator("pl.toggle_form_view", text="Form (⇧C)", icon='SHADING_RENDERED',
                     depress=form_view_active(context.scene))
        n = len(material_images(mat))
        sub = row.row()
        sub.alert = n > SAMPLER_BUDGET - 3
        sub.label(text=f"Images {n}/{SAMPLER_BUDGET}", icon='IMAGE')


class PL_PT_brushes(_Base, bpy.types.Panel):
    bl_label = "Brushes"
    bl_parent_id = "PL_PT_layers"

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None

    def draw(self, context):
        lay = self.layout
        ip = context.tool_settings.image_paint
        b = ip.brush if ip else None
        if b is not None:
            row = lay.row()
            img = b.mask_texture.image if b.mask_texture else None
            if img is not None:
                row.template_icon(icon_value=lay.icon(img), scale=2.0)
            row.label(text=b.name.replace("PL Alpha · ", ""), icon='BRUSH_DATA')
        row = lay.row(align=True)
        row.scale_y = 1.4
        row.operator("pl.brush_browse", text="Alpha Brushes", icon='BRUSHES_ALL')
        row.operator("pl.brush_import", text="Import…", icon='IMPORT')


class PL_PT_brush_settings(_Base, bpy.types.Panel):
    bl_label = "Brush Settings"
    bl_parent_id = "PL_PT_brushes"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ip = context.tool_settings.image_paint
        return ip is not None and ip.brush is not None

    def draw(self, context):
        from ..ops.brushes import draw_settings
        draw_settings(self.layout, context)


class PL_PT_outline(_Base, bpy.types.Panel):
    bl_label = "Outline"
    bl_parent_id = "PL_PT_layers"

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None

    def draw_header(self, context):
        self.layout.label(text="", icon='MOD_LINEART')

    def draw(self, context):
        from ..ops import outline
        outline.draw(self.layout, context, get_stack(context)[1])


class PL_PT_layer_props(_Base, bpy.types.Panel):
    bl_label = "Layer"
    bl_parent_id = "PL_PT_layers"

    @classmethod
    def poll(cls, context):
        stack = get_stack(context)[1]
        return stack is not None and stack.active is not None

    def draw_header(self, context):
        act = get_stack(context)[1].active
        self.layout.label(text=act.name, icon=_type_icon(act))

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        lay.use_property_decorate = False
        mat, stack = get_stack(context)
        l = stack.active
        t = l.layer_type
        # built-in colour adjustments, on every layer (§40)
        head, body = lay.panel("pl_layer_colour", default_closed=True)
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
                body.use_property_split = True
            body.operator("pl.layer_colour_reset", icon='LOOP_BACK')
        if t == "FILL":
            lay.prop(l, "fill_source", expand=True)
            if l.fill_source == "COLOR":
                lay.prop(l, "fill_color")
            else:
                lay.template_ID(l, "fill_image", open="image.open")
                lay.operator("pl.library_browse", text="Texture Library", icon='TEXTURE')
                lay.prop(l, "projection", expand=True)
                if l.projection == "BOX":
                    lay.prop(l, "box_blend", slider=True)
                lay.prop(l, "tex_scale")
                lay.prop(l, "tex_rotation")
                lay.prop(l, "tex_offset")
                lay.prop(l, "tile_break", slider=True)
                if l.tile_break > 0:
                    lay.prop(l, "tile_break_size")
        elif t == "PAINT":
            row = lay.row(align=True)
            row.prop(l, "paint_image", text="Image")
            row.operator("pl.layer_new_image", text="", icon='FILE_NEW')
            if context.mode != 'PAINT_TEXTURE':
                lay.operator("object.mode_set", text="Paint", icon='BRUSH_DATA').mode = 'TEXTURE_PAINT'
        if t in ("FILL", "PAINT"):
            # the layer's height, for Height Blend masks (Phase 4)
            lay.prop(l, "height_source")
            if l.height_source == "IMAGE":
                lay.template_ID(l, "height_image", open="image.open")
            if l.height_source != "NONE" or any(m.source == "HEIGHT" for m in l.masks):
                lay.prop(l, "height_level", slider=True)
            if l.height_source in ("IMAGE", "LUMINANCE"):
                lay.prop(l, "height_strength", slider=True)
        elif t == "ADJUST":
            lay.prop(l, "adjust_kind")
            k = l.adjust_kind
            if k == "HUE_SAT":
                for p in ("hs_hue", "hs_saturation", "hs_lightness"):
                    lay.prop(l, p, slider=True)
            elif k == "LEVELS":
                col = lay.column(align=True)
                col.prop(l, "lv_in_black")
                col.prop(l, "lv_gamma")
                col.prop(l, "lv_in_white")
                col = lay.column(align=True)
                col.prop(l, "lv_out_black")
                col.prop(l, "lv_out_white")
            elif k == "BRIGHT_CONTRAST":
                lay.prop(l, "bc_brightness", slider=True)
                lay.prop(l, "bc_contrast", slider=True)
            elif k == "CURVES" and l.node_tree is not None:
                n = l.node_tree.nodes.get("ADJ.curves")
                if n is not None:
                    lay.use_property_split = False
                    lay.template_curve_mapping(n, "mapping", type='COLOR')
        elif t == "NORMAL_LIGHT" and l.light_ramp:
            # Light Ramp (§52): the ramp IS the layer - shadow, terminator, light are its stops
            n = l.node_tree.nodes.get(layer_trees.LIGHT_RAMP) if l.node_tree is not None else None
            if n is not None:
                lay.label(text="In shadow / turned away (left) → facing the sun (right):")
                lay.use_property_split = False
                lay.template_color_ramp(n, "color_ramp", expand=False)
                lay.use_property_split = True
            lay.prop(l, "include_cast_shadow")
            row = lay.row()
            row.enabled = stack.forms_c is not None
            row.prop(l, "form_size", slider=True, text="Form Size (F)")
            lay.prop(l, "normal_strength", slider=True)
            lay.prop(l, "breakup")
            if l.breakup != "NONE":
                if l.breakup == "IMAGE":
                    lay.template_ID(l, "breakup_image", open="image.open")
                lay.prop(l, "breakup_strength", slider=True)
                lay.prop(l, "breakup_scale")
            lay.prop(l, "light_override")
            if l.light_override:   # (the scene's light ball is in the Light section; this one aims the layer's own)
                lay.use_property_split = False
                draw_light_sphere(lay, context)
            if stack.normal_image is None:
                lay.label(text="No normal map found: using mesh normals", icon='INFO')
        elif t in LIGHT_TYPES:
            rim = t == "RIM_LIGHT"
            sss = t == "SSS_LIGHT"
            if sss:
                lay.prop(l, "sss_mode", expand=True)
                if l.sss_mode == "GLOW":
                    lay.prop(l, "sss_width", slider=True)
                    lay.prop(l, "include_cast_shadow", text="Glow Along Cast Shadows")
                else:
                    box = lay.box()
                    if stack.thickness_image is None:
                        box.alert = True
                        box.label(text="Bake the thickness map once:", icon='INFO')
                    else:
                        box.label(text="Thickness map baked", icon='CHECKMARK')
                    box.prop(stack, "thickness_range", slider=True)
                    box.operator("pl.bake_thickness", text="Bake Thickness" if stack.thickness_image is None
                                 else "Bake Again", icon='RENDER_STILL')
                    lay.prop(l, "sss_distortion", slider=True)
                    lay.prop(l, "sss_power")
            elif rim:
                lay.prop(l, "rim_reflect")
                if l.rim_reflect and l.node_tree is not None and l.node_tree.nodes.get("RIM.sky") is not None:
                    lay.label(text="Ground (left) → horizon → sky (right):")
                    lay.use_property_split = False
                    lay.template_color_ramp(l.node_tree.nodes["RIM.sky"], "color_ramp", expand=False)
                    lay.use_property_split = True
            else:
                lay.prop(l, "light_polarity", expand=True)
            shadow = l.light_polarity == "SHADOW" and not rim and not sss
            if not l.use_ramp and not (rim and l.rim_reflect):
                lay.prop(l, "light_color", text="Shadow Colour" if shadow else "Colour")
            if t == "SPEC_LIGHT":
                lay.prop(l, "spec_tightness", text="Tightness")
            row = lay.row()
            row.enabled = stack.forms_c is not None
            row.prop(l, "form_size", slider=True, text="Form Size (F)")
            lay.prop(l, "normal_strength", slider=True)
            lay.prop(l, "light_size", slider=True, text="Shadow Size (Shift F)" if shadow else
                     ("Amount (Shift F)" if sss else "Size (Shift F)"))
            lay.prop(l, "light_softness", slider=True)
            if shadow:
                lay.prop(l, "opacity", slider=True, text="Shadow Opacity")
                lay.prop(l, "terminator_color")
                lay.prop(l, "terminator_width", slider=True)
                lay.prop(l, "include_cast_shadow")
            elif l.layer_type == "NORMAL_LIGHT":
                lay.prop(l, "light_cast_shadow")
            lay.prop(l, "light_bands")
            lay.prop(l, "breakup")
            if l.breakup != "NONE":
                if l.breakup == "IMAGE":
                    lay.template_ID(l, "breakup_image", open="image.open")
                lay.prop(l, "breakup_strength", slider=True)
                lay.prop(l, "breakup_scale")
            if not (rim and l.rim_reflect):
                lay.prop(l, "use_ramp")
            if l.use_ramp and not (rim and l.rim_reflect) and l.node_tree is not None                     and l.node_tree.nodes.get("LIGHT.ramp") is not None:
                lay.use_property_split = False
                lay.template_color_ramp(l.node_tree.nodes["LIGHT.ramp"], "color_ramp", expand=False)
                lay.use_property_split = True
            if rim:
                lay.label(text="Tip: a Light Side mask = rim on the lit side only", icon='INFO')
            else:
                lay.prop(l, "light_override")
                if l.light_override:
                    lay.use_property_split = False
                    draw_light_sphere(lay, context)
            if stack.normal_image is None:
                lay.label(text="No normal map found: using mesh normals", icon='INFO')
        elif t == "GROUP":
            lay.prop(l, "group_mode")


class PL_PT_masks(_Base, bpy.types.Panel):
    bl_label = "Masks"
    bl_parent_id = "PL_PT_layers"

    @classmethod
    def poll(cls, context):
        stack = get_stack(context)[1]
        return stack is not None and stack.active is not None

    def draw(self, context):
        from ..analysis import cache
        lay = self.layout
        mat, stack = get_stack(context)
        l = stack.active
        state, prog, msg = cache.status(mat)
        if state == "RUNNING":
            lay.progress(factor=prog, type='BAR', text=f"Analysing normal map: {msg}")
        elif state == "ERROR":
            box = lay.box()
            box.alert = True
            box.label(text=f"Analysis failed: {msg}", icon='ERROR')
            box.operator("pl.analyse", text="Try Again", icon='FILE_REFRESH')
        elif state == "NONE" and stack.normal_image is not None:
            lay.operator("pl.analyse", icon='MOD_DISPLACE')
        row = lay.row()
        row.template_list("PL_UL_masks", "", l, "masks", l, "active_mask_index", rows=2)
        col = row.column(align=True)
        col.menu("PL_MT_add_mask", text="", icon='ADD')
        col.operator("pl.mask_remove", text="", icon='REMOVE')
        m = l.active_mask
        if m is None:
            lay.label(text="T paints a mask · D adds and drags a depth mask", icon='INFO')
            return
        col = lay.column()
        col.use_property_split = True
        col.use_property_decorate = False
        painting = l.paint_target == "MASK"
        if m.source == "PAINT":
            row = lay.row(align=True)
            row.operator("pl.mask_paint", text="Painting Mask (T)" if painting else "Paint Mask (T)",
                         icon='BRUSH_DATA', depress=painting)
            row = lay.row(align=True)
            row.operator("pl.mask_edit", text="White").action = "WHITE"
            row.operator("pl.mask_edit", text="Black").action = "BLACK"
            row.operator("pl.mask_edit", text="Invert", icon='ARROW_LEFTRIGHT').action = "INVERT"
            col = lay.column()
            col.use_property_split = True
            col.prop(m, "opacity", slider=True)
            if l.active_mask_index > 0:
                col.prop(m, "op")
            lay.operator("pl.mask_view", text="View Mask", icon='MOD_MASK', depress=stack.mask_view)
            return
        if m.source == "CURVATURE":
            col.prop(m, "curvature_kind", expand=True)
        elif m.source == "IMAGE":
            col.template_ID(m, "image", open="image.open")
            col.operator("pl.mask_paint", text="Editing Image (T)" if painting else "Edit Image (T)",
                         icon='BRUSH_DATA', depress=painting)
        if m.source == "SHADOW":
            col.label(text="White = the key light reaches it (Invert for the shadows)")
        elif m.source == "TERMINATOR":
            col.label(text="White = facing the key light (Threshold 0.5 = the terminator)")
        elif m.source == "HEIGHT":
            col.label(text="Shows where this layer is higher than what's beneath")
            col.label(text="(set the layer's Height below; Threshold raises / lowers it)")
            col.prop(stack, "height_detail", slider=True)
        elif m.source == "NOISE":
            col.prop(m, "noise_type", expand=True)
            col.prop(m, "noise_scale")
            col.prop(m, "noise_detail")
            col.prop(m, "noise_roughness", slider=True)
            if m.noise_type == "NOISE":
                col.prop(m, "noise_distortion")
            col.prop(m, "noise_seed")
        col.prop(m, "threshold", slider=True)
        col.prop(m, "softness", slider=True)
        if m.source in ("DEPTH", "CURVATURE"):
            col.prop(m, "detail", text="Fine / Broad" if m.source == "CURVATURE" else "Detail Size", slider=True)
        col.prop(m, "invert")
        row = col.row(align=True)
        row.prop(m, "opacity", slider=True)
        if l.active_mask_index > 0:
            col.prop(m, "op")
        if m.source == "DEPTH":
            row = lay.row(align=True)
            row.operator("pl.mask_paint", text="Painting Correction (T)" if painting else
                         "Paint Correction (T)", icon='BRUSH_DATA', depress=painting)
            if m.correction is not None:
                row.prop(m, "correction_strength", text="Strength", slider=True)
        lay.operator("pl.mask_view", text="View Mask", icon='MOD_MASK', depress=stack.mask_view)


class PL_PT_blend_if(_Base, bpy.types.Panel):
    bl_label = "Blend If"
    bl_parent_id = "PL_PT_layers"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        stack = get_stack(context)[1]
        l = stack.active if stack else None
        return l is not None and l.node_tree is not None and not (
            l.layer_type == "GROUP" and l.group_mode == "PASS_THROUGH")

    def draw_header(self, context):
        self.layout.prop(get_stack(context)[1].active, "blend_if", text="")

    def draw(self, context):
        lay = self.layout
        l = get_stack(context)[1].active
        if not l.blend_if:   # (§59: off costs nothing; dragging a stop turns it on)
            lay.label(text="Off: drag a stop (or tick the box) to use it", icon='INFO')
        lay.prop(l, "blend_if_channel", expand=True)
        for which, label in (("this", "This Layer"), ("under", "Underlying Layer")):
            n = l.node_tree.nodes.get(f"BI.{which}.{l.blend_if_channel}")
            if n is None:
                continue
            lay.label(text=label)
            lay.template_color_ramp(n, "color_ramp", expand=False)
        lay.label(text="Drag the inner stops apart for a soft falloff", icon='INFO')


class PL_PT_selection(_Base, bpy.types.Panel):
    bl_label = "Selection"
    bl_parent_id = "PL_PT_layers"

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None and context.mode == 'PAINT_TEXTURE'

    def draw(self, context):
        from ..ops.select import selection_image
        lay = self.layout
        has = selection_image(context) is not None
        row = lay.row(align=True)
        row.operator("pl.lasso_select", text="Lasso (L)", icon='MOD_CURVE')
        row.operator("pl.transform", text="Transform (Ctrl T)", icon='OBJECT_ORIGIN')
        row = lay.row(align=True)
        row.prop(context.scene, "pl_sel_feather")
        row = lay.row(align=True)
        row.enabled = has
        row.operator("pl.deselect", text="Deselect", icon='X')
        row.operator("pl.select_invert", text="Invert", icon='ARROW_LEFTRIGHT')
        row = lay.row(align=True)
        row.enabled = has
        row.operator("pl.selection_delete", text="Delete", icon='TRASH')
        row.operator("pl.selection_fill", text="Fill", icon='BRUSH_DATA')
        if has:
            lay.prop(context.scene.tool_settings.image_paint, "stencil_color", text="Tint")


class PL_PT_lighting(_Base, bpy.types.Panel):
    bl_label = "Lighting & Bake"
    bl_parent_id = "PL_PT_layers"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None

    def draw(self, context):
        lay = self.layout
        mat, stack = get_stack(context)
        sc = context.scene
        row = lay.row(align=True)
        row.prop(sc, "pl_key_light", text="Key Light")
        row.operator("pl.key_light_choose", text="", icon='LIGHT_SUN')
        lay.operator("pl.hybrid_toggle", icon='SHADING_RENDERED', depress=stack.hybrid,
                     text="Hybrid Lighting (on)" if stack.hybrid else "Hybrid Lighting")
        if stack.hybrid:
            lay.label(text="Lighting comes from the light layers; click again for your shader", icon='INFO')
        box = lay.box()
        box.operator("pl.bake", icon='RENDER_STILL')
        row = box.row(align=True)
        row.enabled = stack.baked_image is not None
        row.operator("pl.bake_mode", text="Live", depress=stack.mode == "LIVE").mode = "LIVE"
        row.operator("pl.bake_mode", text="Baked", depress=stack.mode == "BAKED").mode = "BAKED"
        box.operator("pl.export_png", icon='EXPORT')


class PL_PT_stack_settings(_Base, bpy.types.Panel):
    bl_label = "Stack Settings"
    bl_parent_id = "PL_PT_layers"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        mat, stack = get_stack(context)
        lay.prop(stack, "blend_space")
        lay.prop(stack, "normal_image")
        from ..ops.attach import normal_colorspace_wrong
        if normal_colorspace_wrong(stack):
            box = lay.box()
            box.alert = True
            box.label(text="Normal map is set to sRGB: UV seams show", icon='ERROR')
            box.operator("pl.fix_normal_colorspace", text="Fix: set to Non-Color", icon='CHECKMARK')
        ob = context.object
        lay.prop_search(stack, "uv_map", ob.data, "uv_layers", text="UV Map")
        lay.prop(context.scene, "pl_key_light")
        if context.scene.pl_key_light is None:
            lay.operator("pl.key_light_detect", icon='LIGHT_SUN')
        lay.separator()
        lay.operator("pl.detach", icon='UNLINKED')


def _wrap(text, n):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur]


def draw_light_sphere(layout, context):
    """The light sphere + readout. Shared by the header popover and the layer panel."""
    import math
    from ..ops.keylight import light_target, world_light_dir
    sc = context.scene
    kind, target = light_target(sc)
    col = layout.column()
    if kind == "key":
        col.prop(sc, "pl_key_light", text="")
        from ..ops.keylight import key_light_issue
        issue = key_light_issue(sc)
        if issue is not None:
            box = col.box()
            box.alert = True
            for i, line in enumerate(_wrap(issue[0], 46)):
                box.label(text=line, icon='ERROR' if i == 0 else 'BLANK1')
            if issue[2] == 'KEY':
                box.operator("pl.key_light_use", text=f"Use '{issue[1].name}' as Key Light",
                             icon='LIGHT_SUN').name = issue[1].name
            elif issue[2] == 'NORENDER':
                box.operator("pl.light_render_off", text=f"Turn '{issue[1].name}' Off in Renders",
                             icon='RESTRICT_RENDER_ON').name = issue[1].name
        if target is None:
            col.operator("pl.key_light_detect", icon='LIGHT_SUN')
            return
    else:
        col.label(text=f"Layer light: {target.name}", icon='LIGHT_SUN')
    big = col.column()
    big.scale_y = 2.0
    big.prop(sc, "pl_light_widget", text="")
    d = world_light_dir(sc)
    row = col.row()
    row.enabled = False
    row.label(text=f"Around {math.degrees(math.atan2(d.y, d.x)):.0f}°   "
                   f"Height {math.degrees(math.asin(max(-1.0, min(1.0, d.z)))):.0f}°")


class PL_PT_light_popover(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Light Direction"
    bl_ui_units_x = 9

    def draw(self, context):
        draw_light_sphere(self.layout, context)


def header_button(self, context):
    from ..ops.view import in_painterly
    if in_painterly(context):
        self.layout.popover("PL_PT_light_popover", text="", icon='LIGHT_SUN')


classes = (PL_UL_layers, PL_UL_masks, PL_MT_add_mask, PL_PT_light_popover, PL_MT_add_layer, PL_PT_layers, PL_PT_brushes, PL_PT_brush_settings, PL_PT_outline, PL_PT_layer_props, PL_PT_masks, PL_PT_blend_if,
           PL_PT_selection, PL_PT_lighting, PL_PT_stack_settings)
