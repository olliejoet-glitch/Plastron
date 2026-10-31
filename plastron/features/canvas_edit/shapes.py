"""Pixel geometry for selections and transforms. Pure numpy (no Blender),
so it's easy to test.

Coordinates are canvas pixels: x right, y up, (0, 0) the bottom-left corner
of the painting; arrays are rows bottom-up like Blender images.
"""

import numpy as np


# --- selections -------------------------------------------------------------------------

def polygon_mask(points, width, height):
    """Even-odd fill of a polygon (canvas pixel coordinates) -> float32 mask."""
    pts = np.asarray(points, np.float64)
    if len(pts) < 3:
        return np.zeros((height, width), np.float32)
    x0, y0 = pts[:, 0], pts[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    ys = np.arange(height) + 0.5
    # crossings[row, edge]: does the edge cross this row's centre line, and where
    lo, hi = np.minimum(y0, y1), np.maximum(y0, y1)
    crosses = (ys[:, None] >= lo[None, :]) & (ys[:, None] < hi[None, :])
    with np.errstate(divide='ignore', invalid='ignore'):     # (flat edges never cross)
        t = (ys[:, None] - y0[None, :]) / (y1 - y0)[None, :]
        xs = x0[None, :] + t * (x1 - x0)[None, :]
    rows, edges = np.nonzero(crosses)
    cols = np.clip(np.ceil(xs[rows, edges] - 0.5), 0, width).astype(np.int64)
    toggles = np.zeros((height, width + 1), np.int32)
    np.add.at(toggles, (rows, cols), 1)
    inside = (np.cumsum(toggles, axis=1)[:, :width] % 2).astype(np.float32)
    return inside


def rect_mask(x0, y0, x1, y1, width, height):
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    m = np.zeros((height, width), np.float32)
    m[max(0, int(round(ya))):max(0, int(round(yb))), max(0, int(round(xa))):max(0, int(round(xb)))] = 1.0
    return m


def combine(old, new, mode):
    """mode: 'SET', 'ADD' (Shift) or 'SUB' (Alt)."""
    if old is None or mode == 'SET':
        return new if mode != 'SUB' else np.zeros_like(new)
    if mode == 'ADD':
        return np.maximum(old, new)
    return old * (1.0 - new)


def bbox(mask, threshold=0.0):
    """(x0, y0, x1, y1) of mask > threshold (x1 / y1 exclusive), or None."""
    ys, xs = np.nonzero(mask > threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def outline(mask):
    """1-pixel boundary of a selection (for drawing it)."""
    m = mask > 0.5
    inner = m.copy()
    inner[1:, :] &= m[:-1, :]
    inner[:-1, :] &= m[1:, :]
    inner[:, 1:] &= m[:, :-1]
    inner[:, :-1] &= m[:, 1:]
    return m & ~inner


# --- transforms ---------------------------------------------------------------------------

def homography(src, dst):
    """3x3 matrix mapping the 4 src points onto the 4 dst points."""
    a = []
    b = []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    h = np.linalg.solve(np.asarray(a, np.float64), np.asarray(b, np.float64))
    return np.append(h, 1.0).reshape(3, 3)


def apply_h(h, pts):
    pts = np.asarray(pts, np.float64)
    p = np.c_[pts, np.ones(len(pts))] @ h.T
    return p[:, :2] / p[:, 2:3]


def rect_corners(x0, y0, x1, y1):
    """Counter-clockwise from bottom-left."""
    return np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], np.float64)


def grid_from_corners(corners, n):
    """(n+1)x(n+1) points: the rectangle's grid carried by the projective map
    onto corners (what free transform / distort look like)."""
    h = homography(rect_corners(0, 0, 1, 1), corners)
    s = np.linspace(0, 1, n + 1)
    uu, vv = np.meshgrid(s, s)
    return apply_h(h, np.c_[uu.ravel(), vv.ravel()]).reshape(n + 1, n + 1, 2)


