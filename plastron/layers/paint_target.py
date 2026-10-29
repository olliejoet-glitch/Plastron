"""Aims Blender's Texture Paint at the active layer's image (single-image mode),
as CaraPainter does. Locked, hidden or non-paint layers paint nothing.

The stack being painted is the active object's material (read live, so it
survives undo and file loads)."""

import bpy


def active_material(context=None):
    """The layer-stack material on the active object, or None."""
    view_layer = getattr(context or bpy.context, "view_layer", None)
    obj = view_layer.objects.active if view_layer else None
    mat = obj.active_material if obj else None
    return mat if mat is not None and mat.plastron_stack.enabled else None


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
    """Point painting at the active layer of the material on the canvas.
    mat: only re-aim if that material is the one on the canvas."""
    current = active_material()
    if mat is not None and mat != current:
        return
    scene = scene or bpy.context.scene
    if scene is None:
        return
    ip = scene.tool_settings.image_paint
    if ip.mode != 'IMAGE':
        ip.mode = 'IMAGE'
    img = target_image(current)
    if ip.canvas != img:
        ip.canvas = img
