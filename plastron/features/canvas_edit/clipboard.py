"""Copy / cut / paste pixels between panels, and flips.

Ctrl+C copies the selected pixels of the active layer (the whole layer with
nothing selected); Ctrl+X cuts them. Ctrl+V pastes in place as a new layer
on the panel being drawn on, so copying between panels keeps the drawing
where it was in the frame.

Ctrl+Alt+F flips the selected pixels left-right (in place); with nothing
selected it flips the active layer (or every paint layer in the active
group). Ctrl+Alt+Shift+F flips upside down.
"""

import bpy
import numpy as np

from ...layers import stack as stack_ops
from . import pixels, selection, shapes

_clip = {"pixels": None}       # full-canvas RGBA (transparent outside what was copied)


def copied():
    return _clip["pixels"]


def _selected_pixels(context):
    mat = pixels.material()
    layer = pixels.paint_layer(mat)
    if layer is None:
        return None, None, None
    a = pixels.array(layer.paint_image).copy()
    m = selection.mask(context)
    if m is not None:
        a[..., 3] *= m
    return mat, layer, (a, m)


class _CanvasOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_TEXTURE' and pixels.material() is not None


class PLASTRON_OT_pixels_copy(_CanvasOp, bpy.types.Operator):
    """Copy the selected pixels (or the whole layer) of the active layer (Ctrl+C)"""
    bl_idname = "plastron.pixels_copy"
    bl_label = "Copy"
    bl_options = {'REGISTER'}

    cut: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        mat, layer, got = _selected_pixels(context)
        if layer is None:
            self.report({'INFO'}, "Pick a paint layer to copy from")
            return {'CANCELLED'}
        a, m = got
        if not (a[..., 3] > 0).any():
            self.report({'INFO'}, "Nothing to copy there")
            return {'CANCELLED'}
        _clip["pixels"] = a
        if self.cut:
            rest = pixels.array(layer.paint_image).copy()
            rest[..., 3] *= (1.0 - m) if m is not None else 0.0
            pixels.replace_image(mat, layer.uid, rest)
            pixels.undo_push("Cut")
        return {'FINISHED'}


class PLASTRON_OT_pixels_paste(_CanvasOp, bpy.types.Operator):
    """Paste in place, as a new layer (Ctrl+V)"""
    bl_idname = "plastron.pixels_paste"
    bl_label = "Paste"

    def execute(self, context):
        data = _clip["pixels"]
        mat = pixels.material()
        if data is None:
            self.report({'INFO'}, "Nothing copied yet")
            return {'CANCELLED'}
        w, h = pixels.size(mat)
        if data.shape[:2] != (h, w):            # a different canvas size: centre it
            out = np.zeros((h, w, 4), np.float32)
            dh, dw = data.shape[:2]
            ys, xs = max(0, (h - dh) // 2), max(0, (w - dw) // 2)
            sy, sx = max(0, (dh - h) // 2), max(0, (dw - w) // 2)
            ch, cw = min(h, dh), min(w, dw)
            out[ys:ys + ch, xs:xs + cw] = data[sy:sy + ch, sx:sx + cw]
            data = out
        uid = stack_ops.add_layer(mat, 'PAINT', name="Pasted")
        pixels.replace_image(mat, uid, data)
        selection.set_mask(context, (data[..., 3] > 0).astype(np.float32))
        return {'FINISHED'}


def _flip(arr, vertical):
    return arr[::-1] if vertical else arr[:, ::-1]


class PLASTRON_OT_pixels_flip(_CanvasOp, bpy.types.Operator):
    """Flip the selected pixels, or the active layer / group (Ctrl+Alt+F; Shift: upside down)"""
    bl_idname = "plastron.layer_flip"
    bl_label = "Flip"

    vertical: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        mat = pixels.material()
        st = mat.plastron_stack
        act = st.active
        m = selection.mask(context)
        if m is not None:
            layer = pixels.paint_layer(mat)
            if layer is None:
                self.report({'INFO'}, "Pick a paint layer to flip")
                return {'CANCELLED'}
            x0, y0, x1, y1 = shapes.bbox(m)
            a = pixels.array(layer.paint_image).copy()
            box = a[y0:y1, x0:x1].copy()
            box_m = m[y0:y1, x0:x1]
            flipped, flipped_m = _flip(box, self.vertical), _flip(box_m, self.vertical)
            keep = a[y0:y1, x0:x1].copy()
            keep[..., 3] *= 1.0 - box_m
            sel_part = flipped.copy()
            sel_part[..., 3] *= flipped_m
            pre = sel_part.copy()
            pre[..., :3] *= pre[..., 3:4]
            a[y0:y1, x0:x1] = shapes.over(keep, pre)
            pixels.replace_image(mat, layer.uid, a)
            new_m = m.copy()
            new_m[y0:y1, x0:x1] = flipped_m
            selection.set_mask(context, new_m)
            return {'FINISHED'}
        if act is None:
            return {'CANCELLED'}
        uids = [act.uid] if act.layer_type != 'GROUP' else stack_ops.subtree_uids(st, act)
        done = 0
        for uid in uids:
            layer = st.by_uid(uid)
            if layer is not None and layer.layer_type == 'PAINT' and layer.paint_image is not None:
                pixels.replace_image(mat, uid, _flip(pixels.array(layer.paint_image), self.vertical).copy())
                done += 1
        if not done:
            self.report({'INFO'}, "Nothing to flip on this layer")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (PLASTRON_OT_pixels_copy, PLASTRON_OT_pixels_paste, PLASTRON_OT_pixels_flip)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
