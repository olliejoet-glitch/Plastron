"""Normal map analysis: UV islands, OpenGL/DirectX detection, height (least-squares
integration per island), curvature, blurs. Pure numpy, no bpy: safe to run on a worker thread.
Arrays are in UV space: row 0 = v 0 (bottom). Productionised from prototypes/phase0.
"""
import numpy as np


# ----------------------------------------------------------------------------- utilities

def box_blur(a, r, axis):
    """Box blur of radius r (window 2r+1) along axis, edge-clamped, via cumulative sums."""
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def gauss_blur(a, sigma):
    """~Gaussian blur: three box passes per axis."""
    if sigma <= 0.5:
        return a
    r = max(1, int(round(np.sqrt(12 * sigma * sigma / 3 + 1) - 1) // 2))
    for _ in range(3):
        a = box_blur(a, r, 0)
        a = box_blur(a, r, 1)
    return a


def masked_blur(a, mask, sigma):
    """Blur that never mixes values across the mask boundary (normalised convolution)."""
    m = mask.astype(np.float32)
    if a.ndim == 3:
        num = np.stack([gauss_blur(a[..., i] * m, sigma) for i in range(a.shape[2])], -1)
        den = gauss_blur(m, sigma)[..., None]
    else:
        num = gauss_blur(a * m, sigma)
        den = gauss_blur(m, sigma)
    return np.where(den > 1e-4, num / np.maximum(den, 1e-4), 0).astype(np.float32)


def dilate_fill(a, mask, pixels):
    """Extend values outward from mask by ~`pixels` px (padding for bilinear/mip sampling)."""
    a = np.where(mask[..., None] if a.ndim == 3 else mask, a, 0).astype(np.float32)
    m = mask.astype(np.float32)
    for _ in range(pixels):
        num = box_blur(box_blur(a * (m[..., None] if a.ndim == 3 else m), 1, 0), 1, 1)
        den = box_blur(box_blur(m, 1, 0), 1, 1)
        grow = (m == 0) & (den > 0)
        fill = num / np.maximum(den, 1e-6)[..., None] if a.ndim == 3 else num / np.maximum(den, 1e-6)
        a = np.where(grow[..., None] if a.ndim == 3 else grow, fill, a)
        m = np.where(grow, 1.0, m)
    return a


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / np.maximum(e1 - e0, 1e-6), 0, 1)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------- UV islands

def uv_islands(tris, uv, loop_vert, loop_poly):
    """Island id per loop: loops connect within a polygon and across shared (vertex, uv)."""
    key = np.stack([loop_vert, np.round(uv[:, 0] * 1e5).astype(np.int64),
                    np.round(uv[:, 1] * 1e5).astype(np.int64)], 1)
    _, node = np.unique(key, axis=0, return_inverse=True)
    node = node.ravel()
    # edges: consecutive loops of the same polygon (loops of a poly are contiguous)
    same = loop_poly[1:] == loop_poly[:-1]
    ea, eb = node[:-1][same], node[1:][same]
    lab = np.arange(node.max() + 1)
    while True:  # min-label propagation + pointer jumping until stable
        m = np.minimum(lab[ea], lab[eb])
        new = lab.copy()
        np.minimum.at(new, ea, m)
        np.minimum.at(new, eb, m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    _, island = np.unique(lab[node], return_inverse=True)
    return island.ravel()


def rasterize_islands(tris, uv, loop_island, res):
    """Island id per texel (-1 = empty). Pixel centres, top-left-ish fill rule."""
    out = np.full((res, res), -1, np.int32)
    P = uv[tris] * res
    isl = loop_island[tris[:, 0]]
    for t, k in zip(P, isl):
        x0, y0 = np.maximum(np.floor(t.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(t.max(0)).astype(int), res)
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1] + 0.5

        def e(a, b):
            return (b[0] - a[0]) * (ys - a[1]) - (b[1] - a[1]) * (xs - a[0])

        w0, w1, w2 = e(t[1], t[2]), e(t[2], t[0]), e(t[0], t[1])
        ins = ((w0 >= 0) & (w1 >= 0) & (w2 >= 0)) | ((w0 <= 0) & (w1 <= 0) & (w2 <= 0))
        sub = out[y0:y1, x0:x1]
        sub[ins] = k
    return out


# ----------------------------------------------------------------------------- gradients

def decode(normal, flip_y):
    n = normal * 2 - 1
    if flip_y:
        n[..., 1] = -n[..., 1]
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    return n


def slopes(n):
    nz = np.maximum(n[..., 2], 0.2)
    return -n[..., 0] / nz, -n[..., 1] / nz  # dh/du, dh/dv in texel units


def curl_error(p, q, island):
    """Mean |dp/dv - dq/du| over texels whose right & up neighbours are in the same island."""
    ok = (island[:-1, :-1] >= 0) & (island[:-1, :-1] == island[1:, :-1]) & (island[:-1, :-1] == island[:-1, 1:])
    c = (p[1:, :-1] - p[:-1, :-1]) - (q[:-1, 1:] - q[:-1, :-1])
    return float(np.abs(c[ok]).mean())


def detect_convention(normal, island):
    """Return 'OPENGL' or 'DIRECTX' (whichever gives the more integrable gradient field)."""
    errs = {}
    for name, flip in (("OPENGL", False), ("DIRECTX", True)):
        p, q = slopes(decode(normal.copy(), flip))
        errs[name] = curl_error(p, q, island)
    return min(errs, key=errs.get), errs


# ----------------------------------------------------------------------------- integration

def _edges(island):
    hx = (island[:, :-1] >= 0) & (island[:, :-1] == island[:, 1:])
    hy = (island[:-1, :] >= 0) & (island[:-1, :] == island[1:, :])
    return hx.astype(np.float32), hy.astype(np.float32)


def _laplace(h, hx, hy):
    """Graph Laplacian (masked, Neumann at island borders) applied to h."""
    out = np.zeros_like(h)
    dx = (h[:, 1:] - h[:, :-1]) * hx
    dy = (h[1:, :] - h[:-1, :]) * hy
    out[:, :-1] -= dx
    out[:, 1:] += dx
    out[:-1, :] -= dy
    out[1:, :] += dy
    return out  # (L h)_i = sum_j (h_i - h_j): positive semi-definite


def _cg(h, p, q, island, iters, tol=1e-6):
    hx, hy = _edges(island)
    gx = 0.5 * (p[:, :-1] + p[:, 1:]) * hx
    gy = 0.5 * (q[:-1, :] + q[1:, :]) * hy
    b = np.zeros_like(h)  # normal equations of sum_e (h_j - h_i - g_e)^2  ->  L h = b
    b[:, :-1] -= gx
    b[:, 1:] += gx
    b[:-1, :] -= gy
    b[1:, :] += gy
    deg = np.zeros_like(h)
    deg[:, :-1] += hx
    deg[:, 1:] += hx
    deg[:-1, :] += hy
    deg[1:, :] += hy
    Minv = np.where(deg > 0, 1.0 / np.maximum(deg, 1), 0).astype(np.float32)
    r = b - _laplace(h, hx, hy)
    z = r * Minv
    d = z.copy()
    rz = float((r * z).sum())
    b_norm = float(np.sqrt((b * b).sum())) + 1e-12
    for i in range(iters):
        Ad = _laplace(d, hx, hy)
        dAd = float((d * Ad).sum())
        if dAd <= 0:
            break
        a = rz / dAd
        h += a * d
        r -= a * Ad
        if np.sqrt(float((r * r).sum())) / b_norm < tol:
            break
        z = r * Minv
        rz_new = float((r * z).sum())
        d = z + (rz_new / rz) * d
        rz = rz_new
    return h, i + 1


def _down_island(island):
    a, b, c, d = island[0::2, 0::2], island[1::2, 0::2], island[0::2, 1::2], island[1::2, 1::2]
    return np.where((a == b) & (a == c) & (a == d), a, -1)


def _down(x):
    return 0.25 * (x[0::2, 0::2] + x[1::2, 0::2] + x[0::2, 1::2] + x[1::2, 1::2])


def integrate_height(p, q, island, levels=4, iters=(400, 300, 200, 150, 120)):
    """Least-squares height per island, coarse-to-fine CG. Returns height in texel units."""
    pyr = [(p, q, island)]
    for _ in range(levels):
        pp, qq, ii = pyr[-1]
        pyr.append((_down(pp) * 2, _down(qq) * 2, _down_island(ii)))  # slope per coarse texel
    h = np.zeros_like(pyr[-1][0])
    stats = []
    for lvl in range(len(pyr) - 1, -1, -1):
        pp, qq, ii = pyr[lvl]
        if h.shape != pp.shape:
            h = np.repeat(np.repeat(h, 2, 0), 2, 1)
        h = np.where(ii >= 0, h, 0).astype(np.float32)
        h, n = _cg(h, pp, qq, ii, iters[min(lvl, len(iters) - 1)])
        stats.append((pp.shape[0], n))
    # zero-mean per island (absolute offset between islands is unknowable)
    ids = island[island >= 0]
    sums = np.bincount(ids, weights=h[island >= 0])
    cnt = np.bincount(ids)
    h[island >= 0] -= (sums / np.maximum(cnt, 1))[ids]
    h[island < 0] = 0
    return h, stats


# ----------------------------------------------------------------------------- derived maps

def normalise(x, mask, lo=1, hi=99, centre=None):
    v = x[mask]
    a, b = np.percentile(v, [lo, hi])
    if centre is not None:  # symmetric around centre -> 0.5
        s = max(abs(a - centre), abs(b - centre), 1e-6)
        return np.clip(0.5 + (x - centre) / (2 * s), 0, 1)
    return np.clip((x - a) / max(b - a, 1e-6), 0, 1)


def curvature(n, mask, sigma):
    """Divergence of the tangent-space normal field: >0 convex (edges), <0 concave (cavities)."""
    nb = masked_blur(n[..., :2], mask, sigma) if sigma > 0 else n[..., :2]
    div = np.zeros(mask.shape, np.float32)
    div[:, 1:-1] += 0.5 * (nb[:, 2:, 0] - nb[:, :-2, 0])
    div[1:-1, :] += 0.5 * (nb[2:, :, 1] - nb[:-2, :, 1])
    # only trust texels whose neighbours are inside the island
    inner = mask.copy()
    inner[:, 1:-1] &= mask[:, 2:] & mask[:, :-2]
    inner[1:-1, :] &= mask[2:, :] & mask[:-2, :]
    return np.where(inner, div, 0)


def detail(height, mask, radius):
    """'Detail size' signal: height minus height blurred at `radius` texels (per island)."""
    return np.where(mask, height - masked_blur(height, mask, radius), 0)


def depth_mask(det, threshold, softness, invert=False):
    m = smoothstep(threshold - softness, threshold + softness, det)
    return 1 - m if invert else m
