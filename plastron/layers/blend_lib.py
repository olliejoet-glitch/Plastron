"""Shared, versioned library node groups: blend modes and colour conversions.

Ported from Ollie's CaraPainter (compiler/blend_lib.py); the 3D key light is left out.

Blend groups all share one interface (ARCHITECTURE §5.2):
    inputs  Cb (under colour), Ab (under alpha), Cs (layer colour), As (layer coverage)
    outputs Co, Ao
    Co = [(1-As)·Ab·Cb + As·(1-Ab)·Cs + As·Ab·B(Cb,Cs)] / Ao,   Ao = As + Ab·(1-As)
Formulas follow Photoshop / the PDF blend-mode spec. layers/flatten.py computes the
same formulas with numpy for the panel images: keep the two in sync (tests compare them).
"""
import bpy

from .nodes import EPS, NB, iface, new_tree

LIB_VERSION = 1
LUMW = (0.3, 0.59, 0.11)
PREFIX = ".PLASTRON "


# ----------------------------------------------------------------------------- scalar modes

def _burn(nb, a, b):
    r = nb.sub(1.0, nb.mn(1.0, nb.div(nb.sub(1.0, a), b)))
    r = nb.sel(nb.lt(b, EPS), 0.0, r)
    return nb.sel(nb.gt(a, 1.0 - EPS), 1.0, r)


def _dodge(nb, a, b):
    r = nb.mn(1.0, nb.div(a, nb.sub(1.0, b)))
    r = nb.sel(nb.gt(b, 1.0 - EPS), 1.0, r)
    return nb.sel(nb.lt(a, EPS), 0.0, r)


def _screen(nb, a, b):
    return nb.sub(nb.add(a, b), nb.mul(a, b))


def _hard(nb, a, b):  # hard light with b as the "light"
    lo = nb.mul(2.0, nb.mul(a, b))
    hi = nb.sub(1.0, nb.mul(2.0, nb.mul(nb.sub(1.0, a), nb.sub(1.0, b))))
    return nb.sel(nb.lt(b, 0.5), lo, hi)


def _soft(nb, a, b):  # Photoshop's soft light (not W3C)
    two_b = nb.mul(2.0, b)
    lo = nb.add(nb.mul(two_b, a), nb.mul(nb.mul(a, a), nb.sub(1.0, two_b)))
    hi = nb.add(nb.mul(nb.mul(2.0, a), nb.sub(1.0, b)),
                nb.mul(nb.m('SQRT', a), nb.sub(two_b, 1.0)))
    return nb.sel(nb.lt(b, 0.5), lo, hi)


SCALAR = {
    "NORMAL": lambda nb, a, b: b,
    "DARKEN": lambda nb, a, b: nb.mn(a, b),
    "MULTIPLY": lambda nb, a, b: nb.mul(a, b),
    "COLOR_BURN": _burn,
    "LINEAR_BURN": lambda nb, a, b: nb.clamp(nb.sub(nb.add(a, b), 1.0)),
    "LIGHTEN": lambda nb, a, b: nb.mx(a, b),
    "SCREEN": _screen,
    "COLOR_DODGE": _dodge,
    "LINEAR_DODGE": lambda nb, a, b: nb.clamp(nb.add(a, b)),
    "OVERLAY": lambda nb, a, b: _hard(nb, b, a),
    "SOFT_LIGHT": _soft,
    "HARD_LIGHT": _hard,
    "VIVID_LIGHT": lambda nb, a, b: nb.sel(nb.lt(b, 0.5), _burn(nb, a, nb.mul(2.0, b)),
                                           _dodge(nb, a, nb.sub(nb.mul(2.0, b), 1.0))),
    "LINEAR_LIGHT": lambda nb, a, b: nb.clamp(nb.add(a, nb.sub(nb.mul(2.0, b), 1.0))),
    "PIN_LIGHT": lambda nb, a, b: nb.sel(nb.lt(b, 0.5), nb.mn(a, nb.mul(2.0, b)),
                                         nb.mx(a, nb.sub(nb.mul(2.0, b), 1.0))),
    "HARD_MIX": lambda nb, a, b: nb.gt(nb.add(a, b), 1.0 - EPS),
    "DIFFERENCE": lambda nb, a, b: nb.m('ABSOLUTE', nb.sub(a, b)),
    "EXCLUSION": lambda nb, a, b: nb.sub(nb.add(a, b), nb.mul(2.0, nb.mul(a, b))),
    "SUBTRACT": lambda nb, a, b: nb.mx(0.0, nb.sub(a, b)),
    "DIVIDE": lambda nb, a, b: nb.sel(nb.lt(a, EPS), 0.0, nb.mn(1.0, nb.div(a, b))),
}


# ----------------------------------------------------------------------------- non-separable

def _lum(nb, c):
    return nb.dot(c, LUMW)


def _clip_color(nb, c):
    L = _lum(nb, c)
    n = nb.min3(c)
    x = nb.max3(c)
    d = nb.v('SUBTRACT', c, L)
    c1 = nb.v('ADD', nb.vscale(d, nb.div(L, nb.sub(L, n))), L)
    c = nb.sel_v(nb.lt(n, 0.0), c1, c)
    d = nb.v('SUBTRACT', c, L)
    c2 = nb.v('ADD', nb.vscale(d, nb.div(nb.sub(1.0, L), nb.sub(x, L))), L)
    return nb.sel_v(nb.gt(x, 1.0), c2, c)


