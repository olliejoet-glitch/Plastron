"""Panel versions (the brief's "when a render replaces a sketch, the old
sketches stay stacked underneath as versions; flip between versions or show
a sketch faintly over the render to compare").

Panel panel (tools area): New Version keeps the drawing as it is (stacked
under the panel) and carries on with a copy. The arrows flip which version
the panel shows (the others stay stacked). Compare shows the version just
before the one shown, faintly, over the canvas.
"""

import bpy

from ...config import review as cfg

COMPARE = "Canvas Compare"


class PLASTRON_PG_version(bpy.types.PropertyGroup):
    material: bpy.props.PointerProperty(type=bpy.types.Material)


def _panel(context):
    from .notes import panel_now
    return panel_now(context)


def new_version(scene, strip):
    """Keep the panel's drawing as a version; the panel goes on with a copy."""
    from ...layers import stack
    info = strip.plastron_panel
    kept = info.material
    v = info.versions.add()
    v.name = f"v{len(info.versions)}"
    v.material = kept
    info.material = stack.copy_material(kept, strip.name)
    info.version_shown = len(info.versions)        # the newest = the current drawing
    _changed(scene, strip)


def flip(scene, strip, step):
    """Show the next / previous version (they swap places with the current drawing)."""
    info = strip.plastron_panel
    count = len(info.versions) + 1
    target = (info.version_shown + step) % count
    if target == info.version_shown:
        return
    # versions + current in one list, ordered by version number; swap the shown one in.
    order = [v.material for v in info.versions]
    order.insert(info.version_shown, info.material)
    info.material = order.pop(target)
    for v, mat in zip(info.versions, order):
        v.material = mat
    info.version_shown = target
    _changed(scene, strip)


def _changed(scene, strip):
    from ..storyboard import canvas_sync, panel_cache
    canvas_sync.invalidate(scene)
    panel_cache.request(strip.plastron_panel.material)
    update_compare(scene)


def compare_material(strip):
    """The version shown faintly when comparing: the one just before."""
    info = strip.plastron_panel
    if not info.versions:
        return None
    order = [v.material for v in info.versions]
    order.insert(info.version_shown, info.material)
    return order[info.version_shown - 1] if info.version_shown > 0 else order[1]


def update_compare(scene=None, *_args):
    from ..storyboard import canvas_sync
    scene = scene or bpy.context.scene
    if scene is None or not hasattr(scene, "plastron_timeline"):
        return
    obj = canvas_sync._sheet_object(scene, COMPARE, False)
    strip = canvas_sync.panel_on_canvas(scene)
    on = bool(getattr(bpy.context.window_manager, "plastron_compare", False))
    mat = compare_material(strip) if (on and strip is not None) else None
    canvas = canvas_sync.canvas_object(scene)
    canvas_sync._set(obj, material=mat or canvas_sync.empty_material(), hidden=mat is None,
                     alpha=cfg.COMPARE_ALPHA)
    if mat is not None:
        obj.matrix_world = canvas.matrix_world
        obj.location.y -= canvas_sync.DEPTH_STEP / 2          # just in front of the canvas


class PLASTRON_OT_version_new(bpy.types.Operator):
    """Keep this drawing as a version (stacked under the panel) and carry on with a copy"""
    bl_idname = "plastron.version_new"
    bl_label = "New Version"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _panel(context) is not None

    def execute(self, context):
        new_version(context.scene, _panel(context))
        return {'FINISHED'}


class PLASTRON_OT_version_flip(bpy.types.Operator):
    """Show another version of this panel"""
    bl_idname = "plastron.version_flip"
    bl_label = "Flip Version"
    bl_options = {'REGISTER', 'UNDO'}
    step: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        strip = _panel(context)
        return strip is not None and len(strip.plastron_panel.versions) > 0

    def execute(self, context):
        flip(context.scene, _panel(context), self.step)
        return {'FINISHED'}


def draw_versions(layout, context):
    strip = _panel(context)
    if strip is None:
        return
    info = strip.plastron_panel
    row = layout.row(align=True)
    count = len(info.versions) + 1
    if count > 1:
        row.operator("plastron.version_flip", text="", icon='TRIA_LEFT').step = -1
        row.label(text=f"Version {info.version_shown + 1} of {count}")
        row.operator("plastron.version_flip", text="", icon='TRIA_RIGHT').step = 1
    row = layout.row(align=True)
    row.operator("plastron.version_new", icon='DUPLICATE')
    sub = row.row(align=True)
    sub.enabled = count > 1
    sub.prop(context.window_manager, "plastron_compare", text="Compare", toggle=True, icon='OVERLAY')


classes = (PLASTRON_PG_version, PLASTRON_OT_version_new, PLASTRON_OT_version_flip)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from ..storyboard.panels import PLASTRON_PG_panel as Panel
    Panel.versions = bpy.props.CollectionProperty(type=PLASTRON_PG_version)
    Panel.version_shown = bpy.props.IntProperty(default=0, min=0)
    bpy.types.WindowManager.plastron_compare = bpy.props.BoolProperty(
        name="Compare", description="Show the version before this one faintly over the canvas",
        update=lambda self, context: update_compare(context.scene))
    from ...layers import paint_target
    paint_target.listen(lambda _mat: update_compare())      # (the canvas changed panel)


def unregister():
    del bpy.types.WindowManager.plastron_compare
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
