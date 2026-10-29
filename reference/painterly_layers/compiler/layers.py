"""Per-layer private node trees ".PL L <uid>".

Every layer tree has the same outer interface so the stack can chain them:
    inputs  Under, UnderA, Opacity, Visible, (+ type parameters)
    outputs Out, OutA
A tree is only rebuilt when its structural signature changes; Blend If ramps and Curves are
carried over across rebuilds, so the user's edits survive.
"""
import bpy
from ..props import LIGHT_TYPES

from . import blend_lib
from .nodes import NB, iface, new_tree

TREE_PREFIX = ".PL L "
BI_CHANNELS = ("GREY", "R", "G", "B")
BI_EPS = 0.006  # keep values >1/255 from the ends: EEVEE samples ramps from a 256-entry LUT,
                # and entries 0/255 are ambiguous where the default stops coincide


LA_DEFAULTS = (("la_hue", 0.0), ("la_saturation", 1.0), ("la_value", 1.0))
LA_CURVE = "LA.curve"


def colour_adjusted(layer):
    """The layer's built-in Hue/Sat/Value moved off its defaults, or its Curve on?"""
    return layer.la_curve or any(abs(getattr(layer, k) - d) > 1e-6 for k, d in LA_DEFAULTS)


def _colour_adjust(nb, gi, layer, c):
    """The layer's own Hue/Sat/Value, then its curve graph, on its colour before it blends (§40).
    The curve node is edited directly by the panel's curve widget (kept across rebuilds)."""
    hs = nb.node('ShaderNodeHueSaturation')
    nb.feed(hs.inputs["Color"], c)
    nb.feed(hs.inputs["Hue"], nb.add(nb.div(gi.outputs["LA Hue"], 360.0), 0.5))
    nb.feed(hs.inputs["Saturation"], gi.outputs["LA Sat"])
    nb.feed(hs.inputs["Value"], gi.outputs["LA Val"])
    out = hs.outputs["Color"]
    if layer.la_curve:
        cv = nb.node('ShaderNodeRGBCurve', name=LA_CURVE, label="Layer curve")
        nb.feed(cv.inputs["Color"], out)
        out = cv.outputs["Color"]
    return out


def signature(layer, stack):
    parts = [blend_lib.LIB_VERSION, COMPILER_REV, layer.layer_type, layer.blend_mode, stack.blend_space,
             stack.uv_map, colour_adjusted(layer), layer.blend_if]
    t = layer.layer_type
    if t == "FILL":
        parts.append(layer.fill_source)
        if layer.fill_source == "IMAGE":
            parts += [layer.projection, layer.tile_break > 0]
            if layer.projection == "BOX":
                parts.append("A:%.4f,%.4f,%.4f" % _noise_aspect(stack))
    elif t == "ADJUST":
        parts.append(layer.adjust_kind)
    elif t in LIGHT_TYPES:
        parts += [layer.rim_reflect if t == "RIM_LIGHT" else False,
                  layer.sss_mode if t == "SSS_LIGHT" else "", bool(stack.thickness_image),
                  bool(stack.normal_image), bool(stack.forms_a and stack.forms_b and stack.forms_c),
                  layer.use_ramp, layer.breakup, stack.bake_variant, layer.light_ramp,
                  layer.light_polarity, layer.include_cast_shadow, layer.light_cast_shadow,
                  bool(stack.bake_shadow_image)]
    elif t == "GROUP":
        parts.append(layer.group_mode)
    if t in ("FILL", "PAINT"):
        parts.append(f"H:{layer.height_source}:{bool(layer.height_image)}")
    for m in layer.masks:  # mask structure (values are pushed, not compiled)
        parts.append(f"M:{m.source}:{m.op}:{bool(m.correction)}:{bool(m.image)}:{m.noise_type}")
        if m.source == "NOISE":
            parts.append("A:%.4f,%.4f,%.4f" % _noise_aspect(stack))
    if len(layer.masks):
        parts.append(f"D:{bool(stack.height_image)}:{bool(stack.curvature_image)}:"
                     f"{stack.bake_variant}:{bool(stack.bake_shadow_image)}")
    return "|".join(str(p) for p in parts)


COMPILER_REV = 9   # bump when layer trees change without a property change: rebuilds them on open
GRAZE = 0.12   # cast-shadow test: N.L below this fades towards 'in shadow' (§43)
CAST_LO, CAST_HI = 0.3, 0.7   # cast-shadow test: lit / expected ratio -> in shadow .. lit (§45)


LIGHT_RAMP = "LIGHT.lramp"
# shadow colour -> dark terminator -> clear (the lit side shows the layers below). The clear stops
# keep the terminator's colour: the ramp fades colour and alpha separately, so a clear WHITE stop
# would wash the fade with half-transparent grey (a pale haze over the lit side).
LIGHT_RAMP_DEFAULT = [(0.0, (0.047, 0.068, 0.030, 1.0)), (0.04, (0.004, 0.004, 0.004, 1.0)),   # (linear)
                      (0.1, (0.004, 0.004, 0.004, 0.0)), (1.0, (0.004, 0.004, 0.004, 0.0))]
# other starting ramps (PL_Layer.light_ramp_start). LAMBERT: clear in shadow, fading smoothly to a
# warm light facing the sun (a soft Lambert highlight; Screen blend)
LIGHT_RAMP_STARTS = {"LAMBERT": [(0.0, (1.0, 0.92, 0.8, 0.0)), (1.0, (1.0, 0.92, 0.8, 1.0))]}


def blocked_light(layer):
    """A Light-mode Normal Light that cast shadows block (§43): the same pull-down to -1 as a Shadow
    layer with Include Cast Shadows, so no fleck of light survives inside a cast shadow."""
    return (layer.layer_type == "NORMAL_LIGHT" and layer.light_polarity == "LIGHT"
            and layer.light_cast_shadow)


SHARED = "pl_shared"   # tree prop: the shared inputs a layer tree asked for, comma-separated


def shared_input(nb, name, socket_type, default):
    """An input of this LAYER tree that the stack computes ONCE for every layer that asks (§54,
    §59): the cast-shadow test, the key light's direction, the decoded normal map levels. None
    outside a layer tree."""
    gi = getattr(nb, "shared_cast_gi", None)
    if gi is None:
        return None
    if gi.outputs.get(name) is None:
        iface(nb.tree, 'INPUT', name, socket_type, default)
        names = [n for n in nb.tree.get(SHARED, "").split(",") if n]
        nb.tree[SHARED] = ",".join(names + [name])
    return gi.outputs[name]


def shared_names(tree):
    names = [n for n in (tree.get(SHARED, "") if tree is not None else "").split(",") if n]
    if tree is not None and tree.get("pl_uses_cast") and "Cast" not in names:   # (pre-0.23 trees)
        names.append("Cast")
    return names


