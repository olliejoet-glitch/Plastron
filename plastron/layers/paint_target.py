"""Aims Blender's Texture Paint at the active layer's image (single-image mode),
as CaraPainter does. Locked, hidden or non-paint layers paint nothing."""

import bpy

_current = {"material": None}


def active_material():
    return _current["material"]


def target_image(mat):
    """The image a brush stroke should go into, or None."""
    if mat is None or not mat.plastron_stack.enabled:
        return None
    layer = mat.plastron_stack.active
    if layer is None or layer.locked:
        return None
    if layer.paint_target == "MASK" and layer.active_mask is not None:
        return layer.active_mask.image
    return layer.paint_image if layer.layer_type == "PAINT" else None


def sync(mat=None, scene=None):
    """Point painting at mat's active layer (mat None = the current canvas material)."""
    if mat is not None:
        _current["material"] = mat
    mat = _current["material"]
    scene = scene or bpy.context.scene
    if scene is None:
        return
    ip = scene.tool_settings.image_paint
    if ip.mode != 'IMAGE':
        ip.mode = 'IMAGE'
    img = target_image(mat)
    if ip.canvas != img:
        ip.canvas = img
