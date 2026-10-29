"""Silhouette outline (§44): an inflated copy of the creature (a "hull"), drawn in ink and pushed
away from the viewer until it hides behind the creature, so only the rim OUTSIDE the silhouette
shows. Correct from any view, in the viewport and in renders.

- One object per creature, "CaraPainter Outline · <creature>", holding only a Geometry Nodes
  modifier: it reads the creature's final mesh (pose, modifiers) plus an optional Include
  collection, at the world origin (unselectable, casts no shadows, only seen by camera rays).
- Per point: inflate along the smooth normal by Width (in pixels at 1080 lines, so the line keeps
  its on-screen size at any distance), then ray-cast along the line of sight: if the creature is
  behind the point, push the point just behind it (hidden). Moving a point along its line of sight
  never moves it on screen, so the ring outside the silhouette keeps its exact width while every
  inner contour (a leg over the body) disappears, and the ring never sinks into the ground.
- Light / Shadow Strength: a second ray towards the key light (cast shadows) x which way the
  point faces it; the line thins away to nothing where its strength is 0.
- Sketchy: 1-3 strokes, each wobbled and thick-and-thin by its own noise.
- Where the viewer is: renders (Is Viewport off) use the scene camera, through plain Property
  drivers on lens / sensor / resolution: SheepIt renders it without the add-on. The viewport
  view comes from a light timer that writes the largest 3D view's eye into the modifier only
  when it changed (the line can trail an orbit by a frame).
The §39 compositor outline (and §38 Line Art) are removed when this one is added.
"""
import bpy
from mathutils import Vector

from .layers import get_stack

GN_GROUP = "CaraPainter Outline"
MOD = "CaraPainter Outline"
INK = "CaraPainter Outline Ink"
VERSION = 5
LINES = 1080.0          # Width is in pixels of an image this many lines tall
TICK = 1.0 / 30.0

# legacy (§39 compositor outline): only ever removed now
LEGACY_NODE = "CaraPainter Outline"
LEGACY_RL = "CaraPainter Render Layers"
LEGACY_AOVS = ("pl_mask", "pl_lit")
LEGACY_MAT_NODES = ("PL AOV Mask", "PL AOV Lit", "PL Outline Lit")

INPUTS = (  # name, socket type, default
    ("Creature", 'NodeSocketObject', None),
    ("Include", 'NodeSocketCollection', None),
    ("Casters", 'NodeSocketCollection', None),
    ("Key Light", 'NodeSocketObject', None),
    ("Key Point", 'NodeSocketFloat', 0.0),
    ("Eye", 'NodeSocketVector', (0.0, -10.0, 0.0)),
    ("View Dir", 'NodeSocketVector', (0.0, 1.0, 0.0)),
    ("Ortho", 'NodeSocketFloat', 0.0),
    ("View Height", 'NodeSocketFloat', 0.8),
    ("Lens", 'NodeSocketFloat', 50.0),
    ("Sensor", 'NodeSocketFloat', 36.0),
    ("Res X", 'NodeSocketFloat', 1920.0),
    ("Res Y", 'NodeSocketFloat', 1080.0),
    ("Cam Type", 'NodeSocketFloat', 0.0),
    ("Ortho Scale", 'NodeSocketFloat', 6.0),
    ("Width", 'NodeSocketFloat', 3.0),
    ("Light Strength", 'NodeSocketFloat', 1.0),
    ("Shadow Strength", 'NodeSocketFloat', 0.0),
    ("Sketchy", 'NodeSocketFloat', 0.0),
    ("Strokes", 'NodeSocketFloat', 2.0),
    ("Wobble", 'NodeSocketFloat', 0.3),
    ("Width Variation", 'NodeSocketFloat', 0.6),
    ("Scale", 'NodeSocketFloat', 6.0),
    ("Seed", 'NodeSocketFloat', 0.0),
    ("Material", 'NodeSocketMaterial', None),
    ("Mask", 'NodeSocketImage', None),
    ("UV Map", 'NodeSocketString', None),
    ("Use Mask", 'NodeSocketFloat', 0.0),
    ("Data", 'NodeSocketObject', None),
    ("Data Mode", 'NodeSocketFloat', 0.0),
)
DRIVEN = (("Lens", "camera.data.lens"), ("Sensor", "camera.data.sensor_width"),
          ("Res X", "render.resolution_x"), ("Res Y", "render.resolution_y"),
          ("Cam Type", "camera.data.type"), ("Ortho Scale", "camera.data.ortho_scale"))
VIEW_INPUTS = ("Eye", "View Dir", "Ortho", "View Height")


# ----------------------------------------------------------------------------- geometry nodes

def _attr(nb, name, data_type='FLOAT'):
    na = nb.node('GeometryNodeInputNamedAttribute', data_type=data_type)
    na.inputs["Name"].default_value = name
    return na.outputs["Attribute"]