def _cast_lit(nb, stack, node_name):
    """Inside a layer tree (live): the stack's ONE shared cast-shadow test, through the layer's
    "Cast" input - four copies of the Shader to RGB test cost ~2 s of shader compiling each (§54).
    Baked shadows read their texture right here (cheap)."""
    if not (stack.bake_variant and stack.bake_shadow_image is not None):
        s = shared_input(nb, "Cast", 'NodeSocketFloat', 1.0)
        if s is not None:
            return s
    return cast_test(nb, stack, node_name)


def _key_dir(nb):
    """Direction toward the key light at this point: the stack's one Key Light helper (§59)."""
    s = shared_input(nb, "KeyDir", 'NodeSocketVector', (0.0, 0.0, 1.0))
    if s is not None:
        return s
    pos = nb.node('ShaderNodeNewGeometry').outputs["Position"]
    return nb.group(blend_lib.key_light_group(), Position=pos).outputs["Direction"]


def cast_test(nb, stack, node_name, kl=None):
    """~1 where the key light arrives, ~0 in cast shadow and on faces turned away from the light
    (self-shadowed, as EEVEE's own shadows treat them; lit / expected-unshadowed).
    Live: Shader to RGB of a white diffuse. Baking: the Cycles direct-diffuse pass."""
    geo = nb.node('ShaderNodeNewGeometry')
    if kl is None:
        kl = nb.group(blend_lib.key_light_group(), Position=geo.outputs["Position"])
    ndl = nb.dot(geo.outputs["Normal"], kl.outputs["Direction"])
    if stack.bake_variant and stack.bake_shadow_image is not None:
        sh = nb.node('ShaderNodeTexImage', name=node_name, interpolation='Linear')
        nb.feed(sh.inputs[0], _uv(nb, stack))
        lum = nb.sep(sh.outputs["Color"])[0]
    else:
        diff = nb.node('ShaderNodeBsdfDiffuse')
        diff.inputs["Color"].default_value = (1, 1, 1, 1)
        nb.feed(diff.inputs["Normal"], geo.outputs["Normal"])
        s2r = nb.node('ShaderNodeShaderToRGB')
        nb.feed(s2r.inputs[0], diff.outputs[0])
        lum = nb.dot(s2r.outputs["Color"], blend_lib.LUMW)
    # the floor: where the surface turns edge-on to the light EEVEE lets a sliver of light through
    # its shadow (a bias against shadow acne); against a tiny expected value that read as fully lit,
    # and normal-map bumps then broke the sliver into lit specks inside cast shadows (§43)
    expected = nb.mul(nb.mul(kl.outputs["Strength"], nb.mx(ndl, GRAZE)), 1.05 / 3.14159265)
    # a firm decision, not the raw ratio: the World's ambient light (a few % of the sun) reads as
    # "partly lit" wherever the sun's own share is small (surfaces near edge-on), and a partial
    # value drew terminator bands and blotches inside cast shadows (§45)
    firm = nb.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
    nb.feed(firm.inputs["Value"], nb.div(lum, expected))
    firm.inputs["From Min"].default_value = CAST_LO
    firm.inputs["From Max"].default_value = CAST_HI
    return nb.mul(firm.outputs[0], nb.gt(ndl, 0.02))


MASK_INPUTS = (("Visible", 1.0), ("Opacity", 1.0), ("Threshold", 0.5), ("Softness", 0.08),
               ("Invert", 0.0), ("Detail", 0.35), ("Kind", 0.0), ("Correction", 0.5),
               ("NScale", 6.0), ("NDetail", 2.0), ("NRough", 0.5), ("NDistort", 0.0), ("NSeed", 0.0))


def depth(nb, stack, detail, node_name):
    """The creature's height (normal-derived, 0..1) at Detail 0..1 (walks the four detail radii)."""
    tex = nb.node('ShaderNodeTexImage', name=node_name, interpolation='Linear')
    if node_name.startswith("BASE"):
        tex.image = stack.height_image
    nb.feed(tex.inputs[0], _uv(nb, stack))
    r, gch, b = nb.sep(tex.outputs["Color"])
    a = tex.outputs["Alpha"]
    f = nb.mul(detail, 3.0)
    v = nb.mixf(nb.clamp(f), r, gch)
    v = nb.mixf(nb.clamp(nb.sub(f, 1.0)), v, b)
    return nb.mixf(nb.clamp(nb.sub(f, 2.0)), v, a)


def _noise_aspect(stack):
    """Generated coordinates are 0..1 per axis of the undeformed mesh's bounds: scale them back to
    the mesh's proportions (largest side = 1) so noise isn't stretched. Constant at compile."""
    mat = stack.id_data
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and any(s.material == mat for s in ob.material_slots):
            s = ob.data.texspace_size
            big = max(max(abs(c) for c in s), 1e-6)
            return tuple(abs(c) / big for c in s)
    return (1.0, 1.0, 1.0)


def _noise(nb, g, m, stack):
    tc = nb.node('ShaderNodeTexCoord')  # Generated = rest pose: the pattern doesn't swim when posed
    p = nb.v('MULTIPLY', tc.outputs["Generated"], _noise_aspect(stack))
    if m.noise_type == "CELLS":
        n = nb.node('ShaderNodeTexVoronoi', voronoi_dimensions='4D', feature='F1', normalize=True)
        nb.feed(n.inputs["Vector"], p)
        nb.feed(n.inputs["W"], g("NSeed"))
        nb.feed(n.inputs["Scale"], g("NScale"))
        nb.feed(n.inputs["Detail"], g("NDetail"))
        nb.feed(n.inputs["Roughness"], g("NRough"))
        # normalised F1 distance has its median near 0.3: rescale so Threshold 0.5 = half coverage
        return nb.clamp(nb.mul(n.outputs["Distance"], 1.0 / 0.6))
    n = nb.node('ShaderNodeTexNoise', noise_dimensions='4D')
    nb.feed(n.inputs["Vector"], p)
    nb.feed(n.inputs["W"], g("NSeed"))
    nb.feed(n.inputs["Scale"], g("NScale"))
    nb.feed(n.inputs["Detail"], g("NDetail"))
    nb.feed(n.inputs["Roughness"], g("NRough"))
    nb.feed(n.inputs["Distortion"], g("NDistort"))
    return n.outputs["Fac"]


