"""Per-layer private node trees ".PLASTRON L <uid>" (ported from CaraPainter's
compiler/layers.py; trimmed to 2D: no lights, heights or 3D projections).

Every layer tree has the same outer interface so the stack can chain them:
    inputs  Under, UnderA, Opacity, Visible, (+ type parameters)
    outputs Out, OutA, Mask
A tree is only rebuilt when its structural signature changes; Blend If ramps
and Curves are carried over across rebuilds, so edits survive.
"""

import bpy

from . import blend_lib
from .nodes import NB, iface

TREE_PREFIX = ".PLASTRON L "
COMPILER_REV = 1   # bump when layer trees change without a property change
BI_CHANNELS = ("GREY", "R", "G", "B")
BI_EPS = 0.006     # EEVEE samples ramps from a 256-entry LUT; keep off the ends
BI_DEFAULT = [(0.0, (0, 0, 0, 1)), (0.0, (1, 1, 1, 1)), (1.0, (1, 1, 1, 1)), (1.0, (0, 0, 0, 1))]
BI_COLOURS = [(0, 0, 0, 1), (1, 1, 1, 1), (1, 1, 1, 1), (0, 0, 0, 1)]
LA_DEFAULTS = (("la_hue", 0.0), ("la_saturation", 1.0), ("la_value", 1.0))
LA_CURVE = "LA.curve"
MASK_INPUTS = (("Visible", 1.0), ("Opacity", 1.0), ("Threshold", 0.5), ("Softness", 0.5),
               ("Invert", 0.0))


def colour_adjusted(layer):
    return layer.la_curve or any(abs(getattr(layer, k) - d) > 1e-6 for k, d in LA_DEFAULTS)


def signature(layer, stack):
    parts = [blend_lib.LIB_VERSION, COMPILER_REV, layer.layer_type, layer.blend_mode,
             stack.blend_space, colour_adjusted(layer), layer.blend_if]
    t = layer.layer_type
    if t == "FILL":
        parts.append(layer.fill_source)
        if layer.fill_source == "IMAGE":
            parts.append(layer.tile_break > 0)
    elif t == "ADJUST":
        parts.append(layer.adjust_kind)
    elif t == "GROUP":
        parts.append(layer.group_mode)
    for m in layer.masks:
        parts.append(f"M:{m.source}:{m.op}:{bool(m.image)}")
    return "|".join(str(p) for p in parts)


# --- preservation of user-edited ramps / curves across rebuilds -----------------

def snapshot(tree):
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


def restore(tree, snap):
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


def normalise_blend_if_ramp(ramp):
    """Keep a Blend If ramp meaning 'black, white, white, black' whatever stop was dragged."""
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


# --- pieces ---------------------------------------------------------------------

def _uv(nb):
    return nb.node('ShaderNodeTexCoord').outputs["UV"]


def _colour_adjust(nb, gi, layer, c):
    """The layer's own Hue/Sat/Value, then its curve graph, before it blends."""
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


def _fill_coords(nb, gi, layer):
    """Coordinates of an image fill: centred, rotated, scaled, offset (+ tiling break)."""
    centred = nb.v('SUBTRACT', _uv(nb), (0.5, 0.5, 0.0))
    rot = nb.node('ShaderNodeVectorRotate', rotation_type='Z_AXIS')
    nb.feed(rot.inputs["Vector"], centred)
    nb.feed(rot.inputs["Angle"], gi.outputs["TexRot"])
    p = nb.vscale(rot.outputs["Vector"], gi.outputs["TexScale"])
    p = nb.v('ADD', p, nb.comb(nb.add(gi.outputs["TexOffX"], 0.5), nb.add(gi.outputs["TexOffY"], 0.5), 0.0))
    out = {"P": p, "P2": None, "W": None}
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