def _lit(nb, blockers, size, ldir):
    """How lit each point is: faces the key light x no cast shadow (a ray towards the light,
    started just off the surface so it can't hit its own triangle). Computed ONCE per update and
    shared by every stroke."""
    P = nb.node('GeometryNodeInputPosition').outputs[0]
    N = nb.node('GeometryNodeInputNormal').outputs[0]
    eps = nb.mul(size, 0.002)
    ndl = nb.dot(N, ldir)
    side = nb.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
    nb.feed(side.inputs["Value"], ndl)
    side.inputs["From Min"].default_value = -0.05
    side.inputs["From Max"].default_value = 0.08
    sh = nb.node('GeometryNodeRaycast')
    nb.feed(sh.inputs["Target Geometry"], blockers)
    nb.feed(sh.inputs["Source Position"], nb.v('ADD', P, nb.vscale(nb.v('ADD', N, ldir), eps)))
    nb.feed(sh.inputs["Ray Direction"], ldir)
    sh.inputs["Ray Length"].default_value = 1e5
    return nb.mul(side.outputs[0], nb.sub(1.0, sh.outputs["Is Hit"]))


def _hull(nb, gi, src, body, size, eye, vdir, ortho, unit, k):
    """One stroke: the inflated, view-pushed copy of `src` (the creature's points near the
    silhouette, with pl_lit / pl_n stored), pushed behind `body` (k = stroke number, for its noise)."""
    I = gi.outputs
    P = nb.node('GeometryNodeInputPosition').outputs[0]
    N = _attr(nb, "pl_n", 'FLOAT_VECTOR')        # the full mesh's smooth normal (before pruning)
    eps = nb.mul(size, 0.002)
    lit = _attr(nb, "pl_lit")
    strength = nb.mixf(lit, I["Shadow Strength"], I["Light Strength"])
    # the painted outline mask (§48): 0.5 = automatic, white -> always (full), black -> never
    na = nb.node('GeometryNodeInputNamedAttribute', data_type='FLOAT')
    na.inputs["Name"].default_value = MASK_ATTR
    m = nb.mixf(na.outputs["Exists"], 0.5, na.outputs["Attribute"])
    km = nb.mul(nb.sub(m, 0.5), 2.0)
    strength = nb.add(strength, nb.mul(nb.sub(1.0, strength), nb.clamp(km)))
    strength = nb.mul(strength, nb.sub(1.0, nb.clamp(nb.mul(km, -1.0))))

    # world size of one width unit here (perspective: grows with distance)
    to_p = nb.v('SUBTRACT', P, eye)
    dist = nb.mx(nb.v('LENGTH', to_p), 1e-3)
    px = nb.mul(unit, nb.mixf(ortho, dist, 1.0))

    # sketchy: thick-and-thin + wobble, from a noise per stroke
    sk = I["Sketchy"]
    noise = nb.node('ShaderNodeTexNoise', noise_dimensions='4D')
    nb.feed(noise.inputs["Vector"], nb.vscale(P, nb.div(I["Scale"], size)))
    nb.feed(noise.inputs["W"], nb.add(I["Seed"], 7.31 * k))
    noise.inputs["Detail"].default_value = 2.0
    f = nb.clamp(nb.add(nb.mul(nb.sub(noise.outputs["Fac"], 0.5), 2.5), 0.5))
    var = nb.sub(1.0, nb.mul(nb.mul(I["Width Variation"], sk), f))
    w = nb.mul(nb.mul(nb.mul(I["Width"], strength), var), px)
    wob = nb.vscale(nb.v('SUBTRACT', noise.outputs["Color"], (0.5, 0.5, 0.5)),
                    nb.mul(nb.mul(nb.mul(I["Wobble"], sk), nb.mul(I["Width"], px)), 3.0))
    q = nb.v('ADD', nb.v('ADD', P, nb.vscale(N, w)), wob)

    # push along the line of sight until just behind whatever part of the creature is there
    ray = nb.mixv(ortho, nb.v('NORMALIZE', nb.v('SUBTRACT', q, eye)), vdir)
    rc = nb.node('GeometryNodeRaycast')
    nb.feed(rc.inputs["Target Geometry"], body)
    nb.feed(rc.inputs["Source Position"], q)
    nb.feed(rc.inputs["Ray Direction"], ray)
    rc.inputs["Ray Length"].default_value = 1e5
    push = nb.mul(rc.outputs["Is Hit"], nb.add(rc.outputs["Hit Distance"], nb.add(nb.mul(w, 3.0), eps)))
    q = nb.v('ADD', q, nb.vscale(ray, push))

    # drop the points whose line is too thin to see (no ink coinciding with the surface)
    dele = nb.node('GeometryNodeDeleteGeometry', domain='POINT')
    nb.feed(dele.inputs["Geometry"], src)
    nb.feed(dele.inputs["Selection"], nb.lt(w, nb.mul(px, 0.05)))
    sp = nb.node('GeometryNodeSetPosition')
    nb.feed(sp.inputs["Geometry"], dele.outputs[0])
    nb.feed(sp.inputs["Position"], q)
    return sp.outputs[0]