def _mask_value(nb, gi, i, m, stack, self_h=0.5):
    """0..1 value of one mask element, before combining."""
    g = lambda n: gi.outputs[f"M{i} {n}"]
    if m.source == "DEPTH":
        if stack.height_image is None:
            return None
        v = depth(nb, stack, g("Detail"), f"M{i}.src")
        if m.correction is not None:
            corr = nb.node('ShaderNodeTexImage', name=f"M{i}.corr", interpolation='Linear')
            nb.feed(corr.inputs[0], _uv(nb, stack))
            c = nb.sep(nb.group(blend_lib.to_srgb_group(), Color=corr.outputs["Color"]).outputs[0])[0]
            v = nb.add(v, nb.mul(nb.sub(c, 0.5), g("Correction")))  # white pushes up, black down
    elif m.source == "CURVATURE":
        if stack.curvature_image is None:
            return None
        tex = nb.node('ShaderNodeTexImage', name=f"M{i}.src", interpolation='Linear')
        nb.feed(tex.inputs[0], _uv(nb, stack))
        r, gch, b = nb.sep(tex.outputs["Color"])
        a = tex.outputs["Alpha"]
        fine = nb.mixf(g("Kind"), r, gch)
        broad = nb.mixf(g("Kind"), b, a)
        v = nb.mixf(g("Detail"), fine, broad)
    elif m.source in ("SHADOW", "TERMINATOR"):
        geo = nb.node('ShaderNodeNewGeometry')
        ndl = nb.dot(geo.outputs["Normal"], _key_dir(nb))
        if m.source == "TERMINATOR":
            v = nb.add(nb.mul(ndl, 0.5), 0.5)   # 0.5 = the terminator
        else:
            # (assumes the key light dominates: other lights also count as "lit")
            v = _cast_lit(nb, stack, f"M{i}.shadow")
    elif m.source == "HEIGHT":
        # 0.5 where this layer's height equals the height beneath; Threshold shifts the level
        v = nb.add(nb.mul(nb.sub(self_h, gi.outputs["UnderH"]), 0.5), 0.5)
    elif m.source == "NOISE":
        v = _noise(nb, g, m, stack)
    elif m.source == "PAINT":  # painted directly: the value IS the mask (display grey = %)
        if m.image is None:
            return None
        tex = nb.node('ShaderNodeTexImage', name=f"M{i}.src", interpolation='Linear')
        nb.feed(tex.inputs[0], _uv(nb, stack))
        v = nb.sep(nb.group(blend_lib.to_srgb_group(), Color=tex.outputs["Color"]).outputs[0])[0]
        return nb.mixf(g("Invert"), v, nb.sub(1.0, v))
    else:  # IMAGE
        tex = nb.node('ShaderNodeTexImage', name=f"M{i}.src", interpolation='Linear')
        nb.feed(tex.inputs[0], _uv(nb, stack))
        v = nb.dot(tex.outputs["Color"], blend_lib.LUMW)
    mr = nb.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
    nb.feed(mr.inputs["Value"], v)
    nb.feed(mr.inputs["From Min"], nb.sub(g("Threshold"), g("Softness")))
    nb.feed(mr.inputs["From Max"], nb.add(g("Threshold"), nb.mx(g("Softness"), 1e-4)))
    val = mr.outputs[0]
    return nb.mixf(g("Invert"), val, nb.sub(1.0, val))


def _combine(nb, op, a, b):
    if op == "MULTIPLY":
        return nb.mul(a, b)
    if op == "ADD":
        return nb.clamp(nb.add(a, b))
    if op == "SUBTRACT":
        return nb.clamp(nb.sub(a, b))
    if op == "MAX":
        return nb.mx(a, b)
    if op == "MIN":
        return nb.mn(a, b)
    lo = nb.mul(2.0, nb.mul(a, b))  # OVERLAY
    hi = nb.sub(1.0, nb.mul(2.0, nb.mul(nb.sub(1.0, a), nb.sub(1.0, b))))
    return nb.sel(nb.lt(a, 0.5), lo, hi)


def _masks(nb, gi, layer, stack, self_h=0.5):
    """Combined mask of the layer (socket), or None when it has no (working) masks."""
    m_acc = None
    for i, m in enumerate(layer.masks):
        v = _mask_value(nb, gi, i, m, stack, self_h)
        if v is None:
            continue
        base = 1.0 if m_acc is None else m_acc
        combined = _combine(nb, m.op, base, v)
        amt = nb.mul(gi.outputs[f"M{i} Visible"], gi.outputs[f"M{i} Opacity"])
        m_acc = nb.mixf(amt, base, combined)
    return m_acc


# ----------------------------------------------------------------------------- preservation

def _snapshot(tree):
    snap = {}
    if tree is None:
        return snap
    for n in tree.nodes:
        if n.type == 'VALTORGB':
            snap[n.name] = ("ramp", [(e.position, tuple(e.color)) for e in n.color_ramp.elements])
        elif n.type == 'CURVE_RGB':
            snap[n.name] = ("curves", [[(p.location[0], p.location[1], p.handle_type)
                                        for p in c.points] for c in n.mapping.curves])
    return snap


def _restore(tree, snap):
    for name, (kind, data) in snap.items():
        n = tree.nodes.get(name)
        if n is None:
            continue
        if kind == "ramp":
            set_ramp(n.color_ramp, data)
        elif kind == "curves":
            for curve, pts in zip(n.mapping.curves, data):
                while len(curve.points) > len(pts):
                    curve.points.remove(curve.points[-1])
                while len(curve.points) < len(pts):
                    curve.points.new(0.5, 0.5)
                for p, (x, y, h) in zip(curve.points, pts):
                    p.location = (x, y)
                    p.handle_type = h
            n.mapping.update()


def set_ramp(ramp, stops):
    els = ramp.elements
    while len(els) > len(stops):
        els.remove(els[-1])
    while len(els) < len(stops):
        els.new(0.5)
    for e, (pos, col) in zip(els, stops):
        e.position = pos
        e.color = col


BI_DEFAULT = [(0.0, (0, 0, 0, 1)), (0.0, (1, 1, 1, 1)), (1.0, (1, 1, 1, 1)), (1.0, (0, 0, 0, 1))]
BI_COLOURS = [(0, 0, 0, 1), (1, 1, 1, 1), (1, 1, 1, 1), (0, 0, 0, 1)]


def bi_is_default_stops(stops):
    return len(stops) == 4 and all(abs(s[0] - p) < 1e-4 for s, (p, _c) in zip(stops, BI_DEFAULT))


def normalise_blend_if_ramp(ramp):
    """Keep a Blend-If ramp meaning 'black, white, white, black' whatever stop the user dragged.

    Elements are always sorted by position, so recolouring by index restores Photoshop's
    semantics: stops 0-1 = shadow split handles, stops 2-3 = highlight split handles.
    Returns True if anything changed.
    """
    els = ramp.elements
    changed = False
    if len(els) != 4:
        pos = sorted(e.position for e in els)
        pos = (pos + [1.0] * 4)[:4] if len(pos) < 4 else [pos[0], pos[1], pos[-2], pos[-1]]
        set_ramp(ramp, list(zip(pos, BI_COLOURS)))
        changed = True
    for e, col in zip(els, BI_COLOURS):
        if tuple(round(c, 4) for c in e.color) != col:
            e.color = col
            changed = True
    if ramp.interpolation != 'LINEAR':
        ramp.interpolation = 'LINEAR'
        changed = True
    return changed


# ----------------------------------------------------------------------------- pieces

def _uv(nb, stack):
    return nb.node('ShaderNodeUVMap', uv_map=stack.uv_map).outputs[0]


