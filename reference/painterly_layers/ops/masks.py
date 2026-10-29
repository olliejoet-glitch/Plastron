"""Layer masks: add/remove, painting the mask (T), fill/invert, View Mask, analysis, D gesture."""
import bpy
import numpy as np
from bpy.props import EnumProperty

from .. import props
from ..analysis import cache
from ..compiler import compile_stack
from ..ui import hud
from .gestures import _Gesture, _snap
from .layers import get_stack, sync_paint_target
from .view import in_painterly


def _layer(context):
    mat, stack = get_stack(context)
    return mat, stack, (stack.active if stack else None)


def add_mask(mat, layer, source, **kw):
    """Add a mask element to the layer; returns it."""
    uid = layer.uid
    with props.suspended():
        m = layer.masks.add()
        m.ensure_uid()
        m.source = source
        m.name = "Mask" if source == "PAINT" else next(i[1] for i in props.MASK_SOURCES if i[0] == source)
        if source == "CURVATURE":
            m.threshold, m.softness, m.detail = 0.3, 0.15, 0.0
        elif source == "SHADOW":
            m.threshold, m.softness = 0.5, 0.25
        elif source == "TERMINATOR":
            m.threshold, m.softness = 0.5, 0.04
        elif source == "HEIGHT":
            m.threshold, m.softness = 0.5, 0.03
        elif source == "NOISE":
            m.threshold, m.softness = 0.5, 0.15
        for k, v in kw.items():
            setattr(m, k, v)
        if source == "PAINT" and m.image is None:
            lay = mat.pl_stack.by_uid(uid)
            m.image = new_grey_image(f"{mat.name} · {lay.name} · mask", mat.pl_stack.resolution, 1.0)
        lay = mat.pl_stack.by_uid(uid)
        lay.active_mask_index = len(lay.masks) - 1
    if source in ("DEPTH", "CURVATURE", "HEIGHT") and mat.pl_stack.height_image is None:
        cache.start(mat)
    compile_stack(mat)
    lay = mat.pl_stack.by_uid(uid)
    return lay.masks[lay.active_mask_index]


def new_grey_image(name, res, value):
    """Greyscale mask/correction image. sRGB, so the grey you pick is the value you get
    (Photoshop masks work in display grey)."""
    img = bpy.data.images.new(name, res, res, alpha=False)
    img.pixels.foreach_set(np.full(res * res * 4, value, np.float32))
    img.update()
    img["pl_owned"] = True
    img.pack()
    return img


def new_correction_image(name, res):
    return new_grey_image(name, res, 0.5)  # mid-grey = no change


def mask_target_image(layer):
    """The image T paints for the active mask (depth: its correction)."""
    m = layer.active_mask
    if m is None:
        return None
    return m.correction if m.source == "DEPTH" else m.image


class _MaskOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _layer(context)[2] is not None


class PL_OT_mask_add(_MaskOp, bpy.types.Operator):
    bl_idname = "pl.mask_add"
    bl_label = "Add Mask"
    bl_description = "Add a mask to the active layer"
    source: EnumProperty(items=props.MASK_SOURCES, default="DEPTH")

    def execute(self, context):
        mat, stack, layer = _layer(context)
        add_mask(mat, layer, self.source)
        return {'FINISHED'}


class PL_OT_mask_remove(_MaskOp, bpy.types.Operator):
    bl_idname = "pl.mask_remove"
    bl_label = "Remove Mask"
    bl_description = "Remove the active mask"

    def execute(self, context):
        mat, stack, layer = _layer(context)
        if layer.active_mask is None:
            return {'CANCELLED'}
        with props.suspended():
            layer.masks.remove(layer.active_mask_index)
            layer.active_mask_index = max(0, min(layer.active_mask_index, len(layer.masks) - 1))
            layer.paint_target = "LAYER"
        compile_stack(mat)
        sync_paint_target(context, mat)
        return {'FINISHED'}


def _brush_black_white(context):
    """Painting a mask: white on the brush, black as the secondary colour (X swaps)."""
    ip = context.tool_settings.image_paint
    ups = ip.unified_paint_settings
    ups.color, ups.secondary_color = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    if ip.brush is not None:
        ip.brush.color, ip.brush.secondary_color = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)


