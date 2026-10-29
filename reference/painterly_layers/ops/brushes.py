"""Alpha brushes: one click turns a black-and-white image into a Texture Paint brush (§30).

The image becomes the brush's MASK texture (view plane, constant falloff), so its shape is the
stamp. Black-on-white alphas (Photoshop style) are detected and inverted. The alpha is stored
as its own small packed image (max 1024), the brush is a local asset (Blender 5 activates brushes
as assets), so it also shows in Blender's own brush selector.
"""
import os

import bpy
import numpy as np
from bpy.props import CollectionProperty, StringProperty

from .. import library

MAX_ALPHA = 1024
PREFIX = "PL Alpha · "
TEST_FOLDERS = []
_cache = {"key": None, "items": []}


# ----------------------------------------------------------------------------- folders

def folders():
    if TEST_FOLDERS:
        return list(TEST_FOLDERS)
    p = library.prefs()
    return [bpy.path.abspath(f.path) for f in p.brush_folders if f.path.strip()] if p is not None else []


def scan(force=False):
    """[(path, name, category)] for every image in the brush folders."""
    roots = folders()
    stamp = tuple((r, library._tree_mtime(r)) for r in roots)
    if not force and _cache["key"] == stamp:
        return _cache["items"]
    out = []
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            rel = os.path.relpath(dirpath, root)
            cat = "" if rel == "." else rel.replace("\\", "/").split("/")[0]
            for f in sorted(files):
                stem, ext = os.path.splitext(f)
                if ext.lower() in library.IMAGE_EXT:
                    out.append((os.path.join(dirpath, f), stem.replace("_", " "), cat))
    _cache["key"], _cache["items"] = stamp, out
    return out


# ----------------------------------------------------------------------------- brush creation

def alpha_from_image(img):
    """0..1 stamp (white = paint) from an image: its alpha if it has a shape in alpha, else its
    brightness; inverted if it's dark-on-light (border brighter than the middle)."""
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    a = px[..., 3]
    lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    if a.min() < 0.95 and lum.std() < 0.05:   # shape lives in the alpha channel
        v = a
    else:
        v = lum * a if a.min() < 0.95 else lum
        border = np.concatenate([v[0], v[-1], v[:, 0], v[:, -1]])
        if border.mean() > 0.5:               # black ink on white paper
            v = 1.0 - v
    return np.clip(v, 0.0, 1.0)


def find_brush(path):
    return next((b for b in bpy.data.brushes if b.get("pl_alpha_src") == path), None)


def make_brush(path):
    """The alpha brush for this image file (reused if it exists)."""
    b = find_brush(path)
    if b is not None:
        return b
    stem = os.path.splitext(os.path.basename(path))[0]
    src = bpy.data.images.load(path, check_existing=False)
    w, h = src.size
    if max(w, h) > MAX_ALPHA:
        k = MAX_ALPHA / max(w, h)
        src.scale(max(1, round(w * k)), max(1, round(h * k)))
        w, h = src.size
    v = alpha_from_image(src)
    bpy.data.images.remove(src)
    img = bpy.data.images.new(PREFIX + stem, w, h, alpha=False)
    img.colorspace_settings.name = "Non-Color"     # before the pixels (else it regenerates)
    rgba = np.empty((h, w, 4), np.float32)
    rgba[..., :3] = v[..., None]
    rgba[..., 3] = 1.0
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    img.pack()
    img["pl_owned"] = True
    tex = bpy.data.textures.new(PREFIX + stem, 'IMAGE')
    tex.image = img
    tex.extension = 'CLIP'
    b = bpy.data.brushes.new(PREFIX + stem, mode='TEXTURE_PAINT')
    b.mask_texture = tex
    b.mask_texture_slot.mask_map_mode = 'VIEW_PLANE'
    b.curve_distance_falloff_preset = 'CONSTANT'   # the alpha alone is the shape
    b.spacing = 15
    b["pl_alpha_src"] = path
    b.asset_mark()
    set_preview(b)
    return b


PREVIEW = 128