def _projection(nb, gi, layer, stack):
    """Texture coordinates of an image Fill (UV or Box) + the tiling-break copy and its blend."""
    if layer.projection == "BOX":
        tc = nb.node('ShaderNodeTexCoord')  # rest pose, in the mesh's proportions
        base = nb.v('MULTIPLY', tc.outputs["Generated"], _noise_aspect(stack))
    else:
        base = _uv(nb, stack)
    centred = nb.v('SUBTRACT', base, (0.5, 0.5, 0.0))
    rot = nb.node('ShaderNodeVectorRotate', rotation_type='Z_AXIS')
    nb.feed(rot.inputs["Vector"], centred)
    nb.feed(rot.inputs["Angle"], gi.outputs["TexRot"])
    p = nb.vscale(rot.outputs["Vector"], gi.outputs["TexScale"])
    p = nb.v('ADD', p, nb.comb(nb.add(gi.outputs["TexOffX"], 0.5), nb.add(gi.outputs["TexOffY"], 0.5), 0.0))
    out = {"P": p, "P2": None, "W": None, "BOX": layer.projection == "BOX"}
    if layer.tile_break > 0:
        rot2 = nb.node('ShaderNodeVectorRotate', rotation_type='Z_AXIS')
        rot2.inputs["Angle"].default_value = 1.37
        nb.feed(rot2.inputs["Vector"], p)
        out["P2"] = nb.v('ADD', rot2.outputs["Vector"], (0.37, 0.61, 0.23))
        noise = nb.node('ShaderNodeTexNoise', noise_dimensions='3D')
        nb.feed(noise.inputs["Vector"], p)
        nb.feed(noise.inputs["Scale"], gi.outputs["BreakFreq"])
        noise.inputs["Detail"].default_value = 1.0
        mr = nb.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
        nb.feed(mr.inputs["Value"], noise.outputs["Fac"])
        mr.inputs["From Min"].default_value = 0.42
        mr.inputs["From Max"].default_value = 0.58
        out["W"] = nb.mul(mr.outputs[0], gi.outputs["Break"])
    return out


def _projected(nb, proj, name):
    """(colour, alpha) of the image node `name` through the projection (raw texture colour)."""
    def one(n, vec):
        tex = nb.node('ShaderNodeTexImage', name=n, interpolation='Linear')
        if proj["BOX"]:
            tex.projection = 'BOX'
        nb.feed(tex.inputs[0], vec)
        return tex.outputs["Color"], tex.outputs["Alpha"]
    c, a = one(name, proj["P"])
    if proj["P2"] is not None:
        c2, a2 = one(name + "#2", proj["P2"])
        c, a = nb.mixc(proj["W"], c, c2), nb.mixf(proj["W"], a, a2)
    return c, a


def _image_source(nb, stack, name, proj=None):
    if proj is not None:
        col, a = _projected(nb, proj, name)
        if stack.blend_space == "SRGB":
            col = nb.group(blend_lib.to_srgb_group(), Color=col).outputs[0]
        return col, a
    return _image_source_uv(nb, stack, name)


def _image_source_uv(nb, stack, name):
    tex = nb.node('ShaderNodeTexImage', name=name, interpolation='Linear')
    nb.feed(tex.inputs[0], _uv(nb, stack))
    col = tex.outputs["Color"]
    if stack.blend_space == "SRGB":
        col = nb.group(blend_lib.to_srgb_group(), Color=col).outputs[0]
    return col, tex.outputs["Alpha"]


def bi_is_default(ramp):
    els = ramp.color_ramp.elements if hasattr(ramp, "color_ramp") else ramp.elements
    return len(els) == 4 and all(abs(e.position - p) < 1e-4 for e, (p, _c) in zip(els, BI_DEFAULT))


def _blend_if(nb, cs, under, on=True):
    """Product of the 8 Blend-If ramps (This Layer / Underlying x Grey, R, G, B). Off (§59): the
    ramps are still there for the panel (and keep your stops), but not wired in: an unconnected
    node costs nothing to compile. Returns None then (weight 1)."""
    if not on:
        for which in ("this", "under"):
            for ch in BI_CHANNELS:
                ramp = nb.node('ShaderNodeValToRGB', name=f"BI.{which}.{ch}", label=f"Blend If {which} {ch}")
                set_ramp(ramp.color_ramp, BI_DEFAULT)
                ramp.color_ramp.interpolation = 'LINEAR'
        return None
    w = None
    for which, col in (("this", cs), ("under", under)):
        r, g, b = nb.sep(col)
        vals = {"GREY": nb.dot(col, blend_lib.LUMW), "R": r, "G": g, "B": b}
        for ch in BI_CHANNELS:
            v = nb.m('MULTIPLY_ADD', vals[ch], 1 - 2 * BI_EPS, BI_EPS)
            ramp = nb.node('ShaderNodeValToRGB', name=f"BI.{which}.{ch}",
                           label=f"Blend If {which} {ch}")
            set_ramp(ramp.color_ramp, BI_DEFAULT)
            ramp.color_ramp.interpolation = 'LINEAR'
            nb.feed(ramp.inputs[0], v)
            out = ramp.outputs["Color"]  # black/white ramp -> grey value = weight
            w = out if w is None else nb.mul(w, out)
    return w


def _xy_to_normal(nb, x, y):
    """Encoded tangent XY (0..1) -> encoded tangent normal colour, z rebuilt."""
    xs, ys = nb.sub(nb.mul(x, 2.0), 1.0), nb.sub(nb.mul(y, 2.0), 1.0)
    z = nb.m('SQRT', nb.mx(nb.sub(1.0, nb.add(nb.mul(xs, xs), nb.mul(ys, ys))), 0.0))
    return nb.comb(x, y, nb.add(nb.mul(z, 0.5), 0.5))


FORM_IMAGES = ("SRC.forms_a", "SRC.forms_b", "SRC.forms_c")


def _has_forms(stack):
    return bool(stack.forms_a and stack.forms_b and stack.forms_c)


N_LEVELS = 7   # the normal map + 6 Form Size levels (finest first)


def normal_levels(nb, stack):
    """The normal map's encoded colour and its 6 Form Size levels, read and decoded ONCE: in the
    stack, shared by every light layer (§59: each layer used to read 4 images and rebuild 6
    levels itself, ~90 nodes a layer). Images are set here (the stack is rebuilt when they change)."""
    tex = nb.node('ShaderNodeTexImage', name="SRC.normal", interpolation='Linear')
    tex.image = stack.normal_image
    nb.feed(tex.inputs[0], _uv(nb, stack))
    levels = [tex.outputs["Color"]]
    if _has_forms(stack):
        for nm_, img in zip(FORM_IMAGES, (stack.forms_a, stack.forms_b, stack.forms_c)):
            t = nb.node('ShaderNodeTexImage', name=nm_, interpolation='Linear')
            t.image = img
            nb.feed(t.inputs[0], _uv(nb, stack))
            r, g, b = nb.sep(t.outputs["Color"])
            levels += [_xy_to_normal(nb, r, g), _xy_to_normal(nb, b, t.outputs["Alpha"])]
    return levels


