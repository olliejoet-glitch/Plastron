"""Screen <-> texture projection on the GPU (lasso selection, transform/warp).

Everything is expressed with explicit inputs (mesh arrays, view-projection matrix, screen size)
so it can be tested headlessly (call gpu.init() first in background mode).

Conventions
- Screen arrays: (h, w, C) float32, row 0 = bottom (region coordinates).
- Texture arrays: (res, res, C) float32, row 0 = v 0, values as stored in the image (for 8-bit
  sRGB images that is the gamma-encoded value; we never colour-convert here).
- "Visible" texel = its surface point is the front-most surface at its screen pixel.
"""
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

_SHADERS = {}
VS_SCREEN = ("void main(){ v_uv = uv; v_clip = VP * vec4(P, 1.0); v_depth = -(V * vec4(P, 1.0)).z;"
             " gl_Position = v_clip; }")


# ----------------------------------------------------------------------------- mesh

def mesh_arrays(obj, depsgraph, uv_name="", normals=False):
    """World-space triangle soup (P (n,3), uv (n,2)[, N (n,3)]) of the evaluated object."""
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        tri_loops = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("loops", tri_loops)
        loop_vert = np.empty(len(me.loops), np.int32)
        me.loops.foreach_get("vertex_index", loop_vert)
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        layer = me.uv_layers.get(uv_name) if uv_name else me.uv_layers.active
        uv = np.empty(len(me.loops) * 2, np.float32)
        layer.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        mw = np.array(obj.matrix_world, np.float32)
        P = co[loop_vert[tri_loops]] @ mw[:3, :3].T + mw[:3, 3]
        if not normals:
            return P.astype(np.float32), uv[tri_loops].astype(np.float32)
        cn = np.empty(len(me.loops) * 3, np.float32)
        me.corner_normals.foreach_get("vector", cn)
        N = cn.reshape(-1, 3)[tri_loops] @ np.linalg.inv(mw[:3, :3])  # inverse-transpose
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        return P.astype(np.float32), uv[tri_loops].astype(np.float32), N.astype(np.float32)
    finally:
        ev.to_mesh_clear()


# ----------------------------------------------------------------------------- shaders

