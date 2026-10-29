"""Flattens a layer stack into one RGBA image with numpy: the panel's cached
image (timeline thumbnail, animatic export). Mirrors the shader exactly
(compiler + blend_lib); tests compare the two.

Works in the stack's blend space (sRGB: gamma-encoded values, like
Photoshop). Paint images are 8-bit sRGB, so their pixels are used as is.
Not mirrored: the fill "tiling break" (Blender noise), approximated by the
plain tiled image.
"""

import numpy as np

from .layer_trees import BI_CHANNELS, BI_EPS, LA_CURVE, colour_adjusted

EPS = 1e-6
LUMW = np.array((0.3, 0.59, 0.11), np.float32)


# --- colour helpers -----------------------------------------------------------------

def _decode(c):
    c = np.maximum(c, 0.0)
    return np.where(c < 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _encode(c):
    c = np.maximum(c, 0.0)
    return np.where(c < 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def _rgb_to_hsv(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mx, mn = np.max(c, -1), np.min(c, -1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, EPS), 0.0)
    dd = np.maximum(d, EPS)
    h = np.where(mx == r, (g - b) / dd, np.where(mx == g, 2.0 + (b - r) / dd, 4.0 + (r - g) / dd))
    h = np.where(d > 0, (h / 6.0) % 1.0, 0.0)
    return np.stack((h, s, mx), -1)


def _hsv_to_rgb(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    i = i.astype(int) % 6
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack((r, g, b), -1)


def _hue_sat(c, hue, sat, val):
    """Blender's Hue/Saturation/Value node (hue 0.5 = no change)."""
    hsv = _rgb_to_hsv(c)
    hsv[..., 0] = (hsv[..., 0] + hue - 0.5) % 1.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0.0, 1.0)
    hsv[..., 2] = hsv[..., 2] * val
    return _hsv_to_rgb(hsv)


def _curve_lut(mapping, n=1024):
    """(combined, r, g, b) lookup tables of an RGB Curves mapping."""
    mapping.initialize()
    xs = np.linspace(0, 1, n)
    curves = mapping.curves   # R, G, B, combined
    return [np.array([mapping.evaluate(curves[k], float(x)) for x in xs], np.float32)
            for k in (3, 0, 1, 2)]


def _apply_lut(lut, v):
    n = len(lut)
    return np.interp(np.clip(v, 0, 1), np.linspace(0, 1, n), lut)


def _rgb_curves(node, c):
    comb, r, g, b = _curve_lut(node.mapping)
    out = np.empty_like(c)
    for k, lut in enumerate((r, g, b)):
        out[..., k] = _apply_lut(lut, _apply_lut(comb, c[..., k]))
    return out


def _ramp_lut(ramp, n=256):
    xs = np.linspace(0, 1, n)
    vals = np.array([ramp.evaluate(float(x))[:3] for x in xs], np.float32)
    return vals @ np.array((0.2126, 0.7152, 0.0722), np.float32)   # grey -> its value


# --- blend modes (blend_lib.SCALAR / VECTOR) ----------------------------------------------

def _burn(a, b):
    r = 1.0 - np.minimum(1.0, (1.0 - a) / np.maximum(b, EPS))
    r = np.where(b < EPS, 0.0, r)
    return np.where(a > 1.0 - EPS, 1.0, r)


def _dodge(a, b):
    r = np.minimum(1.0, a / np.maximum(1.0 - b, EPS))
    r = np.where(b > 1.0 - EPS, 1.0, r)
    return np.where(a < EPS, 0.0, r)


def _hard(a, b):
    return np.where(b < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))


def _soft(a, b):
    lo = 2 * b * a + a * a * (1 - 2 * b)
    hi = 2 * a * (1 - b) + np.sqrt(np.maximum(a, 0)) * (2 * b - 1)
    return np.where(b < 0.5, lo, hi)


SCALAR = {
    "NORMAL": lambda a, b: b,
    "DARKEN": np.minimum,
    "MULTIPLY": lambda a, b: a * b,
    "COLOR_BURN": _burn,
    "LINEAR_BURN": lambda a, b: np.clip(a + b - 1, 0, 1),
    "LIGHTEN": np.maximum,
    "SCREEN": lambda a, b: a + b - a * b,
    "COLOR_DODGE": _dodge,
    "LINEAR_DODGE": lambda a, b: np.clip(a + b, 0, 1),
    "OVERLAY": lambda a, b: _hard(b, a),
    "SOFT_LIGHT": _soft,
    "HARD_LIGHT": _hard,
    "VIVID_LIGHT": lambda a, b: np.where(b < 0.5, _burn(a, 2 * b), _dodge(a, 2 * b - 1)),
    "LINEAR_LIGHT": lambda a, b: np.clip(a + 2 * b - 1, 0, 1),
    "PIN_LIGHT": lambda a, b: np.where(b < 0.5, np.minimum(a, 2 * b), np.maximum(a, 2 * b - 1)),
    "HARD_MIX": lambda a, b: (a + b > 1.0 - EPS).astype(np.float32),
    "DIFFERENCE": lambda a, b: np.abs(a - b),
    "EXCLUSION": lambda a, b: a + b - 2 * a * b,
    "SUBTRACT": lambda a, b: np.maximum(0.0, a - b),
    "DIVIDE": lambda a, b: np.where(a < EPS, 0.0, np.minimum(1.0, a / np.maximum(b, EPS))),
}


def _lum(c):
    return c @ LUMW


def _clip_color(c):
    L = _lum(c)[..., None]
    n = np.min(c, -1)[..., None]
    x = np.max(c, -1)[..., None]
    c1 = (c - L) * (L / np.maximum(L - n, EPS)) + L
    c = np.where(n < 0, c1, c)
    c2 = (c - L) * ((1 - L) / np.maximum(x - L, EPS)) + L
    return np.where(x > 1, c2, c)


def _set_lum(c, l):
    return _clip_color(c + (l - _lum(c))[..., None])


def _sat(c):
    return np.max(c, -1) - np.min(c, -1)


def _set_sat(c, s):
    lo, hi = np.min(c, -1), np.max(c, -1)
    rng = hi - lo
    k = (s / np.maximum(rng, EPS)) * (rng > EPS)
    return (c - lo[..., None]) * k[..., None]


VECTOR = {
    "HUE": lambda a, b: _set_lum(_set_sat(b, _sat(a)), _lum(a)),
    "SATURATION": lambda a, b: _set_lum(_set_sat(a, _sat(b)), _lum(a)),
    "COLOR": lambda a, b: _set_lum(b, _lum(a)),
    "LUMINOSITY": lambda a, b: _set_lum(a, _lum(b)),
    "DARKER_COLOR": lambda a, b: np.where((b.sum(-1) < a.sum(-1))[..., None], b, a),
    "LIGHTER_COLOR": lambda a, b: np.where((b.sum(-1) > a.sum(-1))[..., None], b, a),
}


def blend(mode, cb, ab, cs, as_):
    """Photoshop compositing of colour cs (coverage as_) over cb (alpha ab)."""
    cb, cs = np.clip(cb, 0, 1), np.clip(cs, 0, 1)
    B = SCALAR[mode](cb, cs) if mode in SCALAR else VECTOR[mode](cb, cs)
    ab, as_ = ab[..., None], as_[..., None]
    ao = as_ + ab * (1 - as_)
    num = cb * (1 - as_) * ab + cs * as_ * (1 - ab) + B * as_ * ab
    return num / np.maximum(ao, EPS), ao[..., 0]


# --- sampling ------------------------------------------------------------------------------

class Grid:
    """Which canvas pixels are being computed: a crop of the canvas at a scale."""

    def __init__(self, width, height, crop=None, out_size=None):
        x0, y0, cw, ch = crop or (0, 0, width, height)
        ow, oh = out_size or (cw, ch)
        self.width, self.height = width, height
        self.crop = (x0, y0, cw, ch)
        self.size = (ow, oh)
        xs = x0 + (np.arange(ow) + 0.5) * cw / ow
        ys = y0 + (np.arange(oh) + 0.5) * ch / oh
        self.u, self.v = np.meshgrid(xs / width, ys / height)   # canvas UVs, rows bottom-up


def _pixels(img):
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def _sample(img, u, v, repeat=False):
    """Bilinear sample of a Blender image at UVs -> (srgb-ish colour, alpha).

    8-bit images give their stored (sRGB) values; float images are linear and
    are encoded."""
    px = _pixels(img)
    h, w = px.shape[:2]
    x = u * w - 0.5
    y = v * h - 0.5
    if repeat:
        x, y = x % w, y % h
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]

    def at(xx, yy):
        if repeat:
            return px[yy % h, xx % w]
        inside = ((xx >= 0) & (xx < w) & (yy >= 0) & (yy < h))[..., None]
        return np.where(inside, px[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)], 0.0)

    c = (at(x0, y0) * (1 - fx) * (1 - fy) + at(x0 + 1, y0) * fx * (1 - fy) +
         at(x0, y0 + 1) * (1 - fx) * fy + at(x0 + 1, y0 + 1) * fx * fy)
    rgb, a = c[..., :3], c[..., 3]
    if img.is_float:
        rgb = _encode(rgb)
    return rgb, a