def set_preview(b):
    """The brush's icon (asset shelf, brush selector) = its alpha: a white shape on dark grey (the
    shelf ignores icon transparency)."""
    img = b.mask_texture.image if b.mask_texture else None
    if img is None:
        return False
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    v = px.reshape(h, w, 4)[..., 0]
    s = max(w, h)
    sq = np.zeros((s, s), np.float32)                 # pad to square, centred
    sq[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = v
    idx = (np.arange(PREVIEW) * s / PREVIEW).astype(int)
    small = sq[idx][:, idx]
    rgba = np.ones((PREVIEW, PREVIEW, 4), np.float32)
    rgba[..., :3] = (0.12 + 0.88 * small)[..., None]
    pv = b.preview_ensure()
    pv.image_size = (PREVIEW, PREVIEW)
    pv.image_pixels_float.foreach_set(rgba.ravel())
    b["pl_preview"] = True
    return True


def refresh_previews():
    """Alpha brushes imported before brush icons existed get theirs (on file load)."""
    for b in bpy.data.brushes:
        if b.get("pl_alpha_src") and not b.get("pl_preview") and b.library is None:
            set_preview(b)


def activate(context, brush):
    """Make `brush` the Texture Paint brush (Blender 5: brushes are activated as assets)."""
    ob = context.active_object
    if ob is not None and ob.type == 'MESH' and ob.mode != 'TEXTURE_PAINT':
        bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
    res = bpy.ops.brush.asset_activate(asset_library_type='LOCAL', relative_asset_identifier="Brush/" + brush.name)
    sync_jitter()
    ip = context.tool_settings.image_paint
    return 'FINISHED' in res and ip.brush is not None and ip.brush.name == brush.name


def file_brushes():
    return [b for b in bpy.data.brushes if b.get("pl_alpha_src")]


# ----------------------------------------------------------------------------- operators

class PL_OT_brush_import(bpy.types.Operator):
    bl_idname = "pl.brush_import"
    bl_label = "Import Alpha Brushes"
    bl_description = ("Pick black-and-white alpha images from any folder: each becomes a Texture Paint "
                      "brush, the first one ready to paint with")
    bl_options = {'REGISTER', 'UNDO'}
    filter_image: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    directory: StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={'SKIP_SAVE'})
    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        paths = [os.path.join(self.directory, f.name) for f in self.files if f.name] or \
                ([self.filepath] if self.filepath else [])
        paths = [p for p in paths if os.path.splitext(p)[1].lower() in library.IMAGE_EXT and os.path.isfile(p)]
        if not paths:
            self.report({'ERROR'}, "No image selected")
            return {'CANCELLED'}
        made = [make_brush(p) for p in paths]
        activate(context, made[0])
        self.report({'INFO'}, f"{len(made)} alpha brush(es): {made[0].name} active")
        return {'FINISHED'}


class PL_OT_brush_use(bpy.types.Operator):
    bl_idname = "pl.brush_use"
    bl_label = "Use Alpha Brush"
    bl_description = "Paint with this alpha (made into a brush the first time)"
    bl_options = {'REGISTER', 'UNDO'}
    path: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if not os.path.isfile(self.path) and find_brush(self.path) is None:
            self.report({'ERROR'}, "Image not found")
            return {'CANCELLED'}
        b = make_brush(self.path)
        activate(context, b)
        return {'FINISHED'}


class PL_OT_brush_folder_add(bpy.types.Operator):
    bl_idname = "pl.brush_folder_add"
    bl_label = "Add Brush Folder"
    bl_description = "Choose a folder of alpha images: they all show in the brush grid"
    directory: StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        p = library.prefs()
        if p is None:
            TEST_FOLDERS.append(self.directory)
        elif self.directory not in [f.path for f in p.brush_folders]:
            p.brush_folders.add().path = self.directory
            bpy.context.preferences.is_dirty = True
        scan(force=True)
        return {'FINISHED'}


class PL_OT_brush_folder_remove(bpy.types.Operator):
    bl_idname = "pl.brush_folder_remove"
    bl_label = "Remove Brush Folder"
    bl_description = "Stop listing this folder (nothing is deleted)"
    index: bpy.props.IntProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        p = library.prefs()
        if p is not None and 0 <= self.index < len(p.brush_folders):
            p.brush_folders.remove(self.index)
        return {'FINISHED'}


