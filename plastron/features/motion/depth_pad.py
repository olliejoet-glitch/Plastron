"""Depth chart: a small side view of the panel's layers, next to the camera
box (Ollie wanted 3D parallax without a messy 3D view).

One row per layer (top layer first). Drag a row's dot: left = nearer the
camera, right = further away; the line is the picture plane (depth 1,
where the 2D camera works as before). A hollow dot = the layer follows its
group. Click a name to pick that layer; double-click a row to make it
follow its group again. Depth only shows when the camera moves.
Sizes: DEPTH_PAD in config/motion.py.
"""

import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import motion as cfg, theme as theme_cfg
from ...core.theme import _color
from ...layers.stack import depth as nesting
from . import camera, camera_pad, parallax

D = cfg.DEPTH_PAD


def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def _stack(scene):
    strip = camera.shot(scene)
    mat = strip.plastron_panel.material if strip else None
    return mat.plastron_stack if mat is not None and mat.plastron_stack.enabled else None


def rows(region, stack):
    """[(layer uid, name rect, track rect)] top layer first, plus the box rect."""
    box = camera_pad.layout(region)["BOX"]
    gap, row_h = _ui(camera_pad.P["gap"]), _ui(D["row"])
    x0 = box[2] + gap * 2
    name_w, track_w = _ui(D["name"]), _ui(D["track"])
    layers = list(reversed(stack.layers))[:D["max_rows"]]
    out = []
    y = box[1] + gap
    for layer in reversed(layers):           # bottom row = bottom layer
        out.append((layer.uid, (x0 + gap, y, x0 + gap + name_w, y + row_h),
                    (x0 + gap + name_w, y + 2, x0 + gap + name_w + track_w, y + row_h - 2)))
        y += row_h + 1
    out.reverse()
    frame = (x0, box[1], x0 + gap * 2 + name_w + track_w, y + gap + _ui(14))
    return out, frame


def depth_x(track, d):
    lo, hi = (math.log(v) for v in D["range"])
    f = (math.log(max(d, 1e-3)) - lo) / (hi - lo)
    return track[0] + max(0.0, min(1.0, f)) * (track[2] - track[0])


def x_depth(track, x):
    lo, hi = (math.log(v) for v in D["range"])
    f = max(0.0, min(1.0, (x - track[0]) / max(1.0, track[2] - track[0])))
    return math.exp(lo + f * (hi - lo))


def hit(region, scene, x, y):
    """('NAME' | 'TRACK', uid) under the mouse, ('BOX', None), or None."""
    stack = _stack(scene)
    if stack is None or not stack.layers:
        return None
    out, frame = rows(region, stack)
    for uid, name, track in out:
        if track[0] - 6 <= x <= track[2] + 6 and name[1] <= y <= name[3]:
            return 'TRACK', uid
        if name[0] <= x <= name[2] and name[1] <= y <= name[3]:
            return 'NAME', uid
    if frame[0] <= x <= frame[2] and frame[1] <= y <= frame[3]:
        return 'BOX', None
    return None


def draw(context):
    stack = _stack(context.scene)
    if stack is None or not stack.layers:
        return
    out, frame = rows(context.region, stack)
    c = theme_cfg.CANVAS
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    camera_pad._rect(shader, frame, _color(c["camera_pad_back"]))
    orange, blue = _color(c["frame_edit"]), _color("blue")
    text, dim = _color("text"), _color("text_dim")
    active = stack.active.uid if stack.active else ""
    blf.size(0, _ui(9))
    for uid, name, track in out:
        layer = stack.by_uid(uid)
        if layer is None:
            continue
        if uid == active:                    # the layer being painted: dark row, orange edge
            camera_pad._rect(shader, (name[0], name[1], track[2], name[3]), _color("bg_light"))
            camera_pad._rect(shader, (name[0], name[1], name[0] + _ui(2), name[3]), orange)
        camera_pad._rect(shader, track, _color(c["camera_pad_well"]))
        plane = depth_x(track, 1.0)
        camera_pad._rect(shader, (plane - 0.5, track[1], plane + 0.5, track[3]), (*dim[:3], 0.7))
        d = parallax.effective_depth(layer, stack)
        x = depth_x(track, d)
        cy = (track[1] + track[3]) / 2
        if layer.depth > 0:
            camera_pad._dot(shader, x, cy, _ui(4), orange if uid == active else blue)
        else:
            camera_pad._dot(shader, x, cy, _ui(4), (*dim[:3], 0.9))
            camera_pad._dot(shader, x, cy, _ui(2.5), _color(c["camera_pad_well"]))
        label = ("  " * nesting(stack, layer)) + layer.name
        while label and blf.dimensions(0, label)[0] > name[2] - name[0] - 4:
            label = label[:-1]
        blf.position(0, name[0], (name[1] + name[3]) / 2 - _ui(3), 0)
        blf.color(0, *(text if uid == active else dim))
        blf.draw(0, label)
    track0 = out[0][2]
    blf.size(0, _ui(9))
    blf.color(0, *dim)
    head_y = frame[3] - _ui(12)
    blf.position(0, frame[0] + _ui(6), head_y, 0)
    blf.draw(0, "Depth")
    blf.position(0, track0[0], head_y, 0)
    blf.draw(0, "near")
    w, _h = blf.dimensions(0, "far")
    blf.position(0, track0[2] - w, head_y, 0)
    blf.draw(0, "far")
    gpu.state.blend_set('NONE')


def set_depth(stack, uid, track, x):
    """Depth from the mouse's position on a row's track (snaps to the plane)."""
    layer = stack.by_uid(uid)
    if layer is None:
        return
    d = x_depth(track, x)
    if abs(math.log(d)) < D["snap"]:
        d = 1.0
    d = round(d, 3)
    if abs(layer.depth - d) > 1e-6:
        layer.depth = d


def track_of(region, stack, uid):
    return next((t for u, _n, t in rows(region, stack)[0] if u == uid), None)