def _normal(nb, stack, gi=None):
    """Shading normal for light layers: the normal map, blurred by Form Size (6 levels, finest
    first), at Normal Strength. The levels come from the stack (normal_levels)."""
    if stack.normal_image:
        col = shared_input(nb, "NLev0", 'NodeSocketColor', (0.5, 0.5, 1.0, 1.0))
        if col is None:   # (outside a layer tree)
            lv = normal_levels(nb, stack)
            col, rest = lv[0], lv[1:]
        else:
            rest = [shared_input(nb, f"NLev{k}", 'NodeSocketColor', (0.5, 0.5, 1.0, 1.0))
                    for k in range(1, N_LEVELS)] if _has_forms(stack) else []
        if gi is not None and rest:
            levels = rest
            f = nb.mul(gi.outputs["FormSize"], float(len(levels)))  # 0 = sharp ... 1 = broadest
            for k, lv in enumerate(levels):
                col = nb.mixc(nb.clamp(nb.sub(f, float(k))), col, lv)
        nm = nb.node('ShaderNodeNormalMap', space='TANGENT', uv_map=stack.uv_map)
        nb.feed(nm.inputs["Color"], col)
        if gi is not None:
            nb.feed(nm.inputs["Strength"], gi.outputs["NStrength"])
        return nm.outputs["Normal"]
    return nb.node('ShaderNodeNewGeometry').outputs["Normal"]


def _light_dir(nb, gi):
    key = _key_dir(nb)
    own = nb.v('NORMALIZE', gi.outputs["Direction"])
    return nb.v('NORMALIZE', nb.mixv(gi.outputs["Override"], key, own))


def _breakup(nb, gi, layer, stack, val):
    if layer.breakup == "NOISE":
        noise = nb.node('ShaderNodeTexNoise')
        noise.inputs["Detail"].default_value = 4.0
        pos = nb.node('ShaderNodeNewGeometry').outputs["Position"]
        nb.feed(noise.inputs["Vector"], nb.vscale(pos, gi.outputs["BreakScale"]))
        b = noise.outputs["Fac"]
    elif layer.breakup == "IMAGE":
        tex = nb.node('ShaderNodeTexImage', name="LIGHT.breakup", interpolation='Linear')
        nb.feed(tex.inputs[0], nb.vscale(_uv(nb, stack), gi.outputs["BreakScale"]))
        b = nb.dot(tex.outputs["Color"], blend_lib.LUMW)
    else:
        return val
    return nb.add(val, nb.mul(nb.sub(b, 0.5), gi.outputs["BreakStrength"]))


def _classic_light(nb, gi, layer, stack, t, N, V, val):
    """Threshold / Softness / terminator-band light layers (the pre-§52 controls)."""
    band = None
    shadow = layer.light_polarity == "SHADOW" and t not in ("RIM_LIGHT", "SSS_LIGHT")
    pinned = False   # cast shadows + the side turned away pinned to -1
    if (shadow and layer.include_cast_shadow) or blocked_light(layer):
        # like the old toon shader's ramp on (N.L x shadow): cast shadow, and the side
        # of the mesh turned away from the light, pull the value down to fully dark, so
        # the shadow AND its terminator band follow those edges: no band or lit fleck
        # from normal-map bumps inside a shadow
        pinned = True
        val = nb.mixf(_cast_lit(nb, stack, "LIGHT.shadow"), -1.0, val)
    shaped = _shape(nb, gi, val)
    if shadow:
        # the side the light doesn't reach, with an optional coloured terminator band
        # along the edge, like the old shadow colour ramp
        shaped = nb.sub(1.0, shaped)
        # like a colour ramp on the light value: the band sits around Threshold and fades
        # out both ways wherever the light value has a gradient (§51). With cast shadows the
        # value is pinned to -1 in cast shadow and on the side turned away: the band never
        # fills that flat area (a wide band would otherwise tint the whole shadow).
        W = gi.outputs["TermWidth"]
        dist = nb.m('ABSOLUTE', nb.sub(val, gi.outputs["Threshold"]))
        band = nb.sub(1.0, nb.clamp(nb.div(dist, W)))
        if pinned:
            band = nb.mul(band, nb.clamp(nb.div(nb.add(val, 1.0), 0.08)))
        band = nb.mul(band, nb.gt(W, 1e-4))
    if t == "RIM_LIGHT" and layer.rim_reflect:
        # stylised reflection: the colour of the "world" the surface reflects, from a
        # ground (below) -> horizon -> sky (above) gradient on the reflected direction
        R = nb.v('SUBTRACT', nb.vscale(N, nb.mul(2.0, nb.dot(N, V))), V)
        rz = nb.sepxyz(R)[2]
        sky = nb.node('ShaderNodeValToRGB', name="RIM.sky", label="Reflection: ground -> sky")
        set_ramp(sky.color_ramp, [(0.0, (0.10, 0.07, 0.04, 1)), (0.45, (0.55, 0.5, 0.42, 1)),
                                  (0.55, (0.85, 0.9, 1.0, 1)), (1.0, (0.35, 0.55, 0.95, 1))])
        nb.feed(sky.inputs[0], nb.add(nb.mul(rz, 0.5), 0.5))
        cs = sky.outputs["Color"]
        if stack.blend_space == "SRGB":
            cs = nb.group(blend_lib.to_srgb_group(), Color=cs).outputs[0]
        a_src = shaped
    elif layer.use_ramp:
        ramp = nb.node('ShaderNodeValToRGB', name="LIGHT.ramp", label="Light ramp")
        set_ramp(ramp.color_ramp, [(0.0, (1, 0.85, 0.6, 0)), (1.0, (1, 0.85, 0.6, 1))])
        nb.feed(ramp.inputs[0], shaped)
        cs = ramp.outputs["Color"]
        if stack.blend_space == "SRGB":
            cs = nb.group(blend_lib.to_srgb_group(), Color=cs).outputs[0]
        a_src = ramp.outputs["Alpha"]
    else:
        cs, a_src = gi.outputs["Color"], shaped
    if band is not None:
        cs = nb.mixc(band, cs, gi.outputs["TermColor"])
        a_src = nb.mx(a_src, band)
    return cs, a_src