class PL_OT_brush_browse(bpy.types.Operator):
    bl_idname = "pl.brush_browse"
    bl_label = "Alpha Brushes"
    bl_description = "Your alpha brushes: click one to paint with it"

    def invoke(self, context, event):
        scan()
        return context.window_manager.invoke_popup(self, width=700)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        lay = self.layout
        row = lay.row(align=True)
        row.operator("pl.brush_import", text="Import from Any Folder…", icon='FILEBROWSER')
        row.operator("pl.brush_folder_add", text="Add Brush Folder…", icon='NEWFOLDER')
        items = scan()
        ip = context.tool_settings.image_paint
        active = ip.brush.get("pl_alpha_src") if ip and ip.brush else None
        if items:
            grid = lay.grid_flow(row_major=True, columns=8, even_columns=True, even_rows=True)
            for path, name, _cat in items[:120]:
                col = grid.column(align=True)
                col.template_icon(icon_value=library.icon_for_path(path), scale=3.5)
                op = col.operator("pl.brush_use", text=name, depress=(path == active))
                op.path = path
        else:
            lay.label(text="Add a folder of alpha images, or import from any folder", icon='INFO')
        saved = saved_brushes()
        if saved:
            lay.label(text="My Brushes (saved, in every file):", icon='SOLO_ON')
            grid = lay.grid_flow(row_major=True, columns=8, even_columns=True, even_rows=True)
            cur = ip.brush.name if ip and ip.brush else ""
            for name, rel, thumb in saved:
                col = grid.column(align=True)
                col.template_icon(icon_value=library.icon_for_path(thumb) if os.path.exists(thumb) else 0,
                                  scale=3.5)
                col.operator("pl.brush_use_saved", text=name.replace(PREFIX, ""), depress=(name == cur)).rel = rel
        extra = [b for b in file_brushes() if b.library is None and b["pl_alpha_src"] not in {i[0] for i in items}]
        if extra:
            lay.label(text="Imported in this file:")
            grid = lay.grid_flow(row_major=True, columns=8, even_columns=True, even_rows=True)
            for b in extra:
                col = grid.column(align=True)
                img = b.mask_texture.image if b.mask_texture else None
                col.template_icon(icon_value=lay.icon(img) if img else 0, scale=3.5)
                op = col.operator("pl.brush_use", text=b.name.replace(PREFIX, ""),
                                  depress=(b["pl_alpha_src"] == active))
                op.path = b["pl_alpha_src"]
        p = library.prefs()
        if p is not None and len(p.brush_folders):
            box = lay.box()
            for i, f in enumerate(p.brush_folders):
                r = box.row(align=True)
                r.label(text=f.path, icon='FILE_FOLDER')
                r.operator("pl.brush_folder_remove", text="", icon='X').index = i


def draw_prefs(layout):
    p = library.prefs()
    box = layout.box()
    box.label(text="Alpha brush folders", icon='BRUSH_DATA')
    if p is not None:
        for i, f in enumerate(p.brush_folders):
            row = box.row(align=True)
            row.prop(f, "path", text="")
            row.operator("pl.brush_folder_remove", text="", icon='X').index = i
    box.operator("pl.brush_folder_add", text="Add Folder", icon='ADD')


classes = (PL_OT_brush_import, PL_OT_brush_use, PL_OT_brush_folder_add, PL_OT_brush_folder_remove,
           PL_OT_brush_browse)


# ----------------------------------------------------------------------------- brush settings + My Brushes

TEST_LIBRARY = []   # [(name, path)] in tests: never write to the user's real asset library
CATALOG = "CaraPainter"


def brush_library():
    """(name, path) of the asset library favourites are saved to: 'User Library' if present."""
    if TEST_LIBRARY:
        return TEST_LIBRARY[0]
    libs = list(bpy.context.preferences.filepaths.asset_libraries)
    lib = next((l for l in libs if l.name == "User Library"), libs[0] if libs else None)
    return (lib.name, bpy.path.abspath(lib.path)) if lib is not None else (None, None)