def gn_group():
    from ..compiler.nodes import NB
    tree = bpy.data.node_groups.get(GN_GROUP)
    if tree is not None and tree.bl_idname == 'GeometryNodeTree' and tree.get("pl_version") == VERSION:
        return tree
    if tree is None or tree.bl_idname != 'GeometryNodeTree':
        tree = bpy.data.node_groups.new(GN_GROUP, 'GeometryNodeTree')
    tree.nodes.clear()
    if not len(tree.interface.items_tree):
        tree.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        tree.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    have = {it.name for it in tree.interface.items_tree if getattr(it, "in_out", None) == 'INPUT'}
    for name, typ, d in INPUTS:   # only ADD missing sockets: modifiers link to the identifiers
        if name not in have:
            s = tree.interface.new_socket(name, in_out='INPUT', socket_type=typ)
            if d is not None:
                s.default_value = d
    nb = NB(tree)
    gi = nb.node('NodeGroupInput')
    go = nb.node('NodeGroupOutput')
    I = gi.outputs

    # ---- DATA mode (the hidden "Outline Data" object, §49): everything that doesn't depend on the
    # view - the creature (+ Include) in world space with the painted mask, smooth normals and how
    # lit each point is. Only re-evaluated when the creature, light, casters or mask change.
    oi = nb.node('GeometryNodeObjectInfo', transform_space='RELATIVE')
    nb.feed(oi.inputs["Object"], I["Creature"])
    ci = nb.node('GeometryNodeCollectionInfo', transform_space='RELATIVE')
    nb.feed(ci.inputs["Collection"], I["Include"])
    j = nb.node('GeometryNodeJoinGeometry')
    nb.feed(j.inputs[0], ci.outputs[0])
    # the outline mask, sampled per face corner (each with its own UV: right across UV seams) and
    # averaged onto the points, stored on the creature only (Include parts read as automatic)
    uv = nb.node('GeometryNodeInputNamedAttribute', data_type='FLOAT_VECTOR')
    nb.feed(uv.inputs["Name"], I["UV Map"])
    tex = nb.node('GeometryNodeImageTexture', interpolation='Linear')
    nb.feed(tex.inputs["Image"], I["Mask"])
    nb.feed(tex.inputs["Vector"], uv.outputs["Attribute"])
    sampled = nb.mixf(nb.mul(I["Use Mask"], uv.outputs["Exists"]), 0.5, nb.sepxyz(tex.outputs["Color"])[0])
    per_point = nb.node('GeometryNodeFieldOnDomain', domain='CORNER', data_type='FLOAT')
    nb.feed(per_point.inputs[0], sampled)
    store = nb.node('GeometryNodeStoreNamedAttribute', data_type='FLOAT', domain='POINT')
    nb.feed(store.inputs["Geometry"], oi.outputs["Geometry"])
    store.inputs["Name"].default_value = MASK_ATTR
    nb.feed(store.inputs["Value"], per_point.outputs[0])
    nb.feed(j.inputs[0], store.outputs[0])
    real = nb.node('GeometryNodeRealizeInstances')
    nb.feed(real.inputs[0], j.outputs[0])
    dbody = real.outputs[0]
    # cast shadows onto the line: the creature + every other shadow-casting object (§45)
    cc = nb.node('GeometryNodeCollectionInfo', transform_space='RELATIVE')
    nb.feed(cc.inputs["Collection"], I["Casters"])
    jc = nb.node('GeometryNodeJoinGeometry')
    nb.feed(jc.inputs[0], cc.outputs[0])
    nb.feed(jc.inputs[0], dbody)
    rc = nb.node('GeometryNodeRealizeInstances')
    nb.feed(rc.inputs[0], jc.outputs[0])
    blockers = rc.outputs[0]
    dbb = nb.node('GeometryNodeBoundBox')
    nb.feed(dbb.inputs[0], dbody)
    dsize = nb.mx(nb.v('DISTANCE', dbb.outputs["Min"], dbb.outputs["Max"]), 1e-4)
    # the key light's direction at each point (sun: its rotation; point / spot: towards it)
    kl = nb.node('GeometryNodeObjectInfo', transform_space='RELATIVE')
    nb.feed(kl.inputs["Object"], I["Key Light"])
    kr = nb.node('FunctionNodeRotateVector')
    kr.inputs["Vector"].default_value = (0.0, 0.0, 1.0)
    nb.feed(kr.inputs["Rotation"], kl.outputs["Rotation"])
    P = nb.node('GeometryNodeInputPosition').outputs[0]
    ldir = nb.v('NORMALIZE', nb.mixv(I["Key Point"], kr.outputs[0],
                                     nb.v('SUBTRACT', kl.outputs["Location"], P)))
    st_n = nb.node('GeometryNodeStoreNamedAttribute', data_type='FLOAT_VECTOR', domain='POINT')
    nb.feed(st_n.inputs["Geometry"], dbody)
    st_n.inputs["Name"].default_value = "pl_n"
    nb.feed(st_n.inputs["Value"], nb.node('GeometryNodeInputNormal').outputs[0])
    st_l = nb.node('GeometryNodeStoreNamedAttribute', data_type='FLOAT', domain='POINT')
    nb.feed(st_l.inputs["Geometry"], st_n.outputs[0])
    st_l.inputs["Name"].default_value = "pl_lit"
    nb.feed(st_l.inputs["Value"], _lit(nb, blockers, dsize, ldir))
    data_out = st_l.outputs[0]

    # ---- OUTLINE mode: the data object's geometry (cached), seen from the current viewer
    di = nb.node('GeometryNodeObjectInfo', transform_space='RELATIVE')
    nb.feed(di.inputs["Object"], I["Data"])
    body = di.outputs["Geometry"]
    bb = nb.node('GeometryNodeBoundBox')
    nb.feed(bb.inputs[0], body)
    size = nb.mx(nb.v('DISTANCE', bb.outputs["Min"], bb.outputs["Max"]), 1e-4)

    # the viewer: the viewport's (from the timer) or the scene camera's (renders)
    isv = nb.node('GeometryNodeIsViewport').outputs[0]
    cam = nb.node('GeometryNodeObjectInfo', transform_space='RELATIVE')
    nb.feed(cam.inputs["Object"], nb.node('GeometryNodeInputActiveCamera').outputs[0])
    rv = nb.node('FunctionNodeRotateVector')
    rv.inputs["Vector"].default_value = (0.0, 0.0, -1.0)
    nb.feed(rv.inputs["Rotation"], cam.outputs["Rotation"])
    big = nb.mx(I["Res X"], I["Res Y"])
    ratio = nb.div(I["Res Y"], big)
    cam_ortho = nb.m('COMPARE', I["Cam Type"], 1.0, 0.1)
    cam_h = nb.mixf(cam_ortho, nb.mul(nb.div(I["Sensor"], I["Lens"]), ratio), nb.mul(I["Ortho Scale"], ratio))
    eye = nb.mixv(isv, cam.outputs["Location"], I["Eye"])
    vdir = nb.mixv(isv, rv.outputs[0], I["View Dir"])
    ortho = nb.mixf(isv, cam_ortho, I["Ortho"])
    unit = nb.div(nb.mixf(isv, cam_h, I["View Height"]), LINES)

    # only points near the silhouette can ever show a line: drop the ones facing the viewer or
    # facing away (most of the mesh) before any ray is cast (§49)
    Pp = nb.node('GeometryNodeInputPosition').outputs[0]
    Np = _attr(nb, "pl_n", 'FLOAT_VECTOR')
    view = nb.mixv(ortho, nb.v('NORMALIZE', nb.v('SUBTRACT', Pp, eye)), vdir)
    prune = nb.node('GeometryNodeDeleteGeometry', domain='POINT')
    nb.feed(prune.inputs["Geometry"], body)
    nb.feed(prune.inputs["Selection"], nb.gt(nb.m('ABSOLUTE', nb.dot(Np, view)), PRUNE))
    src = prune.outputs[0]

    out = nb.node('GeometryNodeJoinGeometry')
    for k in range(3):
        h = _hull(nb, gi, src, body, size, eye, vdir, ortho, unit, k)
        if k:
            on = nb.mul(nb.gt(I["Sketchy"], 0.5), nb.gt(I["Strokes"], k + 0.5))
            sw = nb.node('GeometryNodeSwitch', input_type='GEOMETRY')
            nb.feed(sw.inputs["Switch"], on)
            nb.feed(sw.inputs["True"], h)
            h = sw.outputs[0]
        nb.feed(out.inputs[0], h)
    sm = nb.node('GeometryNodeSetMaterial')
    nb.feed(sm.inputs["Geometry"], out.outputs[0])
    nb.feed(sm.inputs["Material"], I["Material"])
    mode = nb.node('GeometryNodeSwitch', input_type='GEOMETRY')   # (lazy: only one side runs)
    nb.feed(mode.inputs["Switch"], nb.gt(I["Data Mode"], 0.5))
    nb.feed(mode.inputs["False"], sm.outputs[0])
    nb.feed(mode.inputs["True"], data_out)
    nb.feed(go.inputs[0], mode.outputs[0])
    tree["pl_version"] = VERSION
    return tree


