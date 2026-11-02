"""Motion panel (tools area) for the panel being drawn on:

  Camera  Start / End (each opens a transform box on the canvas; C does too),
          easing graph, shake, presets, reset.
  Layer   the active layer or group: Start / End (a box to drag), easing
          graph, presets, reset.

Motion presets (ease in / out / in-out, overshoot, camera shake) are JSON in
plastron/presets/motion/: "curve" = the easing graph's points, "shake" =
[amount %, speed]. Camera presets use both; layer presets only the curve.
"""

import bpy

from ...core import presets
from ...widgets import dot_graph
from . import camera, edit, layer_motion

CAMERA_KIND = "camera_motion"
LAYER_KIND = "layer_motion"
FOLDER = "motion"


def _panel(context):
    return camera.shot(context.scene)


def _layer(context):
    strip = _panel(context)
    return strip.plastron_panel.material.plastron_stack.active if strip else None


# --- easing graphs: each panel / layer has its own ------------------------------------

def _users(graph_id):
    n = 0
    for scene in bpy.data.scenes:
        sed = getattr(scene, "sequence_editor", None)
        if sed is not None:
            n += sum(1 for s in sed.strips_all if s.plastron_motion.curve == graph_id)
    for mat in bpy.data.materials:
        if mat.plastron_stack.enabled:
            n += sum(1 for l in mat.plastron_stack.layers if l.move_curve == graph_id)
    return n


def own_graph(owner, attr, prefix):
    """owner.attr names a graph used by owner alone (made / copied if needed)."""
    gid = getattr(owner, attr)
    if gid and dot_graph.node(gid, create=False) is not None and _users(gid) == 1:
        return gid
    new = dot_graph.copy(gid, dot_graph.new_id(prefix)) if gid else dot_graph.new_id(prefix)
    dot_graph.node(new)
    setattr(owner, attr, new)
    return new


def _apply_curve(owner, attr, prefix, preset):
    if "curve" not in preset:
        return
    gid = own_graph(owner, attr, prefix)
    dot_graph.set_points(gid, preset["curve"], preset.get("handle", 'AUTO'))


def _apply_camera(context, preset):
    strip = _panel(context)
    if strip is None:
        return
    m = strip.plastron_motion
    _apply_curve(m, "curve", "cam", preset)
    if "shake" in preset:
        m.shake, m.shake_speed = preset["shake"]
    _redraw(context)


def _capture_camera(context):
    m = _panel(context).plastron_motion
    return {"curve": [list(p) for p in dot_graph.points(m.curve)],
            "handle": dot_graph.handles(m.curve), "shake": [m.shake, m.shake_speed]}


def _apply_layer(context, preset):
    layer = _layer(context)
    if layer is None:
        return
    _apply_curve(layer, "move_curve", "move", preset)
    layer_motion.refresh(context.scene)
    _redraw(context)


def _capture_layer(context):
    layer = _layer(context)
    return {"curve": [list(p) for p in dot_graph.points(layer.move_curve)],
            "handle": dot_graph.handles(layer.move_curve)}


def _redraw(context):
    for area in context.screen.areas if context.screen else []:
        if area.type in {'VIEW_3D', 'PROPERTIES'}:
            area.tag_redraw()


# --- operators ------------------------------------------------------------------------

class PLASTRON_OT_motion_reset(bpy.types.Operator):
    """Take the motion off: no move, straight easing, no shake"""
    bl_idname = "plastron.motion_reset"
    bl_label = "Reset"
    bl_options = {'REGISTER', 'UNDO'}
    target: bpy.props.EnumProperty(items=[('CAMERA', "Camera", ""), ('LAYER', "Layer", "")])

    @classmethod
    def poll(cls, context):
        return _panel(context) is not None and not edit.editing(context)

    def execute(self, context):
        strip = _panel(context)
        if self.target == 'CAMERA':
            m = strip.plastron_motion
            camera.set_state(m.start, camera.REST)
            camera.set_state(m.end, camera.REST)
            m.shake = 0.0
            if m.curve:
                dot_graph.remove(m.curve) if _users(m.curve) == 1 else None
                m.curve = ""
        else:
            layer = _layer(context)
            if layer is None:
                return {'CANCELLED'}
            layer.move_start = layer.move_end = (0.0, 0.0)
            if layer.move_curve:
                dot_graph.remove(layer.move_curve) if _users(layer.move_curve) == 1 else None
                layer.move_curve = ""
            layer_motion.refresh(context.scene)
        from ..storyboard import panel_cache
        panel_cache.request(strip.plastron_panel.material)
        _redraw(context)
        return {'FINISHED'}