def _subsurface(nb, gi, layer, stack, N, L, V):
    """0..1 stylised subsurface value (§36).
    GLOW: a band hugging the terminator: 1 right at it, fading over Glow Width into the shadow and
    half that onto the lit side (light bleeding into the shadow); with cast shadows the light term
    is pulled to dark in cast shadow first, so cast-shadow edges glow too.
    TRANSLUCENT: light passing through the model towards the camera (V . -(L + N x distortion))^focus,
    x thinness from the baked thickness map (1 everywhere until it is baked)."""
    if layer.sss_mode == "TRANSLUCENT":
        through = nb.v('NORMALIZE', nb.v('ADD', L, nb.vscale(N, gi.outputs["SSSDistort"])))
        b = nb.m('POWER', nb.clamp(nb.dot(V, nb.v('SCALE', through, scale=-1.0))), gi.outputs["SSSPower"])
        if stack.thickness_image is not None:
            tex = nb.node('ShaderNodeTexImage', name="SSS.thick", interpolation='Linear')
            nb.feed(tex.inputs[0], _uv(nb, stack))
            b = nb.mul(b, nb.sep(tex.outputs["Color"])[0])
        return b
    d = nb.dot(N, L)
    if layer.include_cast_shadow:
        d = nb.mixf(_cast_lit(nb, stack, "LIGHT.shadow"), -1.0, d)
    w = nb.mx(gi.outputs["SSSWidth"], 1e-3)
    into_shadow = nb.clamp(nb.add(1.0, nb.div(nb.mn(d, 0.0), w)))          # 1 at the edge -> 0 at -width
    into_light = nb.clamp(nb.sub(1.0, nb.div(nb.mx(d, 0.0), nb.mul(w, 0.5))))  # half as far onto the lit side
    return nb.mul(into_shadow, into_light)


def _shape(nb, gi, value):
    """threshold/softness smoothstep, then optional posterise."""
    mr = nb.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
    nb.feed(mr.inputs["Value"], value)
    nb.feed(mr.inputs["From Min"], nb.sub(gi.outputs["Threshold"], gi.outputs["Softness"]))
    nb.feed(mr.inputs["From Max"], nb.add(gi.outputs["Threshold"], nb.mx(gi.outputs["Softness"], 1e-4)))
    v = mr.outputs[0]
    bands = gi.outputs["Bands"]
    post = nb.div(nb.m('FLOOR', nb.m('MULTIPLY_ADD', v, bands, 0.5)), nb.mx(bands, 1.0))
    return nb.sel(nb.gt(bands, 0.5), post, v)


# ----------------------------------------------------------------------------- build

def build(layer, stack):
    """A FRESH tree every time (§55): Blender's threaded material preview may be copying the old
    one right now, so it is never edited in place - it's retired and deleted once no preview runs."""
    from . import retire
    old = layer.node_tree
    snap = _snapshot(old)
    if not layer.blend_if and any(k.startswith("BI.") and not bi_is_default_stops(v[1])
                                  for k, v in snap.items() if v[0] == "ramp"):
        from .. import props
        with props.suspended():   # Blend If used before 0.23 (always wired then): keep it on
            layer.blend_if = True
    tree = bpy.data.node_groups.new(TREE_PREFIX + layer.uid, 'ShaderNodeTree')
    try:
        _build_into(layer, stack, tree, snap)
    except Exception:
        bpy.data.node_groups.remove(tree)   # (never used: the layer keeps its current tree)
        raise
    layer.node_tree = tree
    if old is not None:
        retire(old)                          # only once the new one is complete
    return tree