def _get(mod, ids, name):
    v = getattr(mod.properties.inputs, ids[name]).value
    return tuple(v) if hasattr(v, "__len__") and not isinstance(v, str) else v


def _set(mod, ids, name, value):
    """Blender 5.2: modifier inputs live on mod.properties.inputs.<identifier>.value."""
    getattr(mod.properties.inputs, ids[name]).value = value


def _ids(tree):
    return {it.name: it.identifier for it in tree.interface.items_tree
            if getattr(it, "in_out", None) == 'INPUT'}


# ----------------------------------------------------------------------------- objects

INK_VERSION = 3


def ink_material():
    """Plain emission ink. (Fading it in shadows can't be done in the material: a transparent
    material's mask is evaluated before lighting, where Shader to RGB reads 0 - §45.)"""
    mat = bpy.data.materials.get(INK) or bpy.data.materials.new(INK)
    if mat.get("pl_ink") == INK_VERSION:
        return mat
    tree = mat.node_tree
    tree.nodes.clear()
    em = tree.nodes.new('ShaderNodeEmission')
    em.name = "Ink"
    out = tree.nodes.new('ShaderNodeOutputMaterial')
    out.location = (300, 0)
    tree.links.new(em.outputs[0], out.inputs["Surface"])
    mat["pl_ink"] = INK_VERSION
    return mat


def outline_objects(sc):
    return [o for o in sc.objects if o.get("pl_outline")]


def _ours(o):
    return bool(o.get("pl_outline") or o.get("pl_outline_data"))


def data_object(ob):
    """The hidden data object behind an outline (§49), or None."""
    mod = ob.modifiers.get(MOD)
    if mod is None or mod.node_group is None:
        return None
    ids = _ids(mod.node_group)
    return _get(mod, ids, "Data") if "Data" in ids else None


