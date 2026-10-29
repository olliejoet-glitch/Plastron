"""Brush palette (right-click on the canvas) and importing brushes into it.

The palette is Blender's brush shelf as a pop-up: Blender's own brushes plus
the "Plastron Brushes" library, a folder in Blender's config folder (kept
across updates) that Plastron adds as an asset library at every start.

Import Brushes takes:
  .abr               Photoshop brushes (their sampled tips)
  .png .jpg .tif...  an image is a brush tip (white / light = paint)
  .blend             Blender brushes (texture paint ones)
Each imported file becomes one .blend in the library, its brushes marked as
assets, so they show in the palette.
"""

import os

import bpy
import numpy as np

from ...config import tools as tools_cfg
from . import abr

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".tga", ".webp")
PREVIEW = 128


def library_dir():
    return os.path.join(bpy.utils.user_resource('CONFIG'), "plastron_brushes")


def ensure_library():
    """Add the Plastron Brushes asset library (Blender's preferences aren't saved)."""
    folder = library_dir()
    os.makedirs(folder, exist_ok=True)
    libs = bpy.context.preferences.filepaths.asset_libraries
    lib = next((l for l in libs if l.name == tools_cfg.BRUSH_LIBRARY_NAME), None)
    if lib is None:
        lib = libs.new(name=tools_cfg.BRUSH_LIBRARY_NAME, directory=folder)
    elif os.path.normpath(bpy.path.abspath(lib.path)) != os.path.normpath(folder):
        lib.path = folder
    return lib


# --- making brushes ------------------------------------------------------------------