class PLASTRON_OT_motion_curve(bpy.types.Operator):
    """Shape how it speeds up and slows down: a graph with points you add and drag"""
    bl_idname = "plastron.motion_curve"
    bl_label = "Easing"
    bl_options = {'REGISTER', 'UNDO'}
    target: bpy.props.EnumProperty(items=[('CAMERA', "Camera", ""), ('LAYER', "Layer", "")])

    @classmethod
    def poll(cls, context):
        return _panel(context) is not None

    def execute(self, context):
        if self.target == 'CAMERA':
            own_graph(_panel(context).plastron_motion, "curve", "cam")
        elif _layer(context) is not None:
            own_graph(_layer(context), "move_curve", "move")
        return {'FINISHED'}


class PLASTRON_MT_camera_motion_presets(bpy.types.Menu):
    bl_label = "Camera Presets"

    def draw(self, context):
        presets.draw_menu(self.layout, CAMERA_KIND)


class PLASTRON_MT_layer_motion_presets(bpy.types.Menu):
    bl_label = "Layer Motion Presets"

    def draw(self, context):
        presets.draw_menu(self.layout, LAYER_KIND)


# --- panels ---------------------------------------------------------------------------

class _Tools:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"


def _start_end(layout, target, context):
    """Start / End. Camera: moves the playhead there (the camera box in the
    canvas corner does the moving). Layer: opens the layer's box."""
    mode = edit.editing(context)
    row = layout.row(align=True)
    row.scale_y = 1.4
    for end, icon in (('START', 'REW'), ('END', 'FF')):
        if target == 'CAMERA':
            from . import camera_pad
            strip = _panel(context)
            on = strip is not None and camera_pad.current_end(context.scene, strip) == end
            row.operator("plastron.camera_end", text=end.title(), icon=icon, depress=on).end = end
        else:
            op = row.operator("plastron.motion_set", text=end.title(), icon=icon,
                              depress=(mode == f"{target} {end}"))
            op.target, op.end = target, end


def _easing(layout, owner, attr, target):
    gid = getattr(owner, attr)
    if gid and dot_graph.node(gid, create=False) is not None:
        dot_graph.draw(layout, gid)
    else:
        layout.operator("plastron.motion_curve", text="Easing: straight (edit)",
                        icon='IPO_EASE_IN_OUT').target = target


class PLASTRON_PT_motion(_Tools, bpy.types.Panel):
    bl_label = "Motion"
    bl_order = 15            # under the Layers panel, above Canvas

    def draw(self, context):
        layout = self.layout
        if _panel(context) is None:
            layout.label(text="Scrub onto a panel to move it", icon='INFO')
            return
        mode = edit.editing(context)
        if mode and mode not in ("DONE", "CANCEL"):
            box = layout.box()
            box.label(text="Drag the box on the canvas · Tab: other end", icon='HAND')
            row = box.row(align=True)
            row.operator("plastron.motion_done", text="Done", icon='CHECKMARK').keep = True
            row.operator("plastron.motion_done", text="Cancel", icon='X').keep = False


class PLASTRON_PT_motion_camera(_Tools, bpy.types.Panel):
    bl_label = "Camera"
    bl_parent_id = "PLASTRON_PT_motion"

    @classmethod
    def poll(cls, context):
        return _panel(context) is not None

    def draw_header_preset(self, context):
        self.layout.menu("PLASTRON_MT_camera_motion_presets", text="", icon='PRESET')

    def draw(self, context):
        layout = self.layout
        m = _panel(context).plastron_motion
        _start_end(layout, 'CAMERA', context)
        layout.label(text="Easing")
        _easing(layout, m, "curve", 'CAMERA')
        col = layout.column(align=True)
        col.prop(m, "shake")
        col.prop(m, "shake_speed")
        layout.operator("plastron.motion_reset", icon='LOOP_BACK').target = 'CAMERA'


class PLASTRON_PT_motion_layer(_Tools, bpy.types.Panel):
    bl_label = "Layer"
    bl_parent_id = "PLASTRON_PT_motion"

    @classmethod
    def poll(cls, context):
        return _layer(context) is not None

    def draw_header(self, context):
        self.layout.label(text=_layer(context).name)

    def draw_header_preset(self, context):
        self.layout.menu("PLASTRON_MT_layer_motion_presets", text="", icon='PRESET')

    def draw(self, context):
        layout = self.layout
        layer = _layer(context)
        _start_end(layout, 'LAYER', context)
        layout.label(text="Easing")
        _easing(layout, layer, "move_curve", 'LAYER')
        layout.operator("plastron.motion_reset", icon='LOOP_BACK').target = 'LAYER'


classes = (PLASTRON_OT_motion_reset, PLASTRON_OT_motion_curve,
           PLASTRON_MT_camera_motion_presets, PLASTRON_MT_layer_motion_presets,
           PLASTRON_PT_motion, PLASTRON_PT_motion_camera, PLASTRON_PT_motion_layer)


def register():
    presets.register_kind(CAMERA_KIND, _apply_camera, _capture_camera, folder=FOLDER)
    presets.register_kind(LAYER_KIND, _apply_layer, _capture_layer, folder=FOLDER,
                          accepts=lambda p: "curve" in p)
