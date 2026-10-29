"""Texture library operators (Phase 5): thumbnail browser popup, apply a set to a Fill layer,
library folders in the add-on preferences."""
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from .. import library, props
from ..compiler import compile_stack
from .layers import _StackOp, add_layer, get_stack

GRID_MAX = 60
_cat_items = []   # keep a reference: Blender crashes if dynamic enum strings are freed


def _categories(self, context):
    _cat_items.clear()
    _cat_items.append(("ALL", "All", "Every category"))
    _cat_items.extend((c, c, "") for c in library.categories())
    return _cat_items


class PL_LibFolder(bpy.types.PropertyGroup):
    path: StringProperty(name="Folder", subtype='DIR_PATH')


def apply_set(mat, s, layer_uid=None):
    """Put texture set `s` on the Fill layer `layer_uid` (or a new Fill layer). Returns the layer."""
    stack = mat.pl_stack
    col = library.load_image(s.color, label=f"{s.name} · colour")
    hgt = library.load_image(s.height, non_color=True, label=f"{s.name} · height") if s.height else None
    layer = stack.by_uid(layer_uid) if layer_uid else None
    if layer is None:
        kw = dict(fill_source="IMAGE", fill_image=col, name=s.name, lib_set=s.key)
        if hgt is not None:
            kw.update(height_source="IMAGE", height_image=hgt)
        return add_layer(mat, "FILL", **kw)
    uid = layer.uid
    with props.suspended():
        layer.fill_source = "IMAGE"
        layer.fill_image = col
        layer.lib_set = s.key
        if hgt is not None:
            layer.height_image = hgt
            layer.height_source = "IMAGE"
    compile_stack(mat)
    return stack.by_uid(uid)


class PL_OT_library_browse(_StackOp, bpy.types.Operator):
    bl_idname = "pl.library_browse"
    bl_label = "Texture Library"
    bl_description = "Browse your texture library (folders are set in the add-on preferences)"
    bl_options = {'REGISTER'}
    new_layer: BoolProperty(default=False, options={'SKIP_SAVE'},
                            description="Add the texture as a new Fill layer (else: the active Fill layer)")

    def invoke(self, context, event):
        library.scan()
        return context.window_manager.invoke_popup(self, width=760)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        wm = context.window_manager
        lay = self.layout
        row = lay.row(align=True)
        row.prop(wm, "pl_lib_search", text="", icon='VIEWZOOM')
        row.operator("pl.library_rescan", text="", icon='FILE_REFRESH')
        row = lay.row(align=True)
        row.prop(wm, "pl_lib_category", expand=True)
        sets = library.filtered(wm.pl_lib_search, wm.pl_lib_category)
        if not library.scan():
            box = lay.box()
            box.label(text="No textures found in: " + ("; ".join(library.folders()) or "(no folders)"), icon='INFO')
            box.label(text="Add folders in Preferences > Add-ons > CaraPainter")
            return
        if not sets:
            lay.label(text="Nothing matches", icon='INFO')
            return
        grid = lay.grid_flow(row_major=True, columns=6, even_columns=True, even_rows=True)
        for s in sets[:GRID_MAX]:
            col = grid.column(align=True)
            col.template_icon(icon_value=library.icon(s), scale=5.0)
            op = col.operator("pl.library_apply", text=s.name + ("  ▲" if s.height else ""))
            op.key, op.new_layer = s.key, self.new_layer
        if len(sets) > GRID_MAX:
            lay.label(text=f"{len(sets) - GRID_MAX} more: type to search", icon='INFO')
        lay.label(text="▲ = has a height map (Height Blend uses it)")


class PL_OT_library_apply(_StackOp, bpy.types.Operator):
    bl_idname = "pl.library_apply"
    bl_label = "Use Texture"
    bl_description = ("Use this texture: replaces the active library Fill, else adds a new Fill layer "
                      "(downscaled to 2048 and packed; the original file is untouched)")
    key: StringProperty(options={'SKIP_SAVE'})
    new_layer: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        mat, stack = get_stack(context)
        s = library.find(self.key)
        if s is None:
            self.report({'ERROR'}, "Texture not found (rescan the library)")
            return {'CANCELLED'}
        act = stack.active
        # replace only a library fill (never e.g. the Base layer's own texture): else a new layer
        target = act.uid if (act is not None and act.layer_type == "FILL" and act.lib_set
                             and not self.new_layer) else None
        layer = apply_set(mat, s, target)
        self.report({'INFO'}, f"{layer.name}: {s.name}" + (" + height" if s.height else ""))
        return {'FINISHED'}


class PL_OT_library_rescan(bpy.types.Operator):
    bl_idname = "pl.library_rescan"
    bl_label = "Rescan Library"
    bl_description = "Look for new or changed textures in the library folders"

    def execute(self, context):
        library.free_previews()
        n = len(library.scan(force=True))
        self.report({'INFO'}, f"{n} texture sets")
        return {'FINISHED'}


class PL_OT_library_folder(bpy.types.Operator):
    bl_idname = "pl.library_folder"
    bl_label = "Library Folder"
    bl_description = "Add or remove a library folder"
    remove: IntProperty(default=-1, options={'SKIP_SAVE'})

    def execute(self, context):
        p = library.prefs()
        if p is None:
            return {'CANCELLED'}
        if self.remove >= 0:
            p.library_folders.remove(self.remove)
        else:
            p.library_folders.add()
        return {'FINISHED'}


def draw_prefs(layout):
    p = library.prefs()
    box = layout.box()
    box.label(text="Texture library folders (subfolders become categories)", icon='TEXTURE')
    if p is not None:
        for i, f in enumerate(p.library_folders):
            row = box.row(align=True)
            row.prop(f, "path", text="")
            row.operator("pl.library_folder", text="", icon='X').remove = i
        if not len(p.library_folders):
            box.label(text=f"Default: {library.DEFAULT_FOLDER}")
    row = box.row()
    row.operator("pl.library_folder", text="Add Folder", icon='ADD')
    row.operator("pl.library_rescan", icon='FILE_REFRESH')


classes = (PL_LibFolder, PL_OT_library_browse, PL_OT_library_apply, PL_OT_library_rescan, PL_OT_library_folder)


def register():
    bpy.types.WindowManager.pl_lib_search = StringProperty(name="Search", options={'TEXTEDIT_UPDATE'})
    bpy.types.WindowManager.pl_lib_category = EnumProperty(name="Category", items=_categories)


def unregister():
    del bpy.types.WindowManager.pl_lib_category
    del bpy.types.WindowManager.pl_lib_search
    library.free_previews()