def _build_into(layer, stack, tree, snap):
    t = layer.layer_type

    iface(tree, 'OUTPUT', "Out", 'NodeSocketColor')
    iface(tree, 'OUTPUT', "OutA", 'NodeSocketFloat')
    iface(tree, 'OUTPUT', "OutH", 'NodeSocketFloat')
    iface(tree, 'INPUT', "Under", 'NodeSocketColor', (0, 0, 0, 1))
    iface(tree, 'INPUT', "UnderA", 'NodeSocketFloat', 0.0)
    iface(tree, 'INPUT', "UnderH", 'NodeSocketFloat', 0.5)
    hsrc = layer.height_source if t in ("FILL", "PAINT") else "NONE"
    if hsrc == "IMAGE" and layer.height_image is None:
        hsrc = "FLAT"
    iface(tree, 'INPUT', "HLevel", 'NodeSocketFloat', 0.5)
    iface(tree, 'INPUT', "HStrength", 'NodeSocketFloat', 1.0)
    iface(tree, 'INPUT', "Opacity", 'NodeSocketFloat', 1.0, 0, 1)
    adjusted = colour_adjusted(layer)
    if adjusted:
        for n, d in (("LA Hue", 0.0), ("LA Sat", 1.0), ("LA Val", 1.0)):
            iface(tree, 'INPUT', n, 'NodeSocketFloat', d)
    iface(tree, 'INPUT', "Visible", 'NodeSocketFloat', 1.0, 0, 1)
    if t == "GROUP":
        iface(tree, 'INPUT', "Content", 'NodeSocketColor', (0, 0, 0, 1))
        iface(tree, 'INPUT', "ContentA", 'NodeSocketFloat', 0.0)
        iface(tree, 'INPUT', "ContentH", 'NodeSocketFloat', 0.5)
    elif t == "FILL" and layer.fill_source == "COLOR":
        iface(tree, 'INPUT', "Color", 'NodeSocketColor', (0.5, 0.5, 0.5, 1))
    elif t == "FILL":
        for n, d in (("TexScale", 1.0), ("TexRot", 0.0), ("TexOffX", 0.0), ("TexOffY", 0.0),
                     ("Break", 0.0), ("BreakFreq", 0.5)):
            iface(tree, 'INPUT', n, 'NodeSocketFloat', d)
    elif t == "ADJUST":
        k = layer.adjust_kind
        if k == "HUE_SAT":
            for n in ("Hue", "Saturation", "Lightness"):
                iface(tree, 'INPUT', n, 'NodeSocketFloat', 0.0)
        elif k == "LEVELS":
            for n, d in (("InBlack", 0.0), ("InWhite", 1.0), ("Gamma", 1.0), ("OutBlack", 0.0), ("OutWhite", 1.0)):
                iface(tree, 'INPUT', n, 'NodeSocketFloat', d)
        elif k == "BRIGHT_CONTRAST":
            iface(tree, 'INPUT', "Bright", 'NodeSocketFloat', 0.0)
            iface(tree, 'INPUT', "Contrast", 'NodeSocketFloat', 0.0)
    elif t in LIGHT_TYPES:
        iface(tree, 'INPUT', "Color", 'NodeSocketColor', (1, 1, 1, 1))
        iface(tree, 'INPUT', "Threshold", 'NodeSocketFloat', 0.2)
        iface(tree, 'INPUT', "Softness", 'NodeSocketFloat', 0.15)
        iface(tree, 'INPUT', "Bands", 'NodeSocketFloat', 0.0)
        iface(tree, 'INPUT', "Tightness", 'NodeSocketFloat', 40.0)
        iface(tree, 'INPUT', "Override", 'NodeSocketFloat', 0.0)
        iface(tree, 'INPUT', "Direction", 'NodeSocketVector', (0, 0, 1))
        iface(tree, 'INPUT', "FormSize", 'NodeSocketFloat', 0.0)
        iface(tree, 'INPUT', "NStrength", 'NodeSocketFloat', 1.0)
        iface(tree, 'INPUT', "BreakStrength", 'NodeSocketFloat', 0.3)
        iface(tree, 'INPUT', "BreakScale", 'NodeSocketFloat', 8.0)
        iface(tree, 'INPUT', "TermColor", 'NodeSocketColor', (0, 0, 0, 1))
        iface(tree, 'INPUT', "TermWidth", 'NodeSocketFloat', 0.0)
        iface(tree, 'INPUT', "SSSWidth", 'NodeSocketFloat', 0.35)
        iface(tree, 'INPUT', "SSSDistort", 'NodeSocketFloat', 0.3)
        iface(tree, 'INPUT', "SSSPower", 'NodeSocketFloat', 3.0)
    for i in range(len(layer.masks)):
        for n, d in MASK_INPUTS:
            iface(tree, 'INPUT', f"M{i} {n}", 'NodeSocketFloat', d)
    iface(tree, 'OUTPUT', "Mask", 'NodeSocketFloat')

    nb = NB(tree)
    gi = nb.node('NodeGroupInput')
    go = nb.node('NodeGroupOutput')
    nb.shared_cast_gi = gi
    under, under_a = gi.outputs["Under"], gi.outputs["UnderA"]
    vis = nb.mul(gi.outputs["Opacity"], gi.outputs["Visible"])
    # the layer's own colour first (its brightness can be its height)
    src = proj = None
    if t == "FILL" and layer.fill_source == "COLOR":
        src = gi.outputs["Color"], 1.0
    elif t == "FILL":
        proj = _projection(nb, gi, layer, stack)
        src = _image_source(nb, stack, "SRC.image", proj)
    elif t == "PAINT":
        src = _image_source(nb, stack, "SRC.image")
    # the layer's height (Height Blend compares it with the height beneath: UnderH)
    level = gi.outputs["HLevel"]
    if hsrc == "IMAGE":
        if proj is not None:   # same projection (and tiling break) as the colour
            hval = nb.dot(_projected(nb, proj, "H.image")[0], blend_lib.LUMW)
        else:
            htex = nb.node('ShaderNodeTexImage', name="H.image", interpolation='Linear')
            nb.feed(htex.inputs[0], _uv(nb, stack))
            hval = nb.dot(htex.outputs["Color"], blend_lib.LUMW)
        self_h = nb.add(level, nb.mul(nb.sub(hval, 0.5), gi.outputs["HStrength"]))
    elif hsrc == "LUMINANCE":
        hval = nb.dot(src[0], blend_lib.LUMW)
        self_h = nb.add(level, nb.mul(nb.sub(hval, 0.5), gi.outputs["HStrength"]))
    else:
        self_h = level
    mask = _masks(nb, gi, layer, stack, self_h)
    nb.feed(go.inputs["Mask"], mask if mask is not None else 1.0)
    if mask is not None:
        vis = nb.mul(vis, mask)

    under_h = gi.outputs["UnderH"]
    if t == "GROUP":
        nb.feed(go.inputs["OutH"], nb.mixf(vis, under_h, gi.outputs["ContentH"]))
    if t == "GROUP" and layer.group_mode == "PASS_THROUGH":
        content = _colour_adjust(nb, gi, layer, gi.outputs["Content"]) if adjusted else gi.outputs["Content"]
        nb.feed(go.inputs["Out"], nb.mixc(vis, under, content))
        nb.feed(go.inputs["OutA"], nb.mixf(vis, under_a, gi.outputs["ContentA"]))
    else:
        if t == "GROUP":
            cs, a_src = gi.outputs["Content"], gi.outputs["ContentA"]
        elif src is not None:
            cs, a_src = src
        elif t == "ADJUST":
            cs, a_src = _adjust(nb, gi, layer.adjust_kind, under), 1.0
        else:
            L = _light_dir(nb, gi)
            V = None
            if t in ("SPEC_LIGHT", "RIM_LIGHT", "SSS_LIGHT"):
                geo = nb.node('ShaderNodeNewGeometry')
                if stack.bake_variant:  # Cycles bakes have no camera ray: use the scene camera
                    cam = nb.node('ShaderNodeAttribute', attribute_type='VIEW_LAYER', attribute_name="pl_cam_loc")
                    V = nb.v('NORMALIZE', nb.v('SUBTRACT', cam.outputs["Vector"], geo.outputs["Position"]))
                else:
                    V = geo.outputs["Incoming"]
                H = nb.v('NORMALIZE', nb.v('ADD', L, V))

            def lighting(N):
                if t == "NORMAL_LIGHT":
                    return nb.dot(N, L)
                if t == "RIM_LIGHT":   # fresnel: 0 facing the camera -> 1 edge-on
                    return nb.sub(1.0, nb.clamp(nb.dot(N, V)))
                if t == "SSS_LIGHT":
                    return _subsurface(nb, gi, layer, stack, N, L, V)
                s = nb.m('POWER', nb.mx(nb.dot(N, H), 0.0), gi.outputs["Tightness"])
                return nb.mul(s, nb.gt(nb.dot(N, L), 0.0))  # never light faces turned away

            N = _normal(nb, stack, gi)
            val = lighting(N)
            val = _breakup(nb, gi, layer, stack, val)
            band = None
            if t == "NORMAL_LIGHT" and layer.light_ramp:
                # Light Ramp (§52): the old toon setup - a colour ramp on the light that arrives
                # (N.L x cast shadow, 0..1). Shadow, terminator, highlight: just stops on the ramp.
                if layer.include_cast_shadow:
                    val = nb.mixf(_cast_lit(nb, stack, "LIGHT.shadow"), -1.0, val)
                ramp = nb.node('ShaderNodeValToRGB', name=LIGHT_RAMP, label="Light ramp")
                set_ramp(ramp.color_ramp, LIGHT_RAMP_STARTS.get(layer.light_ramp_start, LIGHT_RAMP_DEFAULT))
                nb.feed(ramp.inputs[0], nb.clamp(val))
                cs = ramp.outputs["Color"]
                if stack.blend_space == "SRGB":
                    cs = nb.group(blend_lib.to_srgb_group(), Color=cs).outputs[0]
                a_src = ramp.outputs["Alpha"]
            else:
                cs, a_src = _classic_light(nb, gi, layer, stack, t, N, V, val)
            # the flat-colour view (C, Z picker) and the Form View (Shift+C) show paint only, never light
            flat = nb.node('ShaderNodeAttribute', attribute_type='VIEW_LAYER', attribute_name="pl_base_view")
            form = nb.node('ShaderNodeAttribute', attribute_type='VIEW_LAYER', attribute_name="pl_form_view")
            a_src = nb.mul(a_src, nb.sub(1.0, nb.clamp(nb.mx(flat.outputs["Fac"], form.outputs["Fac"]))))
        if adjusted:
            cs = _colour_adjust(nb, gi, layer, cs)
        w = _blend_if(nb, cs, under, layer.blend_if)
        if w is not None:
            vis = nb.mul(vis, w)
        as_ = nb.mul(vis, a_src) if not isinstance(a_src, float) else vis
        bl = nb.group(blend_lib.blend_group(layer.blend_mode), name="BLEND",
                      Cb=under, Ab=under_a, Cs=cs, As=as_)
        nb.feed(go.inputs["Out"], bl.outputs["Co"])
        nb.feed(go.inputs["OutA"], bl.outputs["Ao"])
        if t != "GROUP":
            # height composites like colour (Normal) where the layer shows; layers without a
            # height leave it alone
            nb.feed(go.inputs["OutH"], under_h if hsrc == "NONE" else nb.mixf(as_, under_h, self_h))

    _restore(tree, snap)
    tree["pl_sig"] = signature(layer, stack)


