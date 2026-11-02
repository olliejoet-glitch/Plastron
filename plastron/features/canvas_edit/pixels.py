"""Reading and writing the canvas's pixels, undoably.

Blender can't undo pixels written from Python, but it does undo which image
a layer points at (CaraPainter's trick): every edit puts its result in a NEW
image on the layer, so Ctrl+Z goes back to the old one.
"""

import bpy
import numpy as np
from mathutils import Vector
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

def _view(mat=None):
    """How the layer being painted is shown (features/motion: moved,
    parallax): painted px = canvas px * scale - shift."""
    mat = mat or material()
    if mat is None:
        return 1.0, 0.0, 0.0
    st = mat.plastron_stack
    return (st.view_scale or 1.0), st.view_shift[0], st.view_shift[1]


def _sheet_object():
    return bpy.data.objects.get(canvas_sync.CANVAS)


def canvas_point(context, x, y):
    """Mouse position in the canvas region -> pixel (x, y) of the layer being
    painted (less how far that layer is shown moved). Works on the canvas
    sheet itself, wherever it stands and however the view looks at it
    (flat, or through the 3D camera)."""
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
    from mathutils import geometry
    obj = _sheet_object()
    sw, sh = canvas_sync.sheet_size()            # the sheet mesh's own size
    w, h = size()
    a, dx, dy = _view()
    if obj is None:
        loc = region_2d_to_location_3d(context.region, context.region_data, (x, y), (0.0, 0.0, 0.0))
        lx, lz = loc.x, loc.z
    else:
        origin = region_2d_to_origin_3d(context.region, context.region_data, (x, y))
        direction = region_2d_to_vector_3d(context.region, context.region_data, (x, y))
        m = obj.matrix_world
        normal = (m.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
        hit = geometry.intersect_line_plane(origin, origin + direction, m.translation, normal)
        if hit is None:
            hit = m.translation
        local = m.inverted() @ hit
        lx, lz = local.x, local.z
    return ((lx / sw + 0.5) * w * a - dx, (lz / sh + 0.5) * h * a - dy)


def world_point(px, py):
    """Pixel of the layer being painted -> point on the canvas sheet (for drawing)."""
    sw, sh = canvas_sync.sheet_size()
    w, h = size()
    a, dx, dy = _view()
    local = Vector((((px + dx) / a / w - 0.5) * sw, 0.0, ((py + dy) / a / h - 0.5) * sh))
    obj = _sheet_object()
    if obj is None:
        local.y = -0.02
        return tuple(local)
    p = obj.matrix_world @ local
    toward = obj.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))
    return tuple(p + toward.normalized() * 0.02)         # just in front of the sheet


def region_point(context, px, py):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    p = location_3d_to_region_2d(context.region, context.region_data, world_point(px, py))
    return (p.x, p.y) if p is not None else (0.0, 0.0)


def undo_push(message):
    try:
        bpy.ops.ed.undo_push(message=message)
    except RuntimeError:
        pass