def _sample_layer_image(img, grid):
    """Paint images match the canvas, so an unscaled crop is a plain slice."""
    x0, y0, cw, ch = grid.crop
    if img.size[:] == (grid.width, grid.height) and grid.size == (cw, ch) and not img.is_float:
        px = _pixels(img)[y0:y0 + ch, x0:x0 + cw]
        return px[..., :3], px[..., 3]
    return _sample(img, grid.u, grid.v)


# --- layers ------------------------------------------------------------------------------

def _colour_adjust(layer, c):
    c = _hue_sat(c, layer.la_hue / 360.0 + 0.5, layer.la_saturation, layer.la_value)
    if layer.la_curve and layer.node_tree and layer.node_tree.nodes.get(LA_CURVE):
        c = _rgb_curves(layer.node_tree.nodes[LA_CURVE], c)
    return c


def _adjust(layer, under):
    k = layer.adjust_kind
    if k == "HUE_SAT":
        c = _hue_sat(under, 0.5 + layer.hs_hue / 360.0, max(0.0, 1 + layer.hs_saturation / 100.0), 1.0)
        light = layer.hs_lightness / 100.0
        target = 1.0 if light > 0 else 0.0
        return c + (target - c) * abs(light)
    if k == "LEVELS":
        ib, iw = layer.lv_in_black / 255, layer.lv_in_white / 255
        ob, ow = layer.lv_out_black / 255, layer.lv_out_white / 255
        v = np.clip((under - ib) / np.maximum(iw - ib, EPS), 0, 1)
        v = np.power(v, 1.0 / layer.lv_gamma)
        return ob + v * (ow - ob)
    if k == "BRIGHT_CONTRAST":
        a = 1.0 + layer.bc_contrast / 100
        b = layer.bc_brightness / 100 - (layer.bc_contrast / 100) * 0.5
        return np.maximum(a * under + b, 0.0)
    node = layer.node_tree.nodes.get("ADJ.curves") if layer.node_tree else None
    return _rgb_curves(node, under) if node else under


