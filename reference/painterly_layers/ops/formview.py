"""Form View (Shift+C): the stack's base colour on a plain PBR surface with the normal map, lit by
the viewport's studio light, like a Substance Painter base look — to judge the model's forms.

Nodes (added on first use, removed on detach): a "PL Form Switch" mix shader in front of every
Material Output the add-on manages, factor = pl_form_view x (1 - pl_base_view), so the flat view
(C, Z picker) always wins. Light layers hide in Form View (they paint lighting). The scene props
are 0 in every saved file (save_pre/save_post), so SheepIt always renders the real shader.
"""
import bpy

from .attach import STACK_NODE, active_output
from .view import BASE_VIEW, _redraw, base_view_active, in_painterly, set_base_view

FORM_VIEW = "pl_form_view"
F_SWITCH = "PL Form Switch"       # + " · <output name>"
F_BSDF = "PL Form BSDF"
F_NORMAL = "PL Form Normal Map"
F_NIMG = "PL Form Normal"
F_FAC = "PL Form Factor"
F_ATTR, F_ATTR_BASE = "PL Form Attr", "PL Form Base Attr"
NODES = (F_BSDF, F_NORMAL, F_NIMG, F_FAC, F_ATTR, F_ATTR_BASE)

_prev_shading = {}   # space pointer -> viewport lighting settings before Form View


def form_view_active(scene):
    return scene.get(FORM_VIEW, 0.0) > 0.5


def _managed_outputs(mat):
    tree = mat.node_tree
    names = [mat.pl_stack.attach.output_node, "PL Hybrid Output"]
    return [tree.nodes[n] for n in names if n and tree.nodes.get(n) is not None]


_COLOR = "Color"   # (the Diffuse BSDF's colour input; Principled called it "Base Color")


def upgrade_bsdf(mat):
    """Form View nodes made before 0.23 used a Principled BSDF: EEVEE spends ~1 s compiling it in
    every material (§59). Swap it for a Diffuse BSDF in place, links kept. Our own node."""
    tree = mat.node_tree
    old = tree.nodes.get(F_BSDF) if tree is not None else None
    if old is None or old.bl_idname != 'ShaderNodeBsdfPrincipled':
        return False
    new = tree.nodes.new('ShaderNodeBsdfDiffuse')
    new.location = old.location
    for a, b in (("Base Color", "Color"), ("Normal", "Normal")):
        for l in old.inputs[a].links:
            tree.links.new(l.from_socket, new.inputs[b])
    outs = [l.to_socket for l in old.outputs[0].links]
    tree.nodes.remove(old)
    new.name = new.label = F_BSDF
    for s in outs:
        tree.links.new(new.outputs[0], s)
    return True


def ensure_nodes(mat):
    """Build the Form View nodes in the material if missing (idempotent)."""
    st = mat.pl_stack
    tree = mat.node_tree
    stack = tree.nodes.get(STACK_NODE)
    if stack is None:
        return
    upgrade_bsdf(mat)
    bsdf = tree.nodes.get(F_BSDF)
    if bsdf is None:
        x, y = stack.location
        bsdf = tree.nodes.new('ShaderNodeBsdfDiffuse')   # (a Principled cost ~1 s of compiling, §59)
        bsdf.name = bsdf.label = F_BSDF
        bsdf.location = (x + 300, y - 650)
        a = tree.nodes.new('ShaderNodeAttribute')
        a.name = a.label = F_ATTR
        a.attribute_type, a.attribute_name = 'VIEW_LAYER', FORM_VIEW
        b = tree.nodes.new('ShaderNodeAttribute')
        b.name = b.label = F_ATTR_BASE
        b.attribute_type, b.attribute_name = 'VIEW_LAYER', BASE_VIEW
        inv = tree.nodes.new('ShaderNodeMath')
        inv.operation, inv.use_clamp = 'SUBTRACT', True
        inv.inputs[0].default_value = 1.0
        fac = tree.nodes.new('ShaderNodeMath')
        fac.name = fac.label = F_FAC
        fac.operation, fac.use_clamp = 'MULTIPLY', True
        a.location, b.location = (x + 300, y - 450), (x + 300, y - 550)
        inv.location, fac.location = (x + 480, y - 550), (x + 620, y - 450)
        tree.links.new(b.outputs["Fac"], inv.inputs[1])
        tree.links.new(a.outputs["Fac"], fac.inputs[0])
        tree.links.new(inv.outputs[0], fac.inputs[1])
        inv.name = inv.label = F_FAC + " inv"
    src = tree.nodes.get("PL Baked") if st.mode == "BAKED" and tree.nodes.get("PL Baked") else stack
    tree.links.new(src.outputs["Color"], bsdf.inputs[_COLOR])
    # the normal map (read-only input), like the model's own shading
    nimg = tree.nodes.get(F_NIMG)
    if st.normal_image is not None:
        if nimg is None:
            nimg = tree.nodes.new('ShaderNodeTexImage')
            nimg.name = nimg.label = F_NIMG
            nimg.location = (bsdf.location[0] - 500, bsdf.location[1] - 200)
            nm = tree.nodes.new('ShaderNodeNormalMap')
            nm.name = nm.label = F_NORMAL
            nm.location = (bsdf.location[0] - 220, bsdf.location[1] - 200)
            tree.links.new(nimg.outputs["Color"], nm.inputs["Color"])
            tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        nimg.image = st.normal_image
        nm = tree.nodes[F_NORMAL]
        nm.uv_map = st.uv_map
        if st.uv_map:
            uv = tree.nodes.get(F_NIMG + " UV") or tree.nodes.new('ShaderNodeUVMap')
            uv.name = uv.label = F_NIMG + " UV"
            uv.uv_map = st.uv_map
            tree.links.new(uv.outputs[0], nimg.inputs[0])
    fac = tree.nodes[F_FAC]
    for out in _managed_outputs(mat):
        name = f"{F_SWITCH} · {out.name}"
        if tree.nodes.get(name) is not None or not out.inputs["Surface"].is_linked:
            continue
        link = out.inputs["Surface"].links[0]
        mix = tree.nodes.new('ShaderNodeMixShader')
        mix.name = mix.label = name
        mix.location = (out.location[0], out.location[1] - 180)
        tree.links.new(fac.outputs[0], mix.inputs[0])
        tree.links.new(link.from_socket, mix.inputs[1])
        tree.links.new(bsdf.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs[0], out.inputs["Surface"])


