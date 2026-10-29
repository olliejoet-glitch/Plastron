"""Surface decals for the transform tool.

A decal is a flat 2D canvas lying on the surface: an anchor point `a` and an orthonormal frame
(t, b, n) with n = average surface normal. Plane coordinates (x, y) are world units along t, b.
An orthographic "decal camera" looks down -n at the canvas; projecting through it puts the
canvas onto the front-most surface underneath (never through to the far side). Because all of
this lives in world space, the decal stays stuck to the mesh while the user navigates, and
"moving" it re-anchors the frame on the surface under the cursor, so it slides over curvature.
"""
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from . import Projector, _read, texture

_SHADERS = {}


class Frame:
    def __init__(self, a, n, t_hint):
        n = Vector(n).normalized()
        t = Vector(t_hint) - n * Vector(t_hint).dot(n)
        if t.length < 1e-6:
            t = n.orthogonal()
        t.normalize()
        self.a, self.n, self.t, self.b = Vector(a), n, t, n.cross(t)

    def plane(self, P):
        """world -> plane coords; P (3,) Vector or (k, 3) array."""
        if isinstance(P, np.ndarray):
            d = P - np.array(self.a)
            return np.stack([d @ np.array(self.t), d @ np.array(self.b)], -1)
        d = Vector(P) - self.a
        return np.array([d.dot(self.t), d.dot(self.b)])

    def world(self, xy):
        """plane coords (..., 2) -> world points (..., 3) array."""
        xy = np.asarray(xy, float)
        return np.array(self.a) + xy[..., :1] * np.array(self.t) + xy[..., 1:2] * np.array(self.b)

    def slid(self, hit, normal, grab):
        """New frame on the surface: plane point `grab` lands on `hit`, n follows the surface,
        t is parallel-transported (no spin)."""
        f = Frame(self.a, normal, self.t)
        f.a = Vector(hit) - f.t * float(grab[0]) - f.b * float(grab[1])
        return f

    def view(self, dist):
        """world -> decal-camera view space; camera sits `dist` above the anchor, looking down -n."""
        t, b, n, a = self.t, self.b, self.n, self.a
        return Matrix(((t.x, t.y, t.z, -t.dot(a)),
                       (b.x, b.y, b.z, -b.dot(a)),
                       (n.x, n.y, n.z, -n.dot(a) - dist),
                       (0, 0, 0, 1)))


def mirror_matrices(obj, axes):
    """World-space reflections for every non-empty combination of the enabled symmetry axes
    (mirrored about the object's origin, like Blender's paint symmetry). -> [(M 4x4, odd)]."""
    import itertools
    mw = obj.matrix_world
    out = []
    idx = [i for i, on in enumerate(axes) if on]
    for k in range(1, len(idx) + 1):
        for combo in itertools.combinations(idx, k):
            s = [1.0, 1.0, 1.0]
            for i in combo:
                s[i] = -1.0
            S = Matrix.Diagonal((s[0], s[1], s[2], 1.0))
            out.append((mw @ S @ mw.inverted(), len(combo) % 2 == 1))
    return out


def mirror_frame(frame, M, odd):
    """The frame reflected by M. For an odd number of reflections the canvas comes out flipped
    in x (plane x -> -x), which mirror_rect / np.flip(axis=1) account for."""
    m3 = M.to_3x3()
    t = m3 @ frame.t
    return Frame(M @ frame.a, m3 @ frame.n, -t if odd else t)


def mirror_rect(rect, odd):
    return (-rect[2], rect[1], -rect[0], rect[3]) if odd else rect


def ortho(x0, x1, y0, y1, near, far):
    return Matrix(((2 / (x1 - x0), 0, 0, -(x1 + x0) / (x1 - x0)),
                   (0, 2 / (y1 - y0), 0, -(y1 + y0) / (y1 - y0)),
                   (0, 0, -2 / (far - near), -(far + near) / (far - near)),
                   (0, 0, 0, 1)))


def decal_matrices(frame, rect, depth):
    """(view, projection) of the decal camera covering plane rect (x0, y0, x1, y1), seeing
    surfaces within +-depth of the canvas along n."""
    dist = 2.0 * depth
    return frame.view(dist), ortho(rect[0], rect[2], rect[1], rect[3], dist - depth, dist + depth)


def decal_projector(P, uv, frame, rect, size, depth):
    view, proj = decal_matrices(frame, rect, depth)
    px = max((rect[2] - rect[0]) / size[0], (rect[3] - rect[1]) / size[1])
    return Projector(P, uv, view, proj, size, tol=(0.0, 3.0 * px + 1e-6))


# ----------------------------------------------------------------------------- UV-space positions