def _mask(layer, grid):
    acc = None
    for m in layer.masks:
        if m.image is None:
            continue
        rgb, _a = _sample(m.image, grid.u, grid.v)
        if m.source == "PAINT":
            v = rgb[..., 0]
        else:
            t = np.clip((_lum(rgb) - (m.threshold - m.softness)) /
                        max(2 * m.softness, 1e-4), 0, 1)
            v = t * t * (3 - 2 * t)
        if m.invert:
            v = 1 - v
        base = 1.0 if acc is None else acc
        op = m.op
        if op == "MULTIPLY":
            comb = base * v
        elif op == "ADD":
            comb = np.clip(base + v, 0, 1)
        elif op == "SUBTRACT":
            comb = np.clip(base - v, 0, 1)
        elif op == "MAX":
            comb = np.maximum(base, v)
        elif op == "MIN":
            comb = np.minimum(base, v)
        else:
            comb = np.where(base < 0.5, 2 * base * v, 1 - 2 * (1 - base) * (1 - v))
        amt = (1.0 if m.visible else 0.0) * m.opacity
        acc = base + (comb - base) * amt
    return acc


def _blend_if(layer, cs, under):
    tree = layer.node_tree
    w = None
    for which, col in (("this", cs), ("under", under)):
        vals = {"GREY": _lum(col), "R": col[..., 0], "G": col[..., 1], "B": col[..., 2]}
        for ch in BI_CHANNELS:
            node = tree.nodes.get(f"BI.{which}.{ch}") if tree else None
            if node is None:
                continue
            lut = _ramp_lut(node.color_ramp)
            v = vals[ch] * (1 - 2 * BI_EPS) + BI_EPS
            out = _apply_lut(lut, v)
            w = out if w is None else w * out
    return w


