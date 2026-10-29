"""Per-scene key light (ARCHITECTURE §7.1).

Simple drivers (Transform Channel / Single Property, no Python expressions -> renders on SheepIt
without the add-on) copy the key light into scene custom properties that the shader reads with
Attribute nodes (View Layer):
  pl_key_rot (world rotation), pl_key_loc (world position), pl_key_energy (strength / power),
  pl_key_type (0 = sun, 1 = point / spot / area), pl_cam_loc (scene camera, for baked highlights).
"""
import bpy
from ..props import LIGHT_TYPES
from bpy.props import EnumProperty

PROP = "pl_key_rot"
VEC_PROPS = ("pl_key_rot", "pl_key_loc", "pl_cam_loc")


def _transform_drivers(scene, prop, ob, kind):
    path = f'["{prop}"]'
    for i in range(3):
        drv = scene.driver_add(path, i).driver
        drv.type = 'AVERAGE'
        var = drv.variables.new()
        var.type = 'TRANSFORMS'
        t = var.targets[0]
        t.id = ob
        t.transform_type = kind + "_" + "XYZ"[i]
        t.transform_space = 'WORLD_SPACE'
        if kind == "ROT":
            t.rotation_mode = 'XYZ'


def _clear(scene, prop):
    try:
        scene.driver_remove(f'["{prop}"]')
    except TypeError:
        pass


def setup_key_light_drivers(scene):
    for prop in VEC_PROPS:
        if prop not in scene:
            scene[prop] = [0.0, 0.0, 0.0]
        _clear(scene, prop)
    for prop in ("pl_key_energy", "pl_key_type"):
        if prop not in scene:
            scene[prop] = 0.0
        _clear(scene, prop)
    if scene.camera is not None:
        _transform_drivers(scene, "pl_cam_loc", scene.camera, "LOC")
    light = scene.pl_key_light
    if light is None:
        scene[PROP] = [0.0, 0.0, 0.0]
        scene["pl_key_energy"] = 0.0
        return
    _transform_drivers(scene, "pl_key_rot", light, "ROT")
    _transform_drivers(scene, "pl_key_loc", light, "LOC")
    drv = scene.driver_add('["pl_key_energy"]').driver
    drv.type = 'AVERAGE'
    var = drv.variables.new()
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'LIGHT'
    var.targets[0].id = light.data
    var.targets[0].data_path = "energy"
    scene["pl_key_type"] = 0.0 if light.data.type == 'SUN' else 1.0


def auto_detect(scene):
    """Use the only sun in the scene, if there is exactly one."""
    if scene.pl_key_light is not None:
        return scene.pl_key_light
    suns = [o for o in scene.objects if o.type == 'LIGHT' and o.data.type == 'SUN']
    if len(suns) == 1:
        scene.pl_key_light = suns[0]  # update callback creates the drivers
        return suns[0]
    return None


def _light_items(self, context):
    return [(o.name, o.name, f"{o.data.type.title()} light") for o in context.scene.objects if o.type == 'LIGHT'] \
        or [("", "(no lights)", "")]