def _image(nb, stack, name, coords=None, extension='CLIP'):
    """(colour in the blend space, alpha) of the image node `name`."""
    def one(n, vec):
        tex = nb.node('ShaderNodeTexImage', name=n, interpolation='Linear', extension=extension)
        nb.feed(tex.inputs[0], vec)
        return tex.outputs["Color"], tex.outputs["Alpha"]
    if coords is None:
        col, a = one(name, _uv(nb))
    else:
        col, a = one(name, coords["P"])
        if coords["P2"] is not None:
            c2, a2 = one(name + "#2", coords["P2"])
            col, a = nb.mixc(coords["W"], col, c2), nb.mixf(coords["W"], a, a2)
    if stack.blend_space == "SRGB":
        col = nb.group(blend_lib.to_srgb_group(), Color=col).outputs[0]
    return col, a


def _blend_if(nb, cs, under, on=True):
    """Product of the 8 Blend If ramps (This Layer / Underlying x Grey, R, G, B).
    Off: the ramps exist for the panel (keeping their stops) but aren't wired in."""
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
            ramp = nb.node('ShaderNodeValToRGB', name=f"BI.{which}.{ch}", label=f"Blend If {which} {ch}")
            set_ramp(ramp.color_ramp, BI_DEFAULT)
            ramp.color_ramp.interpolation = 'LINEAR'
            nb.feed(ramp.inputs[0], v)
            out = ramp.outputs["Color"]
            w = out if w is None else nb.mul(w, out)
    return w


def _mask_value(nb, gi, i, m, stack):
    g = lambda n: gi.outputs[f"M{i} {n}"]
    if m.image is None:
        return None
    tex = nb.node('ShaderNodeTexImage', name=f"M{i}.src", interpolation='Linear', extension='CLIP')
    nb.feed(tex.inputs[0], _uv(nb))
    grey = nb.group(blend_lib.to_srgb_group(), Color=tex.outputs["Color"]).outputs[0]
    if m.source == "PAINT":      # painted directly: the value IS the mask
        v = nb.sep(grey)[0]
        return nb.mixf(g("Invert"), v, nb.sub(1.0, v))
    v = nb.dot(grey, blend_lib.LUMW)
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


def _masks(nb, gi, layer, stack):
    m_acc = None
    for i, m in enumerate(layer.masks):
        v = _mask_value(nb, gi, i, m, stack)
        if v is None:
            continue
        base = 1.0 if m_acc is None else m_acc
        combined = _combine(nb, m.op, base, v)
        amt = nb.mul(gi.outputs[f"M{i} Visible"], gi.outputs[f"M{i} Opacity"])
        m_acc = nb.mixf(amt, base, combined)
    return m_acc


def _adjust(nb, gi, kind, under):
    if kind == "HUE_SAT":
        hsv = nb.node('ShaderNodeHueSaturation')
        nb.feed(hsv.inputs["Color"], under)
        nb.feed(hsv.inputs["Hue"], nb.add(0.5, nb.div(gi.outputs["Hue"], 360.0)))
        nb.feed(hsv.inputs["Saturation"], nb.mx(0.0, nb.add(1.0, nb.div(gi.outputs["Saturation"], 100.0))))
        c = hsv.outputs[0]
        light = nb.div(gi.outputs["Lightness"], 100.0)
        target = nb.gt(light, 0.0)   # towards white (+) or black (-), like Photoshop
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
    cv = nb.node('ShaderNodeRGBCurve', name="ADJ.curves")   # CURVES
    nb.feed(cv.inputs["Color"], under)
    return cv.outputs[0]


# --- build ------------------------------------------------------------------------

def build(layer, stack):
    """A FRESH tree every time: Blender's threaded material preview may be copying
    the old one right now, so it's retired (deleted later), never edited in place."""
    from .compiler import retire
    old = layer.node_tree
    snap = snapshot(old)
    tree = bpy.data.node_groups.new(TREE_PREFIX + layer.uid, 'ShaderNodeTree')
    try:
        _build_into(layer, stack, tree, snap)
    except Exception:
        bpy.data.node_groups.remove(tree)
        raise
    layer.node_tree = tree
    if old is not None:
        retire(old)
    return tree