def _thumb_dir():
    try:
        d = bpy.utils.extension_path_user(library.ROOT_PKG, path="brush_thumbs", create=True)
    except (ValueError, RuntimeError, AttributeError):
        d = os.path.join(bpy.app.tempdir or os.environ.get("TEMP", "."), "painterly_brush_thumbs")
    os.makedirs(d, exist_ok=True)
    return d


def _thumb_path(name):
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return os.path.join(_thumb_dir(), safe + ".png")


def saved_brushes():
    """[(name, relative asset identifier, thumbnail)] of alpha brushes saved to My Brushes."""
    lib_name, path = brush_library()
    folder = os.path.join(path, "Saved", "Brushes") if path else None
    if not folder or not os.path.isdir(folder):
        return []
    out = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(".asset.blend") and f.startswith(PREFIX):
            name = f[:-len(".asset.blend")]
            out.append((name, f"Saved/Brushes/{f}/Brush/{name}", _thumb_path(name)))
    return out


def _write_thumb(b):
    img = b.mask_texture.image if b.mask_texture else None
    if img is None:
        return
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    k = max(1, max(w, h) // 128)
    small = px.reshape(h, w, 4)[::k, ::k].copy()
    t = bpy.data.images.new("pl_thumb", small.shape[1], small.shape[0], alpha=True)
    t.pixels.foreach_set(small.ravel())
    t.filepath_raw = _thumb_path(b.name)
    t.file_format = 'PNG'
    t.save()
    bpy.data.images.remove(t)


class PL_OT_brush_save(bpy.types.Operator):
    bl_idname = "pl.brush_save"
    bl_label = "Save to My Brushes"
    bl_description = ("Save this brush, with its settings, to your asset library: it's then in the brush grid "
                      "(and Blender's brush selector) in every file. Saved again = updated")

    @classmethod
    def poll(cls, context):
        ip = context.tool_settings.image_paint
        return ip is not None and ip.brush is not None and brush_library()[0] is not None

    def execute(self, context):
        b = context.tool_settings.image_paint.brush
        lib_name, _path = brush_library()
        _write_thumb(b)
        if b.get("pl_alpha_src") and b.library is None:
            set_preview(b)                     # saved with the brush asset
        if b.library is not None:            # already a saved brush: store the changes
            res = bpy.ops.brush.asset_save()
        else:
            res = bpy.ops.brush.asset_save_as(name=b.name, asset_library_reference=lib_name, catalog_path=CATALOG)
        if 'FINISHED' not in res:
            return {'CANCELLED'}
        self.report({'INFO'}, f"Saved to {lib_name}: {b.name.replace(PREFIX, '')}")
        return {'FINISHED'}


class PL_OT_brush_use_saved(bpy.types.Operator):
    bl_idname = "pl.brush_use_saved"
    bl_label = "Use Saved Brush"
    bl_description = "Paint with this saved brush"
    bl_options = {'REGISTER', 'UNDO'}
    rel: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        lib_name, _p = brush_library()
        ob = context.active_object
        if ob is not None and ob.type == 'MESH' and ob.mode != 'TEXTURE_PAINT':
            bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        res = bpy.ops.brush.asset_activate(asset_library_type='CUSTOM', asset_library_identifier=lib_name,
                                           relative_asset_identifier=self.rel)
        sync_jitter()
        return res


def draw_settings(layout, context):
    """Brush settings in the CaraPainter sidebar: the native brush options, grouped like Photoshop."""
    ip = context.tool_settings.image_paint
    b = ip.brush if ip else None
    if b is None:
        layout.label(text="No brush")
        return
    layout.use_property_split = True
    layout.use_property_decorate = False

    head, body = layout.panel("pl_brush_stroke", default_closed=False)
    head.label(text="Stroke")
    if body:
        body.prop(b, "spacing", text="Spacing %", slider=True)
        row = body.row(align=True)
        row.prop(b, "jitter", text="Scatter", slider=True)
        row.prop(b, "use_pressure_jitter", text="", icon='STYLUS_PRESSURE')
        body.prop(b, "use_smooth_stroke", text="Smooth Stroke")
        if b.use_smooth_stroke:
            body.prop(b, "smooth_stroke_radius", text="Radius")
            body.prop(b, "smooth_stroke_factor", text="Factor", slider=True)

    if b.mask_texture is not None:
        slot = b.mask_texture_slot
        head, body = layout.panel("pl_brush_shape", default_closed=False)
        head.label(text="Shape")
        if body:
            body.prop(slot, "angle", text="Angle")
            body.prop(slot, "use_rake", text="Follow Stroke")
            body.prop(slot, "use_random", text="Random Angle")
            if slot.use_random:
                body.prop(slot, "random_angle", text="Range")

    head, body = layout.panel("pl_brush_colour", default_closed=False)
    # (the brush's own values; mirrored to the unified colour settings that painting uses)
    head.prop(b, "use_color_jitter", text="Colour Jitter")
    if body:
        body.active = b.use_color_jitter
        for label, amount, per_stroke, press in (("Hue", "hue_jitter", "use_stroke_random_hue", "use_random_press_hue"),
                                                 ("Saturation", "saturation_jitter", "use_stroke_random_sat",
                                                  "use_random_press_sat"),
                                                 ("Value", "value_jitter", "use_stroke_random_val", "use_random_press_val")):
            row = body.row(align=True)
            row.prop(b, amount, text=label, slider=True)
            row.prop(b, per_stroke, text="", icon='STROKE', toggle=True)
            row.prop(b, press, text="", icon='STYLUS_PRESSURE', toggle=True)
        body.label(text="Stroke icon: once per stroke (else every dab)")

    head, body = layout.panel("pl_brush_pressure", default_closed=True)
    head.label(text="Pen Pressure")
    if body:
        for label, prop, curve in (("Size", "use_pressure_size", "curve_size"),
                                   ("Opacity", "use_pressure_strength", "curve_strength")):
            body.prop(b, prop, text=label)
            if getattr(b, prop):
                body.use_property_split = False
                body.template_curve_mapping(b, curve, brush=True)
                body.use_property_split = True
        body.prop(b, "use_pressure_spacing", text="Spacing")

    row = layout.row(align=True)
    row.use_property_split = False
    row.operator("pl.brush_save", text="Save Changes" if b.library else "Save to My Brushes", icon='FILE_TICK')
    if b.library is not None:
        pass


classes = classes + (PL_OT_brush_save, PL_OT_brush_use_saved)


# ----------------------------------------------------------------------------- per-brush colour jitter
# Texture painting reads colour jitter from the unified paint settings (even with unified colour
# off), not the brush. The brush keeps its own jitter (saved with it); this mirrors the
# active brush's values into the unified settings whenever they or the active brush change.

JITTER_PROPS = ("use_color_jitter", "hue_jitter", "saturation_jitter", "value_jitter",
                "use_stroke_random_hue", "use_stroke_random_sat", "use_stroke_random_val",
                "use_random_press_hue", "use_random_press_sat", "use_random_press_val")
_owner = object()


def sync_jitter(*_):  # always: painting reads the unified jitter even with unified colour off
    ts = bpy.context.scene.tool_settings if bpy.context.scene else None
    ip = ts.image_paint if ts else None
    if ip is None or ip.brush is None:
        return
    ups = ip.unified_paint_settings
    b = ip.brush
    for p in JITTER_PROPS:
        v = getattr(b, p)
        if getattr(ups, p) != v:
            setattr(ups, p, v)


def subscribe():
    bpy.msgbus.clear_by_owner(_owner)
    for p in JITTER_PROPS:
        bpy.msgbus.subscribe_rna(key=(bpy.types.Brush, p), owner=_owner, args=(), notify=sync_jitter)
    for key in ((bpy.types.ImagePaint, "brush"), (bpy.types.Paint, "brush")):
        try:
            bpy.msgbus.subscribe_rna(key=key, owner=_owner, args=(), notify=sync_jitter)
        except (TypeError, KeyError, ValueError):
            pass


def unsubscribe():
    bpy.msgbus.clear_by_owner(_owner)
