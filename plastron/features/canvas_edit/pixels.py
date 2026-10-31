"""Reading and writing the canvas's pixels, undoably.

Blender can't undo pixels written from Python, but it does undo which image
a layer points at (CaraPainter's trick): every edit puts its result in a NEW
image on the layer, so Ctrl+Z goes back to the old one.
"""

import bpy
import numpy as np
from bpy_extras.view3d_utils import region_2d_to_location_3d

from ...layers import compiler, paint_target
from ..storyboard import canvas_sync


def array(img):
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def write(img, arr):
    img.pixels.foreach_set(np.ascontiguousarray(arr, np.float32).ravel())
    img.update()


def material():
    return paint_target.active_material()


def active_layer(mat=None):
    mat = mat or material()
    return mat.plastron_stack.active if mat is not None else None


def paint_layer(mat=None):
    layer = active_layer(mat)
    return layer if layer is not None and layer.layer_type == 'PAINT' and layer.paint_image else None


def size(mat=None):
    mat = mat or material()
    st = mat.plastron_stack
    return st.width, st.height


def replace_image(mat, layer_uid, arr):
    """Give the layer a new image holding arr (undoable). Returns it."""
    layer = mat.plastron_stack.by_uid(layer_uid)
    old = layer.paint_image
    h, w = arr.shape[:2]
    new = bpy.data.images.new(old.name if old else "Paint", w, h, alpha=True)
    new["plastron_owned"] = True        # packed when the project is saved
    write(new, arr)
    layer.paint_image = new
    compiler.push_layer(mat, layer)
    paint_target.sync(mat)
    return new


# --- screen <-> canvas pixels ---------------------------------------------------------------

def canvas_point(context, x, y):
    """Mouse position in the canvas region -> canvas pixel (x, y)."""
    loc = region_2d_to_location_3d(context.region, context.region_data, (x, y), (0.0, 0.0, 0.0))
    sw, sh = canvas_sync.sheet_size()
    w, h = size()
    return ((loc.x / sw + 0.5) * w, (loc.z / sh + 0.5) * h)


def world_point(px, py):
    """Canvas pixel -> point on the sheet (for drawing)."""
    sw, sh = canvas_sync.sheet_size()
    w, h = size()
    return ((px / w - 0.5) * sw, -0.02, (py / h - 0.5) * sh)


def region_point(context, px, py):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    p = location_3d_to_region_2d(context.region, context.region_data, world_point(px, py))
    return (p.x, p.y) if p is not None else (0.0, 0.0)


def undo_push(message):
    try:
        bpy.ops.ed.undo_push(message=message)
    except RuntimeError:
        pass