def toggle_mask_painting(context, mat, layer):
    """T: paint the active mask <-> the layer. A layer without masks gets a white paint mask;
    a depth mask gets its correction image the first time."""
    uid = layer.uid
    if layer.paint_target == "MASK":
        mat.pl_stack.by_uid(uid).paint_target = "LAYER"
        return "LAYER"
    if not len(layer.masks):
        add_mask(mat, layer, "PAINT")
    layer = mat.pl_stack.by_uid(uid)
    m = layer.active_mask
    if m.source == "DEPTH" and m.correction is None:
        m.correction = new_correction_image(f"{mat.name} · {layer.name} · depth correction",
                                            mat.pl_stack.resolution)
    elif m.source in ("PAINT", "IMAGE") and m.image is None:
        m.image = new_grey_image(f"{mat.name} · {layer.name} · mask", mat.pl_stack.resolution, 1.0)
    elif m.source in ("CURVATURE", "HEIGHT", "NOISE"):
        return None  # nothing to paint on these
    layer = mat.pl_stack.by_uid(uid)
    _brush_black_white(context)
    layer.paint_target = "MASK"
    return "MASK"


class PL_OT_mask_paint(_MaskOp, bpy.types.Operator):
    bl_idname = "pl.mask_paint"
    bl_label = "Paint Mask"
    bl_description = ("T: paint the active mask directly (white shows the layer, black hides it; on a "
                      "depth mask: push depth up/down). Again: back to the layer")

    def execute(self, context):
        mat, stack, layer = _layer(context)
        if toggle_mask_painting(context, mat, layer) is None:
            self.report({'INFO'}, "Curvature masks can't be painted: add a Paint mask to edit by hand")
            return {'CANCELLED'}
        return {'FINISHED'}


class PL_OT_paint_target_toggle(bpy.types.Operator):
    bl_idname = "pl.paint_target_toggle"
    bl_label = "Toggle Mask Painting"
    bl_description = "T: paint the layer's mask (adds one if needed) / back to the layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return in_painterly(context) and context.mode == 'PAINT_TEXTURE' and _layer(context)[2] is not None

    def execute(self, context):
        return bpy.ops.pl.mask_paint()


class PL_OT_mask_edit(_MaskOp, bpy.types.Operator):
    bl_idname = "pl.mask_edit"
    bl_label = "Edit Mask"
    bl_description = "Fill or invert the active mask (inside the selection, if there is one)"
    action: EnumProperty(items=[("WHITE", "Fill White", "Show the layer"),
                                ("BLACK", "Fill Black", "Hide the layer"),
                                ("INVERT", "Invert", "Swap shown and hidden"),
                                ("VALUE", "Fill Grey", "Fill with a grey value")])
    value: bpy.props.FloatProperty(default=0.5, min=0, max=1)

    def execute(self, context):
        from .select import image_array, resize_nearest, selection_array, write_image
        mat, stack, layer = _layer(context)
        img = mask_target_image(layer)
        if img is None:
            self.report({'WARNING'}, "The active mask has nothing to edit (Paint / Image masks, or a "
                                     "depth mask's correction)")
            return {'CANCELLED'}
        a = image_array(img).copy()
        if self.action == "WHITE":
            new = np.ones_like(a)
        elif self.action == "BLACK":
            new = np.zeros_like(a)
        elif self.action == "VALUE":
            new = np.full_like(a, self.value)
        else:
            new = 1.0 - a
        new[..., 3] = 1.0
        sel = selection_array(context)
        if sel is not None:  # only inside the selection
            k = resize_nearest(sel, a.shape[0])[..., None]
            new = a * (1 - k) + new * k
        # a new image so Ctrl+Z works (pointer changes are undoable, pixel writes aren't)
        out = bpy.data.images.new(img.name, img.size[0], img.size[1], alpha=False)
        out.colorspace_settings.name = img.colorspace_settings.name
        write_image(out, new)
        out["pl_owned"] = True
        m = layer.active_mask
        if m.source == "DEPTH":
            m.correction = out
        else:
            m.image = out
        sync_paint_target(context, mat)
        return {'FINISHED'}