def _shader(name):
    if name in _SHADERS:
        return _SHADERS[name]
    info = gpu.types.GPUShaderCreateInfo()
    iface = gpu.types.GPUStageInterfaceInfo("pl_" + name.lower())
    if name in ("SCREEN", "SNAP", "UVPROJ"):
        info.vertex_in(0, 'VEC3', 'P')
        info.vertex_in(1, 'VEC2', 'uv')
        info.push_constant('MAT4', 'VP')
        info.push_constant('MAT4', 'V')
        iface.smooth('VEC2', 'v_uv')
        iface.smooth('VEC4', 'v_clip')
        iface.smooth('FLOAT', 'v_depth')   # view-space distance along the view axis
        info.vertex_out(iface)
    if name == "SCREEN":
        # per screen pixel: (u, v, view depth, coverage) of the front-most surface
        info.fragment_out(0, 'VEC4', 'FragColor')
        info.vertex_source(VS_SCREEN)
        info.fragment_source("void main(){ FragColor = vec4(v_uv, v_depth, 1.0); }")
    elif name == "SNAP":
        # the layer (straight RGBA) x selection, as premultiplied colour on screen
        info.sampler(0, 'FLOAT_2D', 'layer_tex')
        info.sampler(1, 'FLOAT_2D', 'sel_tex')
        info.push_constant('FLOAT', 'use_sel')
        info.fragment_out(0, 'VEC4', 'FragColor')
        info.vertex_source(VS_SCREEN)
        info.fragment_source(
            "void main(){ vec4 c = texture(layer_tex, v_uv);"
            " float m = use_sel > 0.5 ? texture(sel_tex, v_uv).r : 1.0;"
            " float a = c.a * m; FragColor = vec4(c.rgb * a, a); }")
    elif name == "UVPROJ":
        # draw in UV space; fetch the screen image under each visible texel
        info.sampler(0, 'FLOAT_2D', 'screen_tex')   # SCREEN pass result
        info.sampler(1, 'FLOAT_2D', 'src_tex')      # what to project (premultiplied / mask)
        info.push_constant('VEC2', 'size')
        info.push_constant('VEC2', 'tol')            # depth tolerance: relative, absolute
        info.fragment_out(0, 'VEC4', 'FragColor')   # projected value (0 where not visible)
        info.fragment_out(1, 'VEC4', 'Coverage')    # (visible, inside mesh, 0, 1)
        info.vertex_source("void main(){ v_uv = uv; v_clip = VP * vec4(P, 1.0);"
                           " v_depth = -(V * vec4(P, 1.0)).z;"
                           " gl_Position = vec4(uv * 2.0 - 1.0, 0.0, 1.0); }")
        info.fragment_source(
            "void main(){"
            " float vis = 0.0; vec4 s = vec4(0.0);"
            " if (v_clip.w > 1e-6) {"
            "  vec2 sc = (v_clip.xy / v_clip.w) * 0.5 + 0.5;"
            "  if (all(greaterThanEqual(sc, vec2(0.0))) && all(lessThan(sc, vec2(1.0)))) {"
            "   ivec2 px = ivec2(sc * size);"
            "   float tolerance = tol.x * abs(v_depth) + tol.y;"
            # visible if the front-most surface at this pixel (or a neighbour: grazing angles,
            # silhouettes) is this texel's surface
            "   float best = 1e30;"
            "   for (int dy = -1; dy <= 1; dy++) for (int dx = -1; dx <= 1; dx++) {"
            "    ivec2 q = clamp(px + ivec2(dx, dy), ivec2(0), ivec2(size) - 1);"
            "    vec4 scr = texelFetch(screen_tex, q, 0);"
            "    if (scr.a > 0.5) best = min(best, abs(scr.b - v_depth));"
            "   }"
            "   if (best < tolerance) { vis = 1.0; s = texture(src_tex, sc); }"
            "  }"
            " }"
            " FragColor = s; Coverage = vec4(vis, 1.0, 0.0, 1.0); }")
    elif name == "OVERLAY":
        # 2D textured mesh in region pixels (transform preview / warped bake)
        info.vertex_in(0, 'VEC2', 'pos')
        info.vertex_in(1, 'VEC2', 'tc')
        info.push_constant('VEC2', 'size')
        info.push_constant('FLOAT', 'opacity')
        info.sampler(0, 'FLOAT_2D', 'img')
        iface.smooth('VEC2', 'v_tc')
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', 'FragColor')
        info.vertex_source("void main(){ v_tc = tc; gl_Position = vec4(pos / size * 2.0 - 1.0, 0.0, 1.0); }")
        info.fragment_source("void main(){ FragColor = texture(img, v_tc) * opacity; }")
    sh = gpu.shader.create_from_info(info)
    _SHADERS[name] = sh
    return sh


# ----------------------------------------------------------------------------- helpers

def texture(arr):
    """float32 (h, w, 4) or (h, w) array -> GPUTexture."""
    arr = np.ascontiguousarray(arr, np.float32)
    h, w = arr.shape[:2]
    fmt = 'RGBA32F' if arr.ndim == 3 else 'R32F'
    buf = gpu.types.Buffer('FLOAT', arr.size, arr.reshape(-1))
    return gpu.types.GPUTexture((w, h), format=fmt, data=buf)


def _read(tex, h, w):
    return np.asarray(tex.read(), dtype=np.float32).reshape(h, w, 4).copy()


def _mat(m):
    import mathutils
    return m if isinstance(m, mathutils.Matrix) else mathutils.Matrix(m)