def _build_into(layer, stack, tree, snap):
    t = layer.layer_type
    iface(tree, 'OUTPUT', "Out", 'NodeSocketColor')
    iface(tree, 'OUTPUT', "OutA", 'NodeSocketFloat')
    iface(tree, 'OUTPUT', "Mask", 'NodeSocketFloat')
    iface(tree, 'INPUT', "Under", 'NodeSocketColor', (0, 0, 0, 1))
    iface(tree, 'INPUT', "UnderA", 'NodeSocketFloat', 0.0)
    iface(tree, 'INPUT', "Opacity", 'NodeSocketFloat', 1.0, 0, 1)
    adjusted = colour_adjusted(layer)
    if adjusted:
        for n, d in (("LA Hue", 0.0), ("LA Sat", 1.0), ("LA Val", 1.0)):
            iface(tree, 'INPUT', n, 'NodeSocketFloat', d)
    iface(tree, 'INPUT', "Visible", 'NodeSocketFloat', 1.0, 0, 1)
    if t == "GROUP":
        iface(tree, 'INPUT', "Content", 'NodeSocketColor', (0, 0, 0, 1))
        iface(tree, 'INPUT', "ContentA", 'NodeSocketFloat', 0.0)
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
    for i in range(len(layer.masks)):
        for n, d in MASK_INPUTS:
            iface(tree, 'INPUT', f"M{i} {n}", 'NodeSocketFloat', d)

    nb = NB(tree)
    gi = nb.node('NodeGroupInput')
    go = nb.node('NodeGroupOutput')
    under, under_a = gi.outputs["Under"], gi.outputs["UnderA"]
    vis = nb.mul(gi.outputs["Opacity"], gi.outputs["Visible"])
    mask = _masks(nb, gi, layer, stack)
    nb.feed(go.inputs["Mask"], mask if mask is not None else 1.0)
    if mask is not None:
        vis = nb.mul(vis, mask)

    if t == "GROUP" and layer.group_mode == "PASS_THROUGH":
        content = _colour_adjust(nb, gi, layer, gi.outputs["Content"]) if adjusted else gi.outputs["Content"]
        nb.feed(go.inputs["Out"], nb.mixc(vis, under, content))
        nb.feed(go.inputs["OutA"], nb.mixf(vis, under_a, gi.outputs["ContentA"]))
    else:
        if t == "GROUP":
            cs, a_src = gi.outputs["Content"], gi.outputs["ContentA"]
        elif t == "FILL" and layer.fill_source == "COLOR":
            cs, a_src = gi.outputs["Color"], 1.0
        elif t == "FILL":
            cs, a_src = _image(nb, stack, "SRC.image", _fill_coords(nb, gi, layer), extension='REPEAT')
        elif t == "PAINT":
            cs, a_src = _image(nb, stack, "SRC.image")
        else:   # ADJUST
            cs, a_src = _adjust(nb, gi, layer.adjust_kind, under), 1.0
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

    restore(tree, snap)
    tree["plastron_sig"] = signature(layer, stack)


# --- values pushed without rebuilding ------------------------------------------------

def _decode(c):
    return tuple(x / 12.92 if x < 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def values(layer, stack):
    """Socket values for the layer's instance node. Colour props are COLOR_GAMMA
    (what the picker shows); in Linear blend space they're decoded."""
    col = (lambda c: (*c, 1.0)) if stack.blend_space == "SRGB" else (lambda c: (*_decode(c), 1.0))
    v = {"LA Hue": layer.la_hue, "LA Sat": layer.la_saturation, "LA Val": layer.la_value,
         "Opacity": layer.opacity, "Visible": 1.0 if layer.visible else 0.0}
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
    for i, m in enumerate(layer.masks):
        v.update({f"M{i} Visible": 1.0 if m.visible else 0.0, f"M{i} Opacity": m.opacity,
                  f"M{i} Threshold": m.threshold, f"M{i} Softness": m.softness,
                  f"M{i} Invert": 1.0 if m.invert else 0.0})
    return v


def images(layer, stack):
    """Image datablocks to assign inside the layer tree (pushed, no rebuild)."""
    out = {}
    if layer.layer_type == "FILL" and layer.fill_source == "IMAGE":
        out["SRC.image"] = out["SRC.image#2"] = layer.fill_image
    elif layer.layer_type == "PAINT":
        out["SRC.image"] = layer.paint_image
    for i, m in enumerate(layer.masks):
        out[f"M{i}.src"] = m.image
    return out