def _layer_source(layer, stack, grid, under):
    t = layer.layer_type
    shape = grid.u.shape
    if t == "FILL" and layer.fill_source == "COLOR":
        c = np.array(layer.fill_color, np.float32)
        if stack.blend_space == "LINEAR":
            c = _decode(c)
        return np.broadcast_to(c, shape + (3,)).copy(), np.ones(shape, np.float32)
    if t == "FILL":
        if layer.fill_image is None:
            return np.zeros(shape + (3,), np.float32), np.zeros(shape, np.float32)
        u, v = grid.u - 0.5, grid.v - 0.5
        ca, sa = np.cos(layer.tex_rotation), np.sin(layer.tex_rotation)
        pu = (u * ca - v * sa) * layer.tex_scale + 0.5 + layer.tex_offset[0]
        pv = (u * sa + v * ca) * layer.tex_scale + 0.5 + layer.tex_offset[1]
        rgb, a = _sample(layer.fill_image, pu, pv, repeat=True)
    elif t == "PAINT":
        if layer.paint_image is None:
            return np.zeros(shape + (3,), np.float32), np.zeros(shape, np.float32)
        rgb, a = _sample_layer_image(layer.paint_image, grid)
    else:   # ADJUST
        return _adjust(layer, under), np.ones(shape, np.float32)
    if stack.blend_space == "LINEAR":
        rgb = _decode(rgb)
    return rgb, a


def _composite(stack, grid, parent_uid, under, under_a):
    for layer in [l for l in stack.layers if l.parent_uid == parent_uid]:
        vis = layer.opacity * (1.0 if layer.visible else 0.0)
        mask = _mask(layer, grid)
        if mask is not None:
            vis = vis * mask
        vis = np.broadcast_to(np.asarray(vis, np.float32), under_a.shape)
        if layer.layer_type == "GROUP":
            if layer.group_mode == "PASS_THROUGH":
                content, content_a = _composite(stack, grid, layer.uid, under, under_a)
                if colour_adjusted(layer):
                    content = _colour_adjust(layer, content)
                under = under + (content - under) * vis[..., None]
                under_a = under_a + (content_a - under_a) * vis
                continue
            cs, a_src = _composite(stack, grid, layer.uid,
                                   np.zeros_like(under), np.zeros_like(under_a))
        else:
            cs, a_src = _layer_source(layer, stack, grid, under)
        if colour_adjusted(layer):
            cs = _colour_adjust(layer, cs)
        if layer.blend_if:
            w = _blend_if(layer, cs, under)
            if w is not None:
                vis = vis * w
        under, under_a = blend(layer.blend_mode, under, under_a, cs, vis * a_src)
    return under, under_a


def flatten(mat, crop=None, out_size=None):
    """Flatten mat's stack -> float32 array (rows bottom-up, w, 4), RGBA with
    gamma-encoded colour (ready for an 8-bit image) and straight alpha."""
    stack = mat.plastron_stack
    grid = Grid(stack.width, stack.height, crop, out_size)
    w, h = grid.size
    col, alpha = _composite(stack, grid, "", np.zeros((h, w, 3), np.float32), np.zeros((h, w), np.float32))
    if stack.blend_space == "LINEAR":
        col = _encode(col)
    return np.concatenate((np.clip(col, 0, 1), np.clip(alpha, 0, 1)[..., None]), -1).astype(np.float32)