def _ensure_data(ob):
    """Outlines from 0.19.0 and earlier have no data object yet: make it (same group, Data Mode)."""
    mod = ob.modifiers[MOD]
    ids = _ids(mod.node_group)
    d = _get(mod, ids, "Data")
    if d is not None and d.name in bpy.data.objects:
        return d
    creature = _get(mod, ids, "Creature")
    me = bpy.data.meshes.new(f"CaraPainter Outline Data · {creature.name if creature else ob.name}")
    d = bpy.data.objects.new(me.name, me)
    d["pl_outline_data"] = True
    for c in ob.users_collection:
        c.objects.link(d)
    dm = d.modifiers.new(MOD, 'NODES')
    dm.node_group = mod.node_group
    _set(dm, ids, "Data Mode", 1.0)
    _set(dm, ids, "Creature", creature)
    d.hide_select = True
    d.lock_location = d.lock_rotation = d.lock_scale = (True, True, True)
    d.display_type = 'BOUNDS'
    d.hide_viewport = d.hide_render = True   # never drawn; evaluated because the outline reads it
    _set(mod, ids, "Data", d)
    return d


def creatures(sc):
    """Mesh objects wearing a CaraPainter material."""
    return [o for o in sc.objects if o.type == 'MESH' and not _ours(o)
            and any(s.material is not None and s.material.pl_stack.enabled for s in o.material_slots)]


def _drive(ob, sc, ids):
    for name, path in DRIVEN:
        dp = f'modifiers["{MOD}"].properties.inputs.{ids[name]}.value'
        ob.driver_remove(dp)
        drv = ob.driver_add(dp).driver
        drv.type = 'AVERAGE'
        v = drv.variables.new()
        v.type = 'SINGLE_PROP'
        v.targets[0].id_type = 'SCENE'
        v.targets[0].id = sc
        v.targets[0].data_path = path


def add_for(sc, creature):
    for o in outline_objects(sc):
        mod = o.modifiers.get(MOD)
        if mod is not None and _get(mod, _ids(mod.node_group), "Creature") == creature:
            return o
    tree = gn_group()
    ids = _ids(tree)
    me = bpy.data.meshes.new(f"CaraPainter Outline · {creature.name}")
    ob = bpy.data.objects.new(me.name, me)
    ob["pl_outline"] = True
    (creature.users_collection[0] if creature.users_collection else sc.collection).objects.link(ob)
    mod = ob.modifiers.new(MOD, 'NODES')
    mod.node_group = tree
    _set(mod, ids, "Creature", creature)
    _set(mod, ids, "Material", ink_material())
    ob.hide_select = True
    ob.lock_location = ob.lock_rotation = ob.lock_scale = (True, True, True)
    for flag in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter"):
        setattr(ob, flag, False)   # only the camera sees it: no shadows, bakes or reflections
    _drive(ob, sc, ids)
    _ensure_data(ob)
    return ob


MASK_ATTR = "pl_outline_mask"
PRUNE = 0.6   # |N . view| above this: never near the silhouette, skipped (§49)


def _stack_of(ob):
    """The first CaraPainter stack on this object's materials."""
    if ob is None:
        return None
    for s in ob.material_slots:
        if s.material is not None and s.material.pl_stack.enabled:
            return s.material.pl_stack
    return None


def _uv_name(ob, st):
    if st is not None and st.uv_map:
        return st.uv_map
    uvs = getattr(ob.data, "uv_layers", None) if ob is not None else None
    if not uvs:
        return ""
    act = next((u for u in uvs if u.active_render), None) or uvs.active or uvs[0]
    return act.name


def _caster_set(sc):
    """What casts shadows in the viewport, minus the creatures (already in the hull's body), their
    Include collection and the outlines themselves."""
    skip = set(creatures(sc)) | set(sc.pl_outline.include.all_objects if sc.pl_outline.include else ())
    return {o for o in sc.objects if o.type == 'MESH' and not _ours(o) and o not in skip
            and o.visible_shadow and o.visible_get()}


def sync_casters(sc):
    """Keep the scene's hidden shadow-casters collection (not linked to the scene: it only feeds the
    outline's light rays; saved with the file for SheepIt) matching the scene. True if changed."""
    name = f"CaraPainter Shadow Casters · {sc.name}"
    coll = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    want = _caster_set(sc)
    have = set(coll.objects)
    if want == have:
        return coll, False
    for o in have - want:
        coll.objects.unlink(o)
    for o in want - have:
        coll.objects.link(o)
    return coll, True


