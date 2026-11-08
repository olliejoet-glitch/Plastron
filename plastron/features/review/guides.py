"""Framing guides on the canvas (the brief's "toggleable canvas overlays for
rule of thirds, YouTube safe areas, and a 9:16 frame"). Toggled in the
options bar's Guides menu, remembered between sessions. Drawn inside the
camera frame as the canvas shows it (flat or through the 3D camera).
"""

import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ...config import review as cfg
from ...core import user_settings
from ...core.theme import _color

SETTING = "guides"


def shown():
    return set(user_settings.get(SETTING, []) or [])


def _prop_name(gid):
    return f"plastron_guide_{gid.lower()}"


def _frame_points(context):
    """The frame on screen as (bottom-left, bottom-right, top-right, top-left)."""
    from ..storyboard import canvas_frame
    corners = canvas_frame.shown_frame(context)
    if not corners:
        return None
    pts = [location_3d_to_region_2d(context.region, context.region_data, c) for c in corners]
    if any(p is None for p in pts):
        return None
    tr, br, bl, tl = pts                     # Blender's view_frame order
    return bl, br, tr, tl


def at(frame, u, v):
    """Point at (u, v) of the frame (0..1 across, 0..1 up)."""
    bl, br, tr, tl = frame
    return bl * (1 - u) * (1 - v) + br * u * (1 - v) + tr * u * v + tl * (1 - u) * v


def lines(frame, which):
    """[(colour, [points])] polylines for the guides that are on."""
    out = []
    if "THIRDS" in which:
        for t in (1 / 3, 2 / 3):
            out.append((cfg.GUIDE_COLOR, [at(frame, t, 0), at(frame, t, 1)]))
            out.append((cfg.GUIDE_COLOR, [at(frame, 0, t), at(frame, 1, t)]))
    if "SAFE" in which:
        for _name, k in cfg.SAFE_AREAS:
            m = (1 - k) / 2
            box = [at(frame, m, m), at(frame, 1 - m, m), at(frame, 1 - m, 1 - m), at(frame, m, 1 - m)]
            out.append((cfg.GUIDE_COLOR, box + box[:1]))
    if "SHORT" in which:
        bl, br, _tr, tl = frame
        aspect = (br - bl).length / max((tl - bl).length, 1e-6)
        half = (9 / 16) / aspect / 2                       # 9:16 at full height, centred
        box = [at(frame, 0.5 - half, 0), at(frame, 0.5 + half, 0),
               at(frame, 0.5 + half, 1), at(frame, 0.5 - half, 1)]
        out.append((cfg.SHORT_COLOR, box + box[:1]))
    return out


def draw(context):
    which = shown()
    if not which:
        return
    frame = _frame_points(context)
    if frame is None:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    for colour, pts in lines(frame, which):
        shader.uniform_float("color", _color(colour))
        batch_for_shader(shader, 'LINE_STRIP', {"pos": [(p.x, p.y) for p in pts]}).draw(shader)


def _guide_prop(gid, label):
    def get(_self):
        return gid in shown()

    def set(_self, value):
        now = shown()
        (now.add if value else now.discard)(gid)
        user_settings.set(SETTING, sorted(now))
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    return bpy.props.BoolProperty(name=label, get=get, set=set)


class PLASTRON_PT_guides(bpy.types.Panel):
    """Framing guides on the canvas"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Guides"
    bl_ui_units_x = 9

    def draw(self, context):
        for gid, label in cfg.GUIDES:
            self.layout.prop(context.window_manager, _prop_name(gid), text=label)


classes = (PLASTRON_PT_guides,)


def register():
    for gid, label in cfg.GUIDES:
        setattr(bpy.types.WindowManager, _prop_name(gid), _guide_prop(gid, label))
    for cls in classes:
        bpy.utils.register_class(cls)
    from ..storyboard import canvas_frame
    canvas_frame.EXTRA_DRAW.append(draw)


def unregister():
    from ..storyboard import canvas_frame
    if draw in canvas_frame.EXTRA_DRAW:
        canvas_frame.EXTRA_DRAW.remove(draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for gid, _label in cfg.GUIDES:
        delattr(bpy.types.WindowManager, _prop_name(gid))