class PL_OT_mask_view(_MaskOp, bpy.types.Operator):
    bl_idname = "pl.mask_view"
    bl_label = "View Mask"
    bl_description = "Show the active layer's mask in greyscale on the model (click again to return)"

    def execute(self, context):
        from .view import base_view_active, set_base_view
        mat, stack, layer = _layer(context)
        stack.mask_view = not stack.mask_view
        sc = context.scene
        if stack.mask_view:  # show it flat and unlit, like Photoshop's Alt-click on a mask
            sc["pl_mask_view_prev_flat"] = base_view_active(sc)
            set_base_view(context, True)
        else:
            set_base_view(context, bool(sc.get("pl_mask_view_prev_flat", False)))
        return {'FINISHED'}


class PL_OT_analyse(bpy.types.Operator):
    bl_idname = "pl.analyse"
    bl_label = "Analyse Normal Map"
    bl_description = ("Work out height and curvature from the normal map (runs in the background; "
                      "redone automatically when the normal map changes)")

    @classmethod
    def poll(cls, context):
        st = get_stack(context)[1]
        return st is not None and st.normal_image is not None

    def execute(self, context):
        mat, stack = get_stack(context)
        job = cache.JOBS.get(stack.normal_image.name)
        if job is not None and job.get("error"):
            del cache.JOBS[stack.normal_image.name]  # retry after an error
        if not cache.start(mat, force=True):
            self.report({'INFO'}, "Analysis already running or up to date")
        return {'FINISHED'}


class PL_OT_gesture_mask(_Gesture, bpy.types.Operator):
    bl_idname = "pl.gesture_mask"
    bl_label = "Drag Mask"
    bl_description = ("D: drag the active layer's mask (adds a depth mask if it has none): "
                      "horizontal = threshold, vertical = softness, Ctrl = detail size")

    def begin(self, context):
        self.mat, stack = get_stack(context)
        layer = stack.active
        if layer is None:
            return False
        self.layer_uid = layer.uid
        self.added = False
        if layer.active_mask is None or layer.active_mask.source == "PAINT":
            idx = next((i for i, m in enumerate(layer.masks) if m.source != "PAINT"), None)
            if idx is None:
                add_mask(self.mat, layer, "DEPTH")
                self.added = True
            else:
                layer.active_mask_index = idx
            layer = stack.by_uid(self.layer_uid)
        m = layer.active_mask
        self.v0 = (m.threshold, m.softness, m.detail, m.noise_scale)
        hud.set_label("Mask")
        return True

    def _mask(self):
        return self.mat.pl_stack.by_uid(self.layer_uid).active_mask

    def apply(self, context, dx, dy, snap):
        m = self._mask()
        t0, s0, d0, n0 = self.v0
        if self._ctrl and m.source == "NOISE":
            m.noise_scale = min(400.0, max(0.1, n0 * 4.0 ** dx))
        elif self._ctrl:
            m.detail = min(1.0, max(0.0, _snap(d0 + dx, 0.05, False)))
        else:
            m.threshold = min(1.0, max(0.0, _snap(t0 + dx, 0.05, snap)))
            m.softness = min(0.5, max(0.0, s0 + dy * 0.5))

    def modal(self, context, event):
        self._ctrl = event.ctrl
        hud.set_mouse(event)
        res = super().modal(context, event)
        if res != {'RUNNING_MODAL'}:
            hud.set_label(None)
        return res

    def invoke(self, context, event):
        self._ctrl = False
        return super().invoke(context, event)

    def restore(self, context):
        if self.added:
            layer = self.mat.pl_stack.by_uid(self.layer_uid)
            with props.suspended():
                layer.masks.remove(layer.active_mask_index)
                layer.active_mask_index = 0
            compile_stack(self.mat)
            return
        m = self._mask()
        m.threshold, m.softness, m.detail = self.v0

    def text(self):
        m = self._mask()
        return f"Threshold {m.threshold:.2f}   Softness {m.softness:.2f}   Detail size {m.detail:.2f} (Ctrl)"


classes = (PL_OT_mask_add, PL_OT_mask_remove, PL_OT_mask_paint, PL_OT_paint_target_toggle,
           PL_OT_mask_edit, PL_OT_mask_view, PL_OT_analyse, PL_OT_gesture_mask)