def apply(sc):
    """Push Scene.pl_outline into every outline (values only)."""
    o = sc.pl_outline
    vals = {"Width": o.width, "Light Strength": o.light, "Shadow Strength": o.shadow,
            "Sketchy": 1.0 if o.sketch else 0.0, "Strokes": float(o.strokes), "Wobble": o.wobble,
            "Width Variation": o.width_var, "Seed": float(o.seed), "Scale": o.scale}
    key = sc.pl_key_light
    if outline_objects(sc):
        gn_group()            # outlines from an older version: bring the node group up to date
    casters = sync_casters(sc)[0] if outline_objects(sc) else None
    for ob in outline_objects(sc):
        mod = ob.modifiers.get(MOD)
        if mod is None or mod.node_group is None:
            continue
        d = _ensure_data(ob)
        ids = _ids(mod.node_group)
        for k, v in vals.items():
            _set(mod, ids, k, v)
        creature = _get(mod, ids, "Creature")
        st = _stack_of(creature)
        mask = st.outline_mask if st is not None else None
        for m in (mod, d.modifiers[MOD]):         # (the data object does the view-free part)
            _set(m, ids, "Include", o.include)
            _set(m, ids, "Casters", casters)
            _set(m, ids, "Mask", mask)
            _set(m, ids, "Use Mask", 1.0 if mask is not None else 0.0)
            _set(m, ids, "UV Map", _uv_name(creature, st))
            _sync_key(m, ids, key)
        ob.hide_viewport = ob.hide_render = not o.show
        d.update_tag()
        ob.update_tag()
    mat = ink_material() if outline_objects(sc) else None
    if mat is not None:
        mat.node_tree.nodes["Ink"].inputs["Color"].default_value = (*o.color, 1.0)
        mat.diffuse_color = (*o.color, 1.0)   # (Solid view)


def _sync_key(mod, ids, key):
    point = 1.0 if key is not None and key.type == 'LIGHT' and key.data.type in ('POINT', 'SPOT', 'AREA') else 0.0
    changed = False
    if _get(mod, ids, "Key Light") != key:
        _set(mod, ids, "Key Light", key)
        changed = True
    if abs(_get(mod, ids, "Key Point") - point) > 1e-6:
        _set(mod, ids, "Key Point", point)
        changed = True
    return changed


def enable(context):
    sc = context.scene
    _remove_legacy(context)
    for c in creatures(sc):
        add_for(sc, c)
    apply(sc)
    tick()


def disable(context):
    sc = context.scene
    coll = bpy.data.collections.get(f"CaraPainter Shadow Casters · {sc.name}")
    if coll is not None:
        bpy.data.collections.remove(coll)
    for ob in outline_objects(sc) + [o for o in sc.objects if o.get("pl_outline_data")]:
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def is_enabled(sc):
    return bool(outline_objects(sc))


def add_for_material(mat, sc):
    """attach(): a newly attached creature gets its outline too, if the scene has one."""
    if not is_enabled(sc):
        return
    for c in creatures(sc):
        if any(s.material == mat for s in c.material_slots):
            add_for(sc, c)
    apply(sc)


# ----------------------------------------------------------------------------- viewport timer

def _view(window):
    """(eye, view dir, ortho, view height at distance 1 / absolute) of the window's largest 3D view."""
    best = None
    for area in window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        if best is None or area.width * area.height > best.width * best.height:
            best = area
    if best is None:
        return None
    r3 = best.spaces.active.region_3d
    if r3 is None:
        return None
    # from the view's own rotation / location / distance (view_matrix only updates on a redraw)
    fwd = Vector((0.0, 0.0, -1.0))
    cam = window.scene.camera
    if r3.view_perspective == 'CAMERA' and cam is not None:
        m = cam.matrix_world
        eye, vdir = m.translation.copy(), (m.to_3x3() @ fwd).normalized()
        ortho = 1.0 if cam.type == 'CAMERA' and cam.data.type == 'ORTHO' else 0.0
    else:
        vdir = (r3.view_rotation @ fwd).normalized()
        eye = r3.view_location - vdir * r3.view_distance
        ortho = 1.0 if r3.view_perspective == 'ORTHO' else 0.0
    p11 = r3.window_matrix[1][1]
    height = 2.0 / p11 if abs(p11) > 1e-9 else 1.0
    return eye, vdir, ortho, height


_count = [0]


_last_shadow_sync = [0.0]


def tick():
    """Write the viewer into each outline when it changed (never from a draw callback)."""
    try:
        import time
        wm = bpy.context.window_manager
        if wm is None:
            return 0.5
        if time.monotonic() - _last_shadow_sync[0] > 0.5:   # Shadow Data modifiers (§50)
            _last_shadow_sync[0] = time.monotonic()
            from . import shadowdata
            for sc in {w.scene for w in wm.windows}:
                shadowdata.cleanup(sc)
        any_outline = False
        for window in wm.windows:
            sc = window.scene
            obs = outline_objects(sc)
            if not obs:
                continue
            any_outline = True
            view = _view(window)
            if view is None:
                continue
            eye, vdir, ortho, height = view
            _count[0] = (_count[0] + 1) % 15          # objects added / hidden: ~twice a second
            coll, new_casters = sync_casters(sc) if _count[0] == 0 else (None, False)
            for ob in obs:
                mod = ob.modifiers.get(MOD)
                if mod is None or mod.node_group is None:
                    continue
                ids = _ids(mod.node_group)
                changed = _sync_key(mod, ids, sc.pl_key_light)
                d = data_object(ob)
                dm = d.modifiers.get(MOD) if d is not None else None
                if dm is not None and _sync_key(dm, ids, sc.pl_key_light):
                    d.update_tag()
                if new_casters:
                    _set(mod, ids, "Casters", coll)
                    if dm is not None:
                        _set(dm, ids, "Casters", coll)
                        d.update_tag()
                    changed = True
                old = (_get(mod, ids, "Eye"), _get(mod, ids, "View Dir"), _get(mod, ids, "Ortho"),
                       _get(mod, ids, "View Height"))
                new = (tuple(eye), tuple(vdir), ortho, height)
                if max(abs(a - b) for a, b in zip((*old[0], *old[1], old[2], old[3]),
                                                    (*new[0], *new[1], new[2], new[3]))) > 1e-5:
                    _set(mod, ids, "Eye", eye)
                    _set(mod, ids, "View Dir", vdir)
                    _set(mod, ids, "Ortho", ortho)
                    _set(mod, ids, "View Height", height)
                    changed = True
                if changed:
                    ob.update_tag()
            if any_outline:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
            break   # the first window with an outline drives it
        return TICK if any_outline else 0.5
    except Exception as e:  # a timer must never die
        print("CaraPainter outline:", e)
        return 0.5