def _bernstein(t):
    t = np.asarray(t, np.float64)
    return np.stack([(1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t ** 2 * (1 - t), t ** 3], -1)


def grid_from_warp(points, n):
    """Smooth (bicubic) surface passing THROUGH a 4x4 grid of warp points,
    sampled into an (n+1)x(n+1) grid: dragging a point moves the drawing
    right there. points[row][col] = (x, y), row 0 at the bottom."""
    p = np.asarray(points, np.float64)
    at = _bernstein(np.linspace(0, 1, 4))          # where the points sit on the surface
    inv = np.linalg.inv(at)
    control = np.einsum('ri,cj,ijd->rcd', inv, inv, p)
    b = _bernstein(np.linspace(0, 1, n + 1))
    return np.einsum('ir,jc,rcd->ijd', b, b, control)


def warp_from_corners(corners):
    """Starting warp control points for a free-transformed box."""
    return grid_from_corners(corners, 3)


def render(src, grid, out_w, out_h):
    """Draw src (rows bottom-up, RGBA straight alpha) through a deformed grid:
    grid[i][j] is where src's point (j/n, i/n) lands. Returns (premultiplied
    RGBA canvas of out size, coverage). Each grid cell is resampled with its
    own homography (bilinear sampling)."""
    n = grid.shape[0] - 1
    sh, sw = src.shape[:2]
    pre = src.astype(np.float32).copy()
    pre[..., :3] *= pre[..., 3:4]
    out = np.zeros((out_h, out_w, 4), np.float32)
    for i in range(n):
        for j in range(n):
            quad = np.array([grid[i, j], grid[i, j + 1], grid[i + 1, j + 1], grid[i + 1, j]])
            xa, ya = np.floor(quad.min(0)).astype(int)
            xb, yb = np.ceil(quad.max(0)).astype(int)
            xa, ya, xb, yb = max(xa, 0), max(ya, 0), min(xb, out_w), min(yb, out_h)
            if xa >= xb or ya >= yb:
                continue
            cell = rect_corners(j * sw / n, i * sh / n, (j + 1) * sw / n, (i + 1) * sh / n)
            try:
                back = homography(quad, cell)
            except np.linalg.LinAlgError:
                continue
            yy, xx = np.mgrid[ya:yb, xa:xb]
            p = apply_h(back, np.c_[xx.ravel() + 0.5, yy.ravel() + 0.5])
            u, v = p[:, 0], p[:, 1]
            cx0, cy0, cx1, cy1 = cell[0][0], cell[0][1], cell[2][0], cell[2][1]
            eps = 1e-6
            inside = (u >= cx0 - eps) & (u < cx1 + eps) & (v >= cy0 - eps) & (v < cy1 + eps)
            if not inside.any():
                continue
            vals = _bilinear(pre, u[inside] - 0.5, v[inside] - 0.5)
            rows = yy.ravel()[inside]
            cols = xx.ravel()[inside]
            out[rows, cols] = vals
    return out


def _bilinear(img, x, y):
    h, w = img.shape[:2]
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]

    def at(xx, yy):
        ok = (xx >= 0) & (xx < w) & (yy >= 0) & (yy < h)
        v = np.zeros((len(xx), img.shape[2]), np.float32)
        v[ok] = img[yy[ok], xx[ok]]
        return v
    return ((at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx) * (1 - fy) +
            (at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx) * fy)


def over(base, top_pre):
    """Composite premultiplied top over straight-alpha base -> straight alpha."""
    a_t = top_pre[..., 3:4]
    a_b = base[..., 3:4]
    a = a_t + a_b * (1 - a_t)
    col = top_pre[..., :3] + base[..., :3] * a_b * (1 - a_t)
    out = np.empty_like(base)
    out[..., :3] = np.where(a > 1e-6, col / np.maximum(a, 1e-6), 0.0)
    out[..., 3:4] = a
    return out