def _adjust(nb, gi, kind, under):
    if kind == "HUE_SAT":
        hsv = nb.node('ShaderNodeHueSaturation')
        nb.feed(hsv.inputs["Color"], under)
        nb.feed(hsv.inputs["Hue"], nb.add(0.5, nb.div(gi.outputs["Hue"], 360.0)))
        nb.feed(hsv.inputs["Saturation"], nb.mx(0.0, nb.add(1.0, nb.div(gi.outputs["Saturation"], 100.0))))
        c = hsv.outputs[0]
        light = nb.div(gi.outputs["Lightness"], 100.0)
        target = nb.gt(light, 0.0)  # towards white (+) or black (-), like Photoshop
        return nb.mixc(nb.m('ABSOLUTE', light), c, target)
    if kind == "LEVELS":
        def lv(nb, c):
            v = nb.clamp(nb.div(nb.sub(c, gi.outputs["InBlack"]),
                                nb.sub(gi.outputs["InWhite"], gi.outputs["InBlack"])))
            v = nb.m('POWER', v, nb.div(1.0, gi.outputs["Gamma"]))
            return nb.add(gi.outputs["OutBlack"], nb.mul(v, nb.sub(gi.outputs["OutWhite"], gi.outputs["OutBlack"])))
        return nb.per_channel(lv, under)
    if kind == "BRIGHT_CONTRAST":
        bc = nb.node('ShaderNodeBrightContrast')
        nb.feed(bc.inputs["Color"], under)
        nb.feed(bc.inputs["Bright"], gi.outputs["Bright"])
        nb.feed(bc.inputs["Contrast"], gi.outputs["Contrast"])
        return bc.outputs[0]
    # CURVES: edited directly through the node's curve widget in the layer panel
    cv = nb.node('ShaderNodeRGBCurve', name="ADJ.curves")
    nb.feed(cv.inputs["Color"], under)
    return cv.outputs[0]


def _decode(c):
    return tuple(x / 12.92 if x < 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def values(layer, stack):
    """Socket values for the layer's instance node (pushed without rebuilding).

    Colour props are COLOR_GAMMA (what the picker shows); in Linear blend space decode them.
    """
    col = (lambda c: (*c, 1.0)) if stack.blend_space == "SRGB" else (lambda c: (*_decode(c), 1.0))
    v = {"LA Hue": layer.la_hue, "LA Sat": layer.la_saturation, "LA Val": layer.la_value,
         "Opacity": layer.opacity, "Visible": 1.0 if layer.visible else 0.0,
         "HLevel": layer.height_level, "HStrength": layer.height_strength}
    t = layer.layer_type
    if t == "FILL" and layer.fill_source == "COLOR":
        v["Color"] = col(layer.fill_color)
    elif t == "FILL":
        v.update(TexScale=layer.tex_scale, TexRot=layer.tex_rotation, TexOffX=layer.tex_offset[0],
                 TexOffY=layer.tex_offset[1], Break=layer.tile_break,
                 BreakFreq=1.0 / max(layer.tile_break_size, 1e-3))
    elif t == "ADJUST":
        k = layer.adjust_kind
        if k == "HUE_SAT":
            v.update(Hue=layer.hs_hue, Saturation=layer.hs_saturation, Lightness=layer.hs_lightness)
        elif k == "LEVELS":
            v.update(InBlack=layer.lv_in_black / 255, InWhite=layer.lv_in_white / 255,
                     Gamma=layer.lv_gamma, OutBlack=layer.lv_out_black / 255,
                     OutWhite=layer.lv_out_white / 255)
        elif k == "BRIGHT_CONTRAST":
            v.update(Bright=layer.bc_brightness / 100, Contrast=layer.bc_contrast / 100)
    elif t in LIGHT_TYPES:
        thr = layer.light_threshold
        if layer.layer_type == "NORMAL_LIGHT" and layer.light_polarity == "SHADOW" and layer.include_cast_shadow:
            thr = max(thr, 0.0)   # below 0 is all pinned shadow: same as Size 0, which the slider shows
        v.update(Color=col(layer.light_color), Threshold=thr,
                 Softness=layer.light_softness, Bands=float(layer.light_bands),
                 Tightness=layer.spec_tightness, Override=1.0 if layer.light_override else 0.0,
                 Direction=tuple(layer.light_dir), FormSize=layer.form_size,
                 NStrength=layer.normal_strength, BreakStrength=layer.breakup_strength,
                 BreakScale=layer.breakup_scale,
                 TermColor=col(layer.terminator_color), TermWidth=layer.terminator_width,
                 SSSWidth=layer.sss_width, SSSDistort=layer.sss_distortion, SSSPower=layer.sss_power)
    for i, m in enumerate(layer.masks):
        v.update({f"M{i} Visible": 1.0 if m.visible else 0.0, f"M{i} Opacity": m.opacity,
                  f"M{i} Threshold": m.threshold, f"M{i} Softness": m.softness,
                  f"M{i} Invert": 1.0 if m.invert else 0.0, f"M{i} Detail": m.detail,
                  f"M{i} Kind": 1.0 if m.curvature_kind == "CAVITY" else 0.0,
                  f"M{i} Correction": m.correction_strength, f"M{i} NScale": m.noise_scale,
                  f"M{i} NDetail": m.noise_detail, f"M{i} NRough": m.noise_roughness,
                  f"M{i} NDistort": m.noise_distortion, f"M{i} NSeed": m.noise_seed})
    return v


def images(layer, stack):
    """Image datablocks to assign inside the layer tree (pushed, no rebuild)."""
    out = {}
    if layer.layer_type == "FILL" and layer.fill_source == "IMAGE":
        out["SRC.image"] = out["SRC.image#2"] = layer.fill_image
        out["H.image#2"] = layer.height_image
    elif layer.layer_type == "PAINT":
        out["SRC.image"] = layer.paint_image
    if layer.layer_type in ("FILL", "PAINT"):
        out["H.image"] = layer.height_image
    if layer.layer_type in LIGHT_TYPES:
        out["LIGHT.breakup"] = layer.breakup_image
        out["LIGHT.shadow"] = stack.bake_shadow_image
        out["SSS.thick"] = stack.thickness_image
    for i, m in enumerate(layer.masks):
        out[f"M{i}.src"] = {"DEPTH": stack.height_image, "CURVATURE": stack.curvature_image}.get(m.source, m.image)
        out[f"M{i}.corr"] = m.correction
        out[f"M{i}.shadow"] = stack.bake_shadow_image
    return out