# ----------------------------------------------------------------------------- legacy removal

def _legacy_compositor(sc):
    tree = sc.compositing_node_group
    return tree is not None and tree.nodes.get(LEGACY_NODE) is not None


def remove_material_aovs(mat):
    tree = mat.node_tree
    if tree is None:
        return
    for name in LEGACY_MAT_NODES:
        n = tree.nodes.get(name)
        if n is not None:
            tree.nodes.remove(n)


def _remove_lineart(st):
    ob = st.outline_object
    st.outline_object = None
    if ob is not None and ob.name in bpy.data.objects:
        gp = ob.data
        bpy.data.objects.remove(ob)
        if gp is not None and gp.users == 0:
            bpy.data.grease_pencils.remove(gp)


def _remove_legacy(context):
    """Take out the §39 compositor outline (restoring the compositor exactly) and §38 Line Art."""
    sc = context.scene
    for m in bpy.data.materials:
        if m.pl_stack.enabled:
            _remove_lineart(m.pl_stack)
        remove_material_aovs(m)
    tree = sc.compositing_node_group
    if tree is not None and tree.nodes.get(LEGACY_NODE) is not None:
        grp = tree.nodes.get(LEGACY_NODE)
        go = next((n for n in tree.nodes if n.type == 'GROUP_OUTPUT'), None)
        if sc.get("pl_comp_created"):
            sc.compositing_node_group = None
            if tree.users == 0:
                bpy.data.node_groups.remove(tree)
        else:
            rec = sc.get("pl_comp_src")
            tree.nodes.remove(grp)
            if rec is not None and go is not None:
                n = tree.nodes.get(rec[0])
                s = next((o for o in n.outputs if o.identifier == rec[1]), None) if n else None
                if s is not None:
                    tree.links.new(s, go.inputs[0])
            rl = tree.nodes.get(LEGACY_RL)
            if rl is not None:
                tree.nodes.remove(rl)
        for spc in _view3d_spaces(context):
            if spc.shading.use_compositor == 'ALWAYS':
                spc.shading.use_compositor = 'DISABLED'
    for k in ("pl_comp_created", "pl_comp_src"):
        if k in sc:
            del sc[k]
    for vl in sc.view_layers:
        for name in LEGACY_AOVS:
            a = vl.aovs.get(name)
            if a is not None:
                vl.aovs.remove(a)
    old = bpy.data.node_groups.get(LEGACY_NODE)
    if old is not None and old.bl_idname == 'CompositorNodeTree' and old.users == 0:
        bpy.data.node_groups.remove(old)


def _view3d_spaces(context):
    screens = {w.screen for w in context.window_manager.windows}
    for ws in bpy.data.workspaces:
        if ws.get("pl_painterly"):
            screens.update(ws.screens)
    for scr in screens:
        for area in scr.areas:
            if area.type == 'VIEW_3D':
                yield area.spaces.active


def remove(st):
    """Detach: a material leaving the stack system takes any old outline nodes along."""
    _remove_lineart(st)
    remove_material_aovs(st.id_data)


# ----------------------------------------------------------------------------- operators / UI

class PL_OT_outline_add(bpy.types.Operator):
    bl_idname = "pl.outline_add"
    bl_label = "Add Outline"
    bl_description = ("Draw the creature's outer silhouette as a line, from any view, in the viewport and in "
                      "renders (an ink copy of the creature hidden behind it). Strong in the key light, "
                      "none in shadow by default")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_stack(context)[1] is not None and not is_enabled(context.scene)

    def execute(self, context):
        enable(context)
        if not is_enabled(context.scene):
            self.report({'WARNING'}, "No object with a CaraPainter material in this scene")
            return {'CANCELLED'}
        return {'FINISHED'}


class PL_OT_outline_remove(bpy.types.Operator):
    bl_idname = "pl.outline_remove"
    bl_label = "Remove Outline"
    bl_description = "Delete the outline objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        disable(context)
        return {'FINISHED'}


# ----------------------------------------------------------------------------- outline painting (§48)

def new_outline_mask(st, ob):
    """2048 greyscale data image at 0.5 (= automatic everywhere), packed."""
    import numpy as np
    res = st.resolution
    img = bpy.data.images.new(f"CaraPainter Outline Mask · {ob.name if ob else st.id_data.name}", res, res,
                              alpha=False)
    img.colorspace_settings.name = "Non-Color"   # (before the pixels: changing it later blanks them)
    px = np.full(res * res * 4, 0.5, np.float32)
    px[3::4] = 1.0
    img.pixels.foreach_set(px)
    img.update()
    img["pl_owned"] = True
    img.pack()
    return img