def _set_lum(nb, c, l):
    return _clip_color(nb, nb.v('ADD', c, nb.sub(l, _lum(nb, c))))


def _sat(nb, c):
    return nb.sub(nb.max3(c), nb.min3(c))


def _set_sat(nb, c, s):
    lo, hi = nb.min3(c), nb.max3(c)
    rng = nb.sub(hi, lo)
    k = nb.mul(nb.div(s, rng), nb.gt(rng, EPS))
    return nb.vscale(nb.v('SUBTRACT', c, lo), k)


def _sum(nb, c):
    return nb.dot(c, (1.0, 1.0, 1.0))


VECTOR = {
    "HUE": lambda nb, a, b: _set_lum(nb, _set_sat(nb, b, _sat(nb, a)), _lum(nb, a)),
    "SATURATION": lambda nb, a, b: _set_lum(nb, _set_sat(nb, a, _sat(nb, b)), _lum(nb, a)),
    "COLOR": lambda nb, a, b: _set_lum(nb, b, _lum(nb, a)),
    "LUMINOSITY": lambda nb, a, b: _set_lum(nb, a, _lum(nb, b)),
    "DARKER_COLOR": lambda nb, a, b: nb.sel_v(nb.lt(_sum(nb, b), _sum(nb, a)), b, a),
    "LIGHTER_COLOR": lambda nb, a, b: nb.sel_v(nb.gt(_sum(nb, b), _sum(nb, a)), b, a),
}


# ----------------------------------------------------------------------------- builders

def _fresh(name):
    t = bpy.data.node_groups.get(name)
    return t is None or t.get("pl_lib_version") != LIB_VERSION


def blend_group(mode):
    name = f"{PREFIX}Blend {mode.replace('_', ' ').title()}"
    if not _fresh(name):
        return bpy.data.node_groups[name]
    tree = new_tree(name)
    iface(tree, 'OUTPUT', "Co", 'NodeSocketColor')
    iface(tree, 'OUTPUT', "Ao", 'NodeSocketFloat')
    iface(tree, 'INPUT', "Cb", 'NodeSocketColor', (0, 0, 0, 1))
    iface(tree, 'INPUT', "Ab", 'NodeSocketFloat', 1.0)
    iface(tree, 'INPUT', "Cs", 'NodeSocketColor', (0, 0, 0, 1))
    iface(tree, 'INPUT', "As", 'NodeSocketFloat', 1.0)
    nb = NB(tree)
    gi = nb.node('NodeGroupInput')
    go = nb.node('NodeGroupOutput')
    clamp01 = lambda c: nb.v('MINIMUM', nb.v('MAXIMUM', c, (0, 0, 0)), (1, 1, 1))
    cb, cs = clamp01(gi.outputs["Cb"]), clamp01(gi.outputs["Cs"])
    ab, as_ = gi.outputs["Ab"], gi.outputs["As"]
    if mode in SCALAR:
        B = nb.per_channel(SCALAR[mode], cb, cs)
    else:
        B = VECTOR[mode](nb, cb, cs)
    ao = nb.add(as_, nb.mul(ab, nb.sub(1.0, as_)))
    w_b = nb.mul(nb.sub(1.0, as_), ab)
    w_s = nb.mul(as_, nb.sub(1.0, ab))
    w_x = nb.mul(as_, ab)
    num = nb.v('ADD', nb.v('ADD', nb.vscale(cb, w_b), nb.vscale(cs, w_s)), nb.vscale(B, w_x))
    nb.feed(go.inputs["Co"], nb.vscale(num, nb.div(1.0, ao)))
    nb.feed(go.inputs["Ao"], ao)
    tree["pl_lib_version"] = LIB_VERSION
    return tree


def _conv_group(name, to_srgb):
    if not _fresh(name):
        return bpy.data.node_groups[name]
    tree = new_tree(name)
    iface(tree, 'OUTPUT', "Color", 'NodeSocketColor')
    iface(tree, 'INPUT', "Color", 'NodeSocketColor', (0, 0, 0, 1))
    nb = NB(tree)
    gi = nb.node('NodeGroupInput')
    go = nb.node('NodeGroupOutput')

    def enc(nb, c):
        c = nb.mx(c, 0.0)
        lin = nb.mul(c, 12.92)
        gam = nb.sub(nb.mul(1.055, nb.m('POWER', c, 1 / 2.4)), 0.055)
        return nb.sel(nb.lt(c, 0.0031308), lin, gam)

    def dec(nb, c):
        c = nb.mx(c, 0.0)
        lin = nb.mul(c, 1 / 12.92)
        gam = nb.m('POWER', nb.mul(nb.add(c, 0.055), 1 / 1.055), 2.4)
        return nb.sel(nb.lt(c, 0.04045), lin, gam)

    nb.feed(go.inputs["Color"], nb.per_channel(enc if to_srgb else dec, gi.outputs["Color"]))
    tree["pl_lib_version"] = LIB_VERSION
    return tree


def to_srgb_group():
    return _conv_group(PREFIX + "To sRGB", True)


def to_linear_group():
    return _conv_group(PREFIX + "To Linear", False)


def ensure_all():
    from .props import BLEND_MODES
    for item in BLEND_MODES:
        blend_group(item[0])
    to_srgb_group()
    to_linear_group()