class Projector:
    """One mesh seen from one view. Reuse for several passes while the view doesn't change."""

    def __init__(self, P, uv, view, proj, size, tol=(0.006, 1e-4)):
        self.size = (int(size[0]), int(size[1]))  # (w, h)
        self.tol = tol  # depth match: relative (perspective views), absolute (ortho decal views)
        self.V = _mat(view)
        self.VP = _mat(proj) @ self.V
        self.P, self.uv = P, uv
        self._batches = {}
        self.screen = None  # (h, w, 4): u, v, view depth, coverage

    def _batch(self, name):
        if name not in self._batches:
            self._batches[name] = batch_for_shader(_shader(name), 'TRIS', {"P": self.P, "uv": self.uv})
        return self._batches[name]

    def _draw_screen_pass(self, name, setup):
        w, h = self.size
        col = gpu.types.GPUTexture((w, h), format='RGBA32F')
        dep = gpu.types.GPUTexture((w, h), format='DEPTH_COMPONENT32F')
        fb = gpu.types.GPUFrameBuffer(color_slots=(col,), depth_slot=dep)
        sh = _shader(name)
        with fb.bind():
            fb.clear(color=(0, 0, 0, 0), depth=1.0)
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.depth_mask_set(True)
            gpu.state.blend_set('NONE')
            sh.bind()
            sh.uniform_float("VP", self.VP)
            try:
                sh.uniform_float("V", self.V)  # optimised away in shaders that don't use depth
            except ValueError:
                pass
            setup(sh)
            self._batch(name).draw(sh)
            gpu.state.depth_test_set('NONE')
            gpu.state.depth_mask_set(False)
        return _read(col, h, w)

    def screen_pass(self):
        if self.screen is None:
            self.screen = self._draw_screen_pass("SCREEN", lambda sh: None)
        return self.screen

    def snapshot(self, layer_rgba, selection=None):
        """Premultiplied (h, w, 4) screen image of the layer (x selection)."""
        lt = texture(layer_rgba)
        st = texture(selection if selection is not None else np.ones((4, 4), np.float32))

        def setup(sh):
            sh.uniform_sampler("layer_tex", lt)
            sh.uniform_sampler("sel_tex", st)
            sh.uniform_float("use_sel", 1.0 if selection is not None else 0.0)
        return self._draw_screen_pass("SNAP", setup)

    def to_texture(self, screen_src, res):
        """Project a screen image (h, w, 4) onto the texture. Returns (values, visible, inside):
        values (res, res, 4) are 0 where the texel isn't visible."""
        w, h = self.size
        scr_t = texture(self.screen_pass())
        src_t = texture(screen_src if screen_src.ndim == 3 else
                        np.repeat(screen_src[..., None], 4, 2))
        out = gpu.types.GPUTexture((res, res), format='RGBA32F')
        cov = gpu.types.GPUTexture((res, res), format='RGBA32F')
        fb = gpu.types.GPUFrameBuffer(color_slots=(out, cov))
        sh = _shader("UVPROJ")
        with fb.bind():
            fb.clear(color=(0, 0, 0, 0))
            gpu.state.depth_test_set('NONE')
            gpu.state.blend_set('NONE')
            sh.bind()
            sh.uniform_float("VP", self.VP)
            sh.uniform_float("V", self.V)
            sh.uniform_float("size", (float(w), float(h)))
            sh.uniform_float("tol", tuple(float(x) for x in self.tol))
            sh.uniform_sampler("screen_tex", scr_t)
            sh.uniform_sampler("src_tex", src_t)
            self._batch("UVPROJ").draw(sh)
        c = _read(cov, res, res)
        return _read(out, res, res), c[..., 0], c[..., 1]