def _set_preview(brush, tip):
    """A grey-on-dark picture of the tip as the brush's thumbnail."""
    h, w = tip.shape
    ys = (np.arange(PREVIEW) * h // PREVIEW)[::-1]
    xs = np.arange(PREVIEW) * w // PREVIEW
    v = tip[np.ix_(ys, xs)].astype(np.float32) / 255.0
    rgba = np.empty((PREVIEW, PREVIEW, 4), np.float32)
    rgba[..., :3] = (0.12 + 0.8 * v)[..., None]
    rgba[..., 3] = 1.0
    preview = brush.preview_ensure()
    preview.image_size = (PREVIEW, PREVIEW)
    preview.image_pixels_float.foreach_set(rgba.ravel())


def brush_from_tip(name, tip):
    """A texture-paint brush whose dab is shaped like tip (uint8 rows, top
    first, 255 = paint). Returns (brush, [datablocks to save with it])."""
    h, w = tip.shape
    img = bpy.data.images.new(name, w, h, alpha=False)
    v = (tip[::-1].astype(np.float32) / 255.0)
    rgba = np.empty((h, w, 4), np.float32)
    rgba[..., :3] = v[..., None]
    rgba[..., 3] = 1.0
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    img.pack()
    tex = bpy.data.textures.new(name, 'IMAGE')
    tex.image = img
    tex.extension = 'CLIP'
    brush = bpy.data.brushes.new(name, mode='TEXTURE_PAINT')
    brush.mask_texture = tex
    brush.mask_texture_slot.mask_map_mode = 'VIEW_PLANE'
    brush.curve_distance_falloff_preset = 'CONSTANT'     # the tip is the shape
    brush.spacing = 25                                   # Photoshop's default
    brush.use_pressure_size = True
    brush.size = int(min(200, max(5, max(w, h) // 2)))
    _set_preview(brush, tip)
    return brush, [brush, tex, img]


def _image_tip(path):
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    px = px.reshape(h, w, 4)[::-1]
    grey = px[..., :3].mean(-1)
    if px[..., 3].min() < 0.99:             # transparent background: the shape is the alpha
        grey = px[..., 3]
    elif grey.mean() > 0.5:                  # dark marks on white paper: dark = paint
        grey = 1.0 - grey
    return np.clip(grey * 255 + 0.5, 0, 255).astype(np.uint8)


def _blend_brushes(path):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.brushes = list(src.brushes)
    keep, ids = [], []
    for brush in dst.brushes:
        if brush is None:
            continue
        if brush.use_paint_image:
            keep.append(brush)
            ids.append(brush)
        else:
            bpy.data.brushes.remove(brush)
    return keep, ids


def import_file(path):
    """Import one file into the library. Returns the brush names made."""
    ext = os.path.splitext(path)[1].lower()
    stem = os.path.splitext(os.path.basename(path))[0]
    made, ids = [], []
    if ext == ".abr":
        for name, w, h, data in abr.read(path):
            tip = np.frombuffer(data, np.uint8).reshape(h, w)
            brush, more = brush_from_tip(name, tip)
            made.append(brush)
            ids += more
    elif ext in IMAGE_TYPES:
        brush, more = brush_from_tip(stem, _image_tip(path))
        made.append(brush)
        ids += more
    elif ext == ".blend":
        made, ids = _blend_brushes(path)
    else:
        raise ValueError(f"Can't import {os.path.basename(path)} (not .abr, .blend or an image)")
    if not made:
        raise ValueError(f"No painting brushes in {os.path.basename(path)}")
    for brush in made:
        if brush.asset_data is None:
            brush.asset_mark()
    names = [b.name for b in made]
    folder = ensure_library().path
    out = os.path.join(folder, bpy.path.clean_name(stem) + ".blend")
    n = 2
    while os.path.exists(out):
        out = os.path.join(folder, f"{bpy.path.clean_name(stem)}_{n}.blend")
        n += 1
    bpy.data.libraries.write(out, set(ids), path_remap='NONE', fake_user=True, compress=True)
    bpy.data.batch_remove([i for i in ids if i is not None])   # the project doesn't keep them
    return names, out


def refresh_palette(context):
    """Re-read the brush libraries (the palette lists them once and keeps that).
    Needs the canvas's brush shelf region as context, even while it's hidden."""
    window = context.window or context.window_manager.windows[0]
    for area in window.screen.areas:
        shelf = next((r for r in area.regions if r.type == 'ASSET_SHELF'), None)
        if area.type == 'VIEW_3D' and shelf is not None:
            try:
                with context.temp_override(window=window, area=area, region=shelf):
                    bpy.ops.asset.library_refresh()
            except RuntimeError as err:
                print("Plastron: couldn't refresh the brush palette:", err)
            return


class PLASTRON_OT_brushes_import(bpy.types.Operator):
    """Add brushes to the palette: Photoshop .abr, images (brush tips) or Blender .blend"""
    bl_idname = "plastron.brushes_import"
    bl_label = "Import Brushes"

    filter_glob: bpy.props.StringProperty(
        default="*.abr;*.blend;" + ";".join("*" + e for e in IMAGE_TYPES), options={'HIDDEN'})
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN'})
    directory: bpy.props.StringProperty(subtype='DIR_PATH', options={'HIDDEN'})
    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        paths = [os.path.join(self.directory, f.name) for f in self.files if f.name] or \
            ([self.filepath] if self.filepath else [])
        total, problems = 0, []
        for path in paths:
            try:
                names, _out = import_file(path)
                total += len(names)
            except (OSError, ValueError, abr.AbrError, RuntimeError) as err:
                problems.append(f"{os.path.basename(path)}: {err}")
        refresh_palette(context)
        for problem in problems:
            self.report({'WARNING'}, problem)
        if total:
            self.report({'INFO'}, f"Added {total} brush{'es' if total != 1 else ''} to the palette "
                                  "(right-click the canvas)")
            return {'FINISHED'}
        return {'CANCELLED'}


classes = (PLASTRON_OT_brushes_import,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    try:
        ensure_library()
    except (AttributeError, OSError, RuntimeError) as err:
        print("Plastron: couldn't add the brush library:", err)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