def _set_brush_value(context, v):
    """Brush colours are scene-linear; the mask is Non-Color, so this lands as v in the image."""
    ip = context.tool_settings.image_paint
    ups = ip.unified_paint_settings
    ups.color = (v, v, v)
    if ip.brush is not None:
        ip.brush.color = (v, v, v)


BRUSH_VALUES = {"ADD": 1.0, "REMOVE": 0.0, "AUTO": 0.5}
BRUSH_KINDS = (
    ("ADD", "Add Line", "Paint white: a line here whenever this part is on the silhouette, even in shadow"),
    ("REMOVE", "Remove Line", "Paint black: never a line here"),
    ("AUTO", "Automatic", "Paint grey: back to the automatic light / shadow line"))


class PL_OT_outline_paint(bpy.types.Operator):
    bl_idname = "pl.outline_paint"
    bl_label = "Paint Outline"
    bl_description = ("Paint where the outline goes, on the creature: white = always a line there (even in "
                      "shadow), black = never, grey = automatic. Green / red on the model show your edits. "
                      "Click again to go back to painting your layers")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return get_stack(context)[1] is not None and ob is not None and ob.type == 'MESH'

    def execute(self, context):
        mat, st = get_stack(context)
        ob = context.active_object
        if st.outline_paint:
            st.outline_paint = False
            return {'FINISHED'}
        if st.outline_mask is None:
            st.outline_mask = new_outline_mask(st, ob)
        if not is_enabled(context.scene):
            enable(context)
        st.outline_paint = True
        if ob.mode != 'TEXTURE_PAINT':
            bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        _set_brush_value(context, 1.0)
        apply(context.scene)
        return {'FINISHED'}


class PL_OT_outline_brush(bpy.types.Operator):
    bl_idname = "pl.outline_brush"
    bl_label = "Outline Brush"
    bl_options = {'REGISTER', 'UNDO'}
    kind: bpy.props.EnumProperty(items=[(k, n, d) for k, n, d in BRUSH_KINDS], options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return next((d for k, _, d in BRUSH_KINDS if k == props.kind), "")

    def execute(self, context):
        _set_brush_value(context, BRUSH_VALUES[self.kind])
        return {'FINISHED'}


class PL_OT_outline_mask_clear(bpy.types.Operator):
    bl_idname = "pl.outline_mask_clear"
    bl_label = "Reset Outline Painting"
    bl_description = "Back to automatic everywhere (fills the outline mask with grey)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        st = get_stack(context)[1]
        return st is not None and st.outline_mask is not None

    def execute(self, context):
        import numpy as np
        img = get_stack(context)[1].outline_mask
        n = img.size[0] * img.size[1]
        px = np.full(n * 4, 0.5, np.float32)
        px[3::4] = 1.0
        img.pixels.foreach_set(px)
        img.update()
        img.pack()
        for ob in outline_objects(context.scene):
            ob.update_tag()
        return {'FINISHED'}


def draw(layout, context, st):
    sc = context.scene
    if not is_enabled(sc):
        layout.operator("pl.outline_add", icon='MOD_SOLIDIFY')
        if _legacy_compositor(sc):
            layout.label(text="(replaces the old compositor outline)", icon='INFO')
        return
    o = sc.pl_outline
    row = layout.row(align=True)
    row.prop(o, "show", text="", icon='HIDE_OFF' if o.show else 'HIDE_ON')
    row.prop(o, "color", text="")
    row.operator("pl.outline_remove", text="", icon='X')
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = False
    col.prop(o, "width")
    col.prop(o, "light", slider=True)
    col.prop(o, "shadow", slider=True)
    col.prop(o, "include")
    col.prop(o, "sketch")
    if o.sketch:
        col.prop(o, "strokes")
        col.prop(o, "wobble", slider=True)
        col.prop(o, "width_var", slider=True)
        col.prop(o, "scale")
        col.prop(o, "seed")
    if st is not None:
        box = layout.box()
        row = box.row(align=True)
        row.operator("pl.outline_paint", text="Paint Outline", icon='BRUSH_DATA', depress=st.outline_paint)
        if st.outline_mask is not None:
            row.operator("pl.outline_mask_clear", text="", icon='LOOP_BACK')
        if st.outline_paint:
            row = box.row(align=True)
            for kind, text, icon in (("ADD", "Add", 'ADD'), ("REMOVE", "Remove", 'REMOVE'),
                                     ("AUTO", "Auto", 'RADIOBUT_OFF')):
                row.operator("pl.outline_brush", text=text, icon=icon).kind = kind
            box.label(text="Green = always a line, red = never", icon='INFO')
    if sc.pl_key_light is None:
        layout.label(text="Pick the key light (Lighting & Bake) for light / shadow", icon='INFO')


classes = (PL_OT_outline_add, PL_OT_outline_remove, PL_OT_outline_paint, PL_OT_outline_brush,
           PL_OT_outline_mask_clear)


def register():
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=1.0, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