def remove_nodes(mat):
    """Undo ensure_nodes exactly: outputs get their original shader back."""
    tree = mat.node_tree
    if tree is None:
        return
    for n in list(tree.nodes):
        if n.name.startswith(F_SWITCH):
            src = n.inputs[1].links[0].from_socket if n.inputs[1].is_linked else None
            dsts = [l.to_socket for l in n.outputs[0].links]
            tree.nodes.remove(n)
            if src is not None:
                for d in dsts:
                    tree.links.new(src, d)
    for name in NODES + (F_FAC + " inv", F_NIMG + " UV"):
        n = tree.nodes.get(name)
        if n is not None:
            tree.nodes.remove(n)


def _stack_materials():
    return [m for m in bpy.data.materials if m.node_tree is not None and m.pl_stack.enabled
            and m.node_tree.nodes.get(STACK_NODE) is not None]


def _shading_spaces(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                yield area.spaces.active


def set_form_view(context, on):
    sc = context.scene
    if on:
        if base_view_active(sc):
            set_base_view(context, False)
        for m in _stack_materials():
            ensure_nodes(m)
        for sp in _shading_spaces(context):   # neutral studio light, like Substance's base look
            sh = sp.shading
            key = sp.as_pointer()
            if key not in _prev_shading:
                _prev_shading[key] = (sh.use_scene_lights, sh.use_scene_world,
                                      sh.use_scene_lights_render, sh.use_scene_world_render)
            sh.use_scene_lights = sh.use_scene_world = False
            sh.use_scene_lights_render = sh.use_scene_world_render = False
    else:
        for sp in _shading_spaces(context):
            prev = _prev_shading.pop(sp.as_pointer(), None)
            if prev is not None:
                sh = sp.shading
                (sh.use_scene_lights, sh.use_scene_world,
                 sh.use_scene_lights_render, sh.use_scene_world_render) = prev
    sc[FORM_VIEW] = 1.0 if on else 0.0
    _redraw(context)


class _ToggleFormView:   # shared, never registered itself (see view._ToggleBaseView)
    bl_label = "Form View"
    bl_description = ("Show the base colour on a plain surface with the normal map under a neutral "
                      "studio light, like a Substance Painter base look (Shift+C). Click again to return")

    def execute(self, context):
        set_form_view(context, not form_view_active(context.scene))
        return {'FINISHED'}


class PL_OT_toggle_form_view(_ToggleFormView, bpy.types.Operator):
    bl_idname = "pl.toggle_form_view"


class PL_OT_toggle_form_view_key(_ToggleFormView, bpy.types.Operator):
    bl_idname = "pl.toggle_form_view_key"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return in_painterly(context)


# ----------------------------------------------------------------------------- save safety

_saved = {}


def views_off_for_save(scene):
    """save_pre: a file must never be saved in the flat or form view (SheepIt would render it)."""
    _saved.clear()
    if scene is None:
        return
    for k in (BASE_VIEW, FORM_VIEW):
        if scene.get(k, 0.0) > 0.5:
            _saved[k] = scene[k]
            scene[k] = 0.0
    if BASE_VIEW in _saved:
        from .view import PREV_VT
        vs = scene.view_settings
        _saved["vt"] = vs.view_transform
        vs.view_transform = scene.get(PREV_VT, vs.view_transform)


def views_back_after_save(scene):
    if scene is None or not _saved:
        return
    for k in (BASE_VIEW, FORM_VIEW):
        if k in _saved:
            scene[k] = _saved[k]
    if "vt" in _saved:
        scene.view_settings.view_transform = _saved["vt"]
    _saved.clear()


classes = (PL_OT_toggle_form_view, PL_OT_toggle_form_view_key)
