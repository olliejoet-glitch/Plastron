"""Modal viewport drag gestures in the style of Blender's F key (ARCHITECTURE §10).

Drag to change, LMB / Enter / Space to confirm (one undo step), RMB / Esc to cancel and restore.
Shift = fine, Ctrl = snap.
"""
import bpy
from ..props import LIGHT_TYPES
from bpy.props import BoolProperty
from mathutils import Vector

from .layers import add_layer, get_stack, remove_layer
from .view import in_painterly


class _Gesture:
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING', 'GRAB_CURSOR'}
    PX = 400.0  # pixels for one full unit of change

    @classmethod
    def poll(cls, context):
        return in_painterly(context) and get_stack(context)[1] is not None \
            and context.area is not None and context.area.type == 'VIEW_3D'

    # subclasses: begin(context) -> bool, apply(context, dx, dy, snap), restore(context), text()
    def invoke(self, context, event):
        if not self.begin(context):
            return {'CANCELLED'}
        self.start = Vector((event.mouse_x, event.mouse_y))
        self.acc = Vector((0.0, 0.0))
        self.last = self.start.copy()
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _header(self, context):
        context.area.header_text_set(self.text() + "   ·   LMB confirm · RMB cancel · Shift fine · Ctrl snap")

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            cur = Vector((event.mouse_x, event.mouse_y))
            d = cur - self.last
            self.last = cur
            self.acc += d * (0.1 if event.shift else 1.0)
            self.apply(context, self.acc.x / self.PX, self.acc.y / self.PX, event.ctrl)
            self._header(context)
        elif event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            context.area.header_text_set(None)
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self.restore(context)
            context.area.header_text_set(None)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


def _snap(v, step, on):
    return round(v / step) * step if on else v


class PL_OT_gesture_opacity(_Gesture, bpy.types.Operator):
    bl_idname = "pl.gesture_opacity"
    bl_label = "Drag Layer Opacity"
    bl_description = "Drag left/right to change the active layer's opacity (A)"

    def begin(self, context):
        self.mat, stack = get_stack(context)
        self.layer_uid = stack.active.uid if stack.active else None
        if self.layer_uid is None:
            return False
        self.v0 = stack.active.opacity
        return True

    def _layer(self):
        return self.mat.pl_stack.by_uid(self.layer_uid)

    def apply(self, context, dx, dy, snap):
        self._layer().opacity = min(1.0, max(0.0, _snap(self.v0 + dx, 0.1, snap)))

    def restore(self, context):
        self._layer().opacity = self.v0

    def text(self):
        return f"Opacity {self._layer().opacity * 100:.0f}%"


class PL_OT_gesture_huesat(_Gesture, bpy.types.Operator):
    bl_idname = "pl.gesture_huesat"
    bl_label = "Drag Hue/Saturation"
    bl_description = ("S: add a Hue/Saturation layer and drag (horizontal = hue, vertical = "
                      "saturation). Shift+S: drag the active Hue/Saturation layer instead")
    new_layer: BoolProperty(default=True)

    def begin(self, context):
        self.mat, stack = get_stack(context)
        act = stack.active
        if self.new_layer:
            layer = add_layer(self.mat, "ADJUST", adjust_kind="HUE_SAT", name="Hue/Saturation")
        elif act is not None and act.layer_type == "ADJUST" and act.adjust_kind == "HUE_SAT":
            layer = act
        else:
            self.report({'WARNING'}, "Active layer is not a Hue/Saturation layer")
            return False
        self.layer_uid = layer.uid
        self.h0, self.s0 = layer.hs_hue, layer.hs_saturation
        return True

    def _layer(self):
        return self.mat.pl_stack.by_uid(self.layer_uid)

    def apply(self, context, dx, dy, snap):
        l = self._layer()
        h = (self.h0 + dx * 180.0 + 180.0) % 360.0 - 180.0
        l.hs_hue = _snap(h, 15.0, snap)
        l.hs_saturation = max(-100.0, min(100.0, _snap(self.s0 + dy * 100.0, 10.0, snap)))

    def restore(self, context):
        if self.new_layer:
            remove_layer(self.mat, self._layer())
        else:
            l = self._layer()
            l.hs_hue, l.hs_saturation = self.h0, self.s0

    def text(self):
        l = self._layer()
        return f"Hue {l.hs_hue:+.0f}°   Saturation {l.hs_saturation:+.0f}"


class PL_OT_gesture_form(_Gesture, bpy.types.Operator):
    bl_idname = "pl.gesture_form"
    bl_label = "Drag Light Form Size"
    bl_description = "F: drag the active light layer's form size (left = every scale, right = broad planes)"

    def begin(self, context):
        self.mat, stack = get_stack(context)
        act = stack.active
        if act is None or act.layer_type not in LIGHT_TYPES:
            self.report({'INFO'}, "Select a light layer for F")
            return False
        self.layer_uid = act.uid
        self.v0 = act.form_size
        return True

    def _layer(self):
        return self.mat.pl_stack.by_uid(self.layer_uid)

    def apply(self, context, dx, dy, snap):
        self._layer().form_size = min(1.0, max(0.0, _snap(self.v0 + dx, 0.05, snap)))

    def restore(self, context):
        self._layer().form_size = self.v0

    def text(self):
        return f"Form size {self._layer().form_size:.2f}"


class PL_OT_gesture_threshold(_Gesture, bpy.types.Operator):
    bl_idname = "pl.gesture_threshold"
    bl_label = "Drag Light Threshold"
    bl_description = ("Shift+F: drag the active light / shadow layer's threshold (shadow layers: the "
                      "size of the shadow), vertical = softness")

    def begin(self, context):
        self.mat, stack = get_stack(context)
        act = stack.active
        if act is None or act.layer_type not in LIGHT_TYPES:
            self.report({'INFO'}, "Select a light or shadow layer for Shift+F")
            return False
        self.layer_uid = act.uid
        self.v0 = (act.light_threshold, act.light_softness, act.light_size)
        return True

    def _layer(self):
        return self.mat.pl_stack.by_uid(self.layer_uid)

    def apply(self, context, dx, dy, snap):
        l = self._layer()
        l.light_size = min(1.0, max(0.0, _snap(self.v0[2] + dx * 0.5, 0.025, snap)))
        l.light_softness = min(1.0, max(0.0, self.v0[1] + dy * 0.5))

    def restore(self, context):
        l = self._layer()
        l.light_threshold, l.light_softness = self.v0[:2]

    def text(self):
        l = self._layer()
        what = "Shadow size" if l.light_polarity == "SHADOW" else "Size"
        return f"{what} {l.light_size:.3f}   Softness {l.light_softness:.2f}"


classes = (PL_OT_gesture_opacity, PL_OT_gesture_huesat, PL_OT_gesture_form, PL_OT_gesture_threshold)