class PL_OT_key_light_choose(bpy.types.Operator):
    bl_idname = "pl.key_light_choose"
    bl_label = "Choose Key Light"
    bl_description = "Pick which light is this scene's key light (light layers and shadow masks follow it)"
    bl_options = {'REGISTER', 'UNDO'}
    light: EnumProperty(name="Key Light", items=_light_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        ob = context.scene.objects.get(self.light)
        if ob is None:
            return {'CANCELLED'}
        context.scene.pl_key_light = ob
        return {'FINISHED'}


class PL_OT_key_light_detect(bpy.types.Operator):
    bl_idname = "pl.key_light_detect"
    bl_label = "Detect Key Light"
    bl_description = "Use the scene's only sun lamp as the key light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if auto_detect(context.scene) is None:
            return bpy.ops.pl.key_light_choose('INVOKE_DEFAULT')
        return {'FINISHED'}


def _lights_on(scene, viewport):
    """Lights that actually light the scene (in the viewport, or in renders)."""
    out = []
    for o in scene.objects:
        if o.type != 'LIGHT':
            continue
        on = o.visible_get() if viewport else not o.hide_render
        if on and o.data.energy > 0:
            out.append(o)
    return out


def key_light_issue(scene):
    """(message, light, action) when the shadows can't follow the key light (§42); action 'KEY' =
    offer that light as the key light, 'NORENDER' = offer to turn it off in renders, None = just a note:
    cast shadows compare the light that really arrives with what the key light should give, so
    the key light must be the light doing the lighting."""
    key = scene.pl_key_light
    seen = _lights_on(scene, viewport=True)
    rendered = _lights_on(scene, viewport=False)
    others_seen = [o for o in seen if o != key]
    if key is not None and key not in seen and others_seen:
        return (f"'{key.name}' is hidden, but '{others_seen[0].name}' lights the model: shadows will be wrong",
                others_seen[0], 'KEY')
    if key is not None and key not in rendered and [o for o in rendered if o != key]:
        return (f"'{key.name}' is off in renders: rendered shadows will be wrong", None, None)
    hidden_but_rendering = [o for o in rendered if o != key and o not in seen]
    if key is not None and hidden_but_rendering:
        o = hidden_but_rendering[0]
        return (f"'{o.name}' is hidden in the viewport but still lights renders: rendered shadows will be wrong",
                o, 'NORENDER')
    if key is not None and others_seen:
        return (f"'{others_seen[0].name}' also lights the model: cast shadows assume the key light is "
                f"the only light", None, None)
    return None


class PL_OT_key_light_use(bpy.types.Operator):
    bl_idname = "pl.key_light_use"
    bl_label = "Use as Key Light"
    bl_description = "Make this light the key light: light layers and cast shadows follow it"
    bl_options = {'REGISTER', 'UNDO'}
    name: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None or ob.type != 'LIGHT':
            return {'CANCELLED'}
        context.scene.pl_key_light = ob
        return {'FINISHED'}


class PL_OT_light_render_off(bpy.types.Operator):
    bl_idname = "pl.light_render_off"
    bl_label = "Turn Off in Renders"
    bl_description = "Stop this (viewport-hidden) light from lighting renders"
    bl_options = {'REGISTER', 'UNDO'}
    name: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            return {'CANCELLED'}
        ob.hide_render = True
        return {'FINISHED'}


classes = (PL_OT_key_light_detect, PL_OT_key_light_choose, PL_OT_key_light_use, PL_OT_light_render_off)


# ----------------------------------------------------------------------------- light sphere
# A DIRECTION property draws as Blender's shaded sphere: the highlight sits where the light
# comes from. It is shown in VIEW space (rotated with the 3D view), so "lit from the upper left"
# on the sphere means upper left on screen. Value = direction TOWARD the light.

def _view_rotation():
    """The view the light ball shows the light from: the 3D view you last orbited (so a ball in a
    second view's sidebar still follows the view you're working in), else this sidebar's own view."""
    from mathutils import Quaternion
    q = _last_moved[0]
    if q is not None:
        return Quaternion(q)
    ctx = bpy.context
    rv = getattr(ctx, "region_data", None)
    if rv is None:
        sp = getattr(ctx, "space_data", None)
        if sp is not None and sp.type == 'VIEW_3D':
            rv = sp.region_3d
    screens = [ctx.screen] if getattr(ctx, "screen", None) is not None else []
    if ctx.window_manager is not None:   # (a floating window has no 3D view: use another window's)
        screens += [w.screen for w in ctx.window_manager.windows if w.screen is not None]
    for scr in screens if rv is None else ():
        area = next((a for a in scr.areas if a.type == 'VIEW_3D'), None)
        if area is not None:
            rv = area.spaces.active.region_3d
            break
    return rv.view_rotation.copy() if rv is not None else Quaternion()


_last_views = {}
_last_moved = [None]   # view_rotation of the 3D view that changed last


def watch_views():
    """The light balls show the light AS SEEN FROM the view: repaint the sidebars / header of a 3D
    view when its angle changes (they don't redraw on orbit by themselves). Light timer."""
    try:
        wm = bpy.context.window_manager
        seen = set()
        changed = False
        for win in (wm.windows if wm else ()):
            for area in win.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                r3 = area.spaces.active.region_3d
                if r3 is None:
                    continue
                key = area.as_pointer()
                seen.add(key)
                q = tuple(round(x, 4) for x in r3.view_rotation)
                if _last_views.get(key) != q:
                    first = key not in _last_views
                    _last_views[key] = q
                    if not first:   # (a view seen for the first time hasn't been orbited)
                        _last_moved[0] = tuple(r3.view_rotation)
                        changed = True
        if changed:   # every 3D view's sidebar / header: a ball anywhere follows the moved view
            for win in wm.windows:
                for area in win.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            if region.type in ('UI', 'HEADER', 'TOOL_HEADER'):
                                region.tag_redraw()
        for key in list(_last_views):
            if key not in seen:
                del _last_views[key]
        from ..ui.floating import redraw_floats
        redraw_floats(force=changed)   # (floating windows: after any change, and their light ball)
    except Exception as e:   # (a timer must never die)
        print("CaraPainter light ball:", e)
    return 0.1


def light_target(scene):
    """('layer', layer) when the active layer overrides its direction, else ('key', light)."""
    ob = bpy.context.object
    mat = ob.active_material if ob else None
    if mat is not None and mat.pl_stack.enabled:
        act = mat.pl_stack.active
        if act is not None and act.layer_type in LIGHT_TYPES and act.light_override:
            return "layer", act
    return "key", scene.pl_key_light


def world_light_dir(scene):
    from mathutils import Vector
    kind, target = light_target(scene)
    if kind == "layer":
        return Vector(target.light_dir).normalized()
    if target is None:
        return Vector((0, 0, 1))
    return (target.matrix_world.to_quaternion() @ Vector((0, 0, 1))).normalized()


def set_world_light_dir(scene, d):
    kind, target = light_target(scene)
    d = d.normalized()
    if kind == "layer":
        target.light_dir = d
    elif target is not None:
        mw = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()  # light's +Z points at the light dir
        mw.translation = target.matrix_world.translation
        target.matrix_world = mw


def get_light_widget(scene):
    return tuple(_view_rotation().inverted() @ world_light_dir(scene))


def set_light_widget(scene, value):
    from mathutils import Vector
    set_world_light_dir(scene, _view_rotation() @ Vector(value))
