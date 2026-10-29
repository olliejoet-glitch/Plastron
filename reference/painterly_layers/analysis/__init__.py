"""Normal-map derived data (Phase 2). `compute_derived` is pure numpy: run it on a worker thread.

Outputs (UV space, float32, row 0 = v 0):
  height  RGBA = detail height at radius 4 / 16 / 48 / 128 texels  (0.5 = locally mid-height)
  curve   RGBA = convex fine, cavity fine, convex broad, cavity broad  (0..1)
  forms_a RGBA = tangent normal XY blurred at FORM_SIGMAS[0], [1]   (encoded *0.5+0.5)
  forms_b RGBA = ... at FORM_SIGMAS[2], [3]
  forms_c RGBA = ... at FORM_SIGMAS[4], [5]                         ("form size" for light layers)
"""
import numpy as np

from . import normals as nrm

DETAIL_RADII = (4, 16, 48, 128)
FORM_SIGMAS = (1.0, 2.0, 4.0, 8.0, 20.0, 48.0)  # fine steps first: tiny scales


def compute_derived(normal, tris, uv, loop_vert, loop_poly, progress=lambda f, msg: None):
    h0, w0 = normal.shape[:2]
    res = max(h0, w0)
    if (h0, w0) != (res, res):  # analysis works on a square grid
        ys = (np.arange(res) * h0 / res).astype(int)
        xs = (np.arange(res) * w0 / res).astype(int)
        normal = normal[ys][:, xs]
    progress(0.02, "UV islands")
    loop_island = nrm.uv_islands(tris, uv, loop_vert, loop_poly)
    island = nrm.rasterize_islands(tris, uv, loop_island, res)
    mask = island >= 0
    if not mask.any():
        raise ValueError("the mesh's UVs don't cover the normal map")
    progress(0.12, "normal map convention")
    conv, _ = nrm.detect_convention(normal, island)
    n = nrm.decode(normal.astype(np.float32).copy(), conv == "DIRECTX")
    p, q = nrm.slopes(n)
    progress(0.18, "height (this is the slow part)")
    h, _ = nrm.integrate_height(p, q, island)
    progress(0.82, "detail levels")

    def norm(x):
        return nrm.normalise(x, mask, lo=5, hi=95, centre=0)

    height = np.stack([norm(nrm.detail(h, mask, r)) for r in DETAIL_RADII], -1)
    progress(0.9, "curvature")
    curves = []
    for sigma in (1.0, 6.0):
        c = nrm.normalise(nrm.curvature(n, mask, sigma), mask, lo=2, hi=98, centre=0)
        curves += [np.clip((c - 0.5) * 2, 0, 1), np.clip((0.5 - c) * 2, 0, 1)]
    curve = np.stack(curves, -1)
    progress(0.93, "form sizes")
    xy = []
    for sigma in FORM_SIGMAS:  # normals blurred within islands: light falls on broad planes
        nb = nrm.masked_blur(n, mask, sigma)
        nb /= np.maximum(np.linalg.norm(nb, axis=-1, keepdims=True), 1e-6)
        xy += [nb[..., 0] * 0.5 + 0.5, nb[..., 1] * 0.5 + 0.5]
    forms_a = np.stack(xy[0:4], -1)
    forms_b = np.stack(xy[4:8], -1)
    forms_c = np.stack(xy[8:12], -1)
    progress(0.97, "padding seams")
    height = nrm.dilate_fill(height, mask, 8)
    curve = nrm.dilate_fill(curve, mask, 8)
    forms_a = nrm.dilate_fill(forms_a, mask, 8)
    forms_b = nrm.dilate_fill(forms_b, mask, 8)
    forms_c = nrm.dilate_fill(forms_c, mask, 8)
    grown = nrm.dilate_fill(mask.astype(np.float32), mask, 8) > 0.5
    height[~grown] = 0.5  # never sampled; neutral anyway
    progress(1.0, "done")
    if conv == "DIRECTX":  # stored like the sharp map is read (OpenGL), flip back for the shader
        forms_a[..., 1::2] = 1.0 - forms_a[..., 1::2]
        forms_b[..., 1::2] = 1.0 - forms_b[..., 1::2]
        forms_c[..., 1::2] = 1.0 - forms_c[..., 1::2]
    return (height.astype(np.float32), curve.astype(np.float32), forms_a.astype(np.float32),
            forms_b.astype(np.float32), forms_c.astype(np.float32), conv)