def draw_lattice(src_tex, grid_xy, src_rect, size, opacity=1.0, target=None, src_size=None):
    """Draw src_tex (premultiplied) mapped through a lattice.

    grid_xy: (n+1, n+1, 2) region-pixel positions of lattice points (row = v, col = u).
    src_rect: (x0, y0, x1, y1) region pixels of the source rectangle the lattice covers.
    target None -> draw into the current framebuffer (viewport overlay), else returns an
    offscreen (h, w, 4) premultiplied render.
    """
    n = grid_xy.shape[0] - 1
    w, h = size
    sw, sh_ = src_size or size  # the source may come from a differently sized view
    us = np.linspace(0, 1, n + 1, dtype=np.float32)
    U, V = np.meshgrid(us, us)
    tc = np.stack([(src_rect[0] + U * (src_rect[2] - src_rect[0])) / sw,
                   (src_rect[1] + V * (src_rect[3] - src_rect[1])) / sh_], -1)
    i, j = np.meshgrid(np.arange(n), np.arange(n))
    a = (j * (n + 1) + i).ravel()
    quads = np.stack([a, a + 1, a + n + 2, a, a + n + 2, a + n + 1], 1).ravel()
    pos = grid_xy.reshape(-1, 2)[quads].astype(np.float32)
    tcs = tc.reshape(-1, 2)[quads].astype(np.float32)
    sh = _shader("OVERLAY")
    batch = batch_for_shader(sh, 'TRIS', {"pos": pos, "tc": tcs})

    def go():
        gpu.state.blend_set('ALPHA_PREMULT')
        sh.bind()
        sh.uniform_float("size", (float(w), float(h)))
        sh.uniform_float("opacity", float(opacity))
        sh.uniform_sampler("img", src_tex)
        batch.draw(sh)
        gpu.state.blend_set('NONE')

    if target is None:
        go()
        return None
    col = gpu.types.GPUTexture((w, h), format='RGBA32F')
    fb = gpu.types.GPUFrameBuffer(color_slots=(col,))
    with fb.bind():
        fb.clear(color=(0, 0, 0, 0))
        go()
    return _read(col, h, w)


# ----------------------------------------------------------------------------- CPU helpers

def polygon_mask(points, size):
    """Even-odd scanline fill of a screen polygon -> (h, w) float32 mask."""
    w, h = size
    pts = np.asarray(points, np.float64)
    mask = np.zeros((h, w), np.float32)
    if len(pts) < 3:
        return mask
    x0, y0 = pts[:, 0], pts[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    ys = np.arange(h) + 0.5
    for row, y in enumerate(ys):
        cross = ((y0 <= y) & (y1 > y)) | ((y1 <= y) & (y0 > y))
        if not cross.any():
            continue
        xs = np.sort(x0[cross] + (y - y0[cross]) * (x1[cross] - x0[cross]) / (y1[cross] - y0[cross]))
        for a, b in zip(xs[0::2], xs[1::2]):
            lo, hi = int(np.ceil(a - 0.5)), int(np.floor(b - 0.5))
            if hi >= lo:
                mask[row, max(lo, 0):min(hi + 1, w)] = 1.0
    return mask


def _box(a, r, axis):
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    return ((np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
             - np.take(c, np.arange(n), axis=axis)) / (2 * r + 1)).astype(np.float32)


def blur(a, radius):
    """~Gaussian blur (3 box passes)."""
    r = max(0, int(round(radius / 1.7)))
    for _ in range(3):
        a = _box(_box(a, r, 0), r, 1)
    return a


def bleed(values, inside, pixels=4):
    """Extend values from texels inside the mesh into the UV gutter (seams paint cleanly)."""
    v = values.astype(np.float32)
    m = inside.astype(np.float32)
    for _ in range(pixels):
        num = _box(_box(v * m, 1, 0), 1, 1)
        den = _box(_box(m, 1, 0), 1, 1)
        grow = (m < 0.5) & (den > 1e-6)
        v = np.where(grow, num / np.maximum(den, 1e-6), v)
        m = np.where(grow, 1.0, m)
    return v


def bezier_patch(ctrl, n=32):
    """Bicubic Bezier patch: ctrl (4, 4, 2) -> lattice (n+1, n+1, 2). Row = v, col = u."""
    t = np.linspace(0, 1, n + 1)
    B = np.stack([(1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t ** 2 * (1 - t), t ** 3], 1)  # (n+1, 4)
    return np.einsum('vi,uj,ijk->vuk', B, B, ctrl)


def homography(src, dst):
    """3x3 H with H @ [x, y, 1] ~ dst for 4 point pairs."""
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.asarray(A, np.float64))
    return vt[-1].reshape(3, 3)


def quad_lattice(corners, n=32):
    """Perspective lattice for a quad (corners in order: (0,0), (1,0), (1,1), (0,1))."""
    H = homography([(0, 0), (1, 0), (1, 1), (0, 1)], corners)
    t = np.linspace(0, 1, n + 1)
    U, V = np.meshgrid(t, t)
    p = np.stack([U, V, np.ones_like(U)], -1) @ H.T
    return p[..., :2] / p[..., 2:3]
