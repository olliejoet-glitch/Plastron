"""Canvas (paper) colour: swatches + colour picker in the tools area.

The canvas shows panels in Material Preview over the project's world, so
the paper colour is the world colour (and the 3D-view background colour,
for any other shading). Changing it costs nothing at draw time. The choice
is remembered via core.user_settings. Swatches: CANVAS_PRESETS in
config/theme.py.
"""

import bpy
from mathutils import Color

from ...config import theme as theme_cfg
from ...core import handlers, user_settings
from ...core.theme import _color

SETTING = "canvas_color"
WORLD = "Paper"


def current():
    saved = user_settings.get(SETTING)
    return tuple(saved) if saved else tuple(_color("paper")[:3])


def _world_color(scene, rgb):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.get(WORLD) or bpy.data.worlds.new(WORLD)
        scene.world = world
    linear = Color(rgb).from_srgb_to_scene_linear()
    if world.node_tree is None:
        world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg is None:
        bg = world.node_tree.nodes.new('ShaderNodeBackground')
        out = next((n for n in world.node_tree.nodes if n.type == 'OUTPUT_WORLD'), None) or \
            world.node_tree.nodes.new('ShaderNodeOutputWorld')
        world.node_tree.links.new(bg.outputs[0], out.inputs["Surface"])
    if any(abs(a - b) > 1e-5 for a, b in zip(bg.inputs["Color"].default_value[:3], linear)):
        bg.inputs["Color"].default_value = (*linear, 1.0)
        bg.inputs["Strength"].default_value = 1.0
        world.color = linear


def apply(rgb):
    gradients = bpy.context.preferences.themes[0].view_3d.space.gradients
    gradients.high_gradient = rgb
    gradients.gradient = rgb
    if isinstance(bpy.data, bpy.types.BlendData):      # (not while add-ons register)
        for scene in bpy.data.scenes:
            if hasattr(scene, "plastron_timeline"):
                _world_color(scene, rgb)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _get(_self):
    return current()


def _set(_self, value):
    rgb = tuple(value)
    user_settings.set(SETTING, list(rgb))
    apply(rgb)
    from . import panel_cache, panels       # panel images are painted over the paper
    for scene in bpy.data.scenes:
        if hasattr(scene, "plastron_timeline") and scene.sequence_editor:
            for strip in panels.all_panels(scene):
                panel_cache.request(strip.plastron_panel.material)


class PLASTRON_OT_canvas_color(bpy.types.Operator):
    """Set the canvas colour"""
    bl_idname = "plastron.canvas_color"
    bl_label = "Canvas Colour"
    bl_options = {'INTERNAL'}

    color: bpy.props.StringProperty(name="Colour (#rrggbb)")

    def execute(self, context):
        context.window_manager.plastron_canvas_color = _color(self.color)[:3]
        return {'FINISHED'}


class PLASTRON_PT_canvas(bpy.types.Panel):
    # Shown in the tools area (see tools.py for why it's VIEW_3D / "Tool").
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Canvas"
    bl_order = 20

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        for name, hex_color in theme_cfg.CANVAS_PRESETS:
            row.operator("plastron.canvas_color", text=name).color = hex_color
        layout.prop(context.window_manager, "plastron_canvas_color", text="")


classes = (PLASTRON_OT_canvas_color, PLASTRON_PT_canvas)


def register():
    bpy.types.WindowManager.plastron_canvas_color = bpy.props.FloatVectorProperty(
        name="Canvas Colour", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0,
        get=_get, set=_set)
    for cls in classes:
        bpy.utils.register_class(cls)
    apply(current())
    handlers.on_load(lambda _scene: apply(current()))


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.plastron_canvas_color