def _uvpos_shader():
    if "UVPOS" not in _SHADERS:
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC3', 'P')
        info.vertex_in(1, 'VEC2', 'uv')
        info.vertex_in(2, 'VEC3', 'N')
        iface = gpu.types.GPUStageInterfaceInfo("pl_uvpos")
        iface.smooth('VEC3', 'v_P')
        iface.smooth('VEC3', 'v_N')
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', 'OutP')
        info.fragment_out(1, 'VEC4', 'OutN')
        info.vertex_source("void main(){ v_P = P; v_N = N; gl_Position = vec4(uv * 2.0 - 1.0, 0.0, 1.0); }")
        info.fragment_source("void main(){ OutP = vec4(v_P, 1.0); OutN = vec4(normalize(v_N), 1.0); }")
        _SHADERS["UVPOS"] = gpu.shader.create_from_info(info)
    return _SHADERS["UVPOS"]


def uv_positions(P, uv, N, res):
    """World position, normal and coverage of every texel: ((res,res,3), (res,res,3), (res,res))."""
    sh = _uvpos_shader()
    batch = batch_for_shader(sh, 'TRIS', {"P": P, "uv": uv, "N": N})
    tp = gpu.types.GPUTexture((res, res), format='RGBA32F')
    tn = gpu.types.GPUTexture((res, res), format='RGBA32F')
    fb = gpu.types.GPUFrameBuffer(color_slots=(tp, tn))
    with fb.bind():
        fb.clear(color=(0, 0, 0, 0))
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')
        sh.bind()
        batch.draw(sh)
    p = _read(tp, res, res)
    n = _read(tn, res, res)
    return p[..., :3], n[..., :3], p[..., 3]


# ----------------------------------------------------------------------------- viewport preview

def _view_shader():
    if "VIEW" not in _SHADERS:
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC3', 'P')
        info.push_constant('MAT4', 'VP')
        info.push_constant('MAT4', 'DV')
        info.push_constant('MAT4', 'DP')
        info.push_constant('VEC2', 'size')
        info.push_constant('FLOAT', 'tol')
        info.sampler(0, 'FLOAT_2D', 'dmap')
        info.sampler(1, 'FLOAT_2D', 'wtex')
        iface = gpu.types.GPUStageInterfaceInfo("pl_decalview")
        iface.smooth('VEC3', 'v_P')
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', 'FragColor')
        info.vertex_source("void main(){ v_P = P; gl_Position = VP * vec4(P, 1.0);"
                           " gl_Position.z -= 0.0004 * gl_Position.w; }")
        info.fragment_source(
            "void main(){"
            " vec4 dv = DV * vec4(v_P, 1.0); float depth = -dv.z;"
            " vec2 sc = (DP * dv).xy * 0.5 + 0.5;"
            " if (any(lessThan(sc, vec2(0.0))) || any(greaterThanEqual(sc, vec2(1.0)))) discard;"
            " ivec2 px = ivec2(sc * size); float best = 1e30;"
            " for (int dy = -1; dy <= 1; dy++) for (int dx = -1; dx <= 1; dx++) {"
            "  vec4 d = texelFetch(dmap, clamp(px + ivec2(dx, dy), ivec2(0), ivec2(size) - 1), 0);"
            "  if (d.a > 0.5) best = min(best, abs(d.b - depth)); }"
            " if (best > tol) discard;"
            " vec4 c = texture(wtex, sc); if (c.a < 0.003) discard;"
            " FragColor = c; }")
        _SHADERS["VIEW"] = gpu.shader.create_from_info(info)
    return _SHADERS["VIEW"]


class Preview:
    """The decal drawn on the mesh in the viewport (premultiplied, depth-tested)."""

    def __init__(self, P):
        self.P = P
        self.batch = batch_for_shader(_view_shader(), 'TRIS', {"P": P})
        self.ready = False

    def update(self, uv, frame, rect, W, depth):
        h, w = W.shape[:2]
        pr = decal_projector(self.P, uv, frame, rect, (w, h), depth)
        self.dmap = texture(pr.screen_pass())
        self.wtex = texture(W)
        self.DV, self.DP = pr.V, pr.VP @ pr.V.inverted()
        self.size = (float(w), float(h))
        self.tol = float(pr.tol[1])
        self.ready = True

    def draw(self, view_proj):
        if not self.ready:
            return
        sh = _view_shader()
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA_PREMULT')
        sh.bind()
        sh.uniform_float("VP", view_proj)
        sh.uniform_float("DV", self.DV)
        sh.uniform_float("DP", self.DP)
        sh.uniform_float("size", self.size)
        sh.uniform_float("tol", self.tol)
        sh.uniform_sampler("dmap", self.dmap)
        sh.uniform_sampler("wtex", self.wtex)
        self.batch.draw(sh)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
