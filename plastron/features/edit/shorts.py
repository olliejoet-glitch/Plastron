"""Shorts reframing: a 9:16 version of the edit. Shorts (preview header)
shows a tall box over the picture (outside dimmed) for the shot at the
playhead; drag it left / right to choose what that shot shows in the Short
(kept per clip: strip["plastron_short_x"], -1 left ... 1 right). The
YouTube Shorts export (presets/export/youtube_shorts.json) renders the edit
at 1080×1920 with every picture clip scaled and slid to each shot's choice
for the render only (keyed at the cuts), then put back."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import edit as cfg
from ...config import theme as theme_cfg
from ...core.theme import _color
from ...core.views import is_preview
from ...timeline import clips, events, tracks

KEY = "plastron_short_x"


def box_width(scene):
    r = scene.render
    a, b = cfg.SHORTS_ASPECT
    return r.resolution_y * a / b


def travel(scene):
    """How far (project pixels) the box can slide from the middle."""
    return max(0.0, (scene.render.resolution_x - box_width(scene)) / 2)


def shot_at(scene, frame):
    """The picture clip seen at frame: the top video track's (adjustment /
    values clips aside)."""
    best = None
    for strip in clips.top_clips(scene):
        if strip.type in {'SOUND', 'ADJUSTMENT'} or strip.mute:
            continue
        track = tracks.track_of_clip(scene, strip)
        if track is None or track.kind != 'VIDEO':
            continue
        if clips.start(strip) <= frame < clips.end(strip) and (best is None or strip.channel > best.channel):
            best = strip
    return best


def short_x(strip):
    return float(strip.get(KEY, 0.0)) if strip is not None else 0.0


def offset_at(scene, frame):
    """The box's middle (project pixels from the frame's middle) at frame."""
    return short_x(shot_at(scene, frame)) * travel(scene)


def on(context=None):
    return bool(getattr((context or bpy.context).window_manager, "plastron_shorts", False))


# --- In the preview ------------------------------------------------------------------------

def draw():
    context = bpy.context
    if not on(context) or not is_preview(context.space_data) or context.region is None \
            or context.region.type != 'PREVIEW':
        return
    scene = context.scene
    region = context.region
    v2d = region.view2d
    r = scene.render
    cx = offset_at(scene, scene.frame_current)
    hw, hh = box_width(scene) / 2, r.resolution_y / 2
    fx0, fy0 = v2d.view_to_region(-r.resolution_x / 2, -hh, clip=False)
    fx1, fy1 = v2d.view_to_region(r.resolution_x / 2, hh, clip=False)
    bx0, _ = v2d.view_to_region(cx - hw, 0, clip=False)
    bx1, _ = v2d.view_to_region(cx + hw, 0, clip=False)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.uniform_float("color", cfg.SHORTS_DIM)
    for x0, x1 in ((fx0, bx0), (bx1, fx1)):
        if x1 > x0:
            batch_for_shader(shader, 'TRIS', {"pos": [(x0, fy0), (x1, fy0), (x1, fy1), (x0, fy1)]},
                             indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)
    line = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    line.uniform_float("viewportSize", (region.width, region.height))
    line.uniform_float("lineWidth", 2.0)
    line.uniform_float("color", _color(theme_cfg.CANVAS["frame_edit"]))
    batch_for_shader(line, 'LINE_STRIP', {"pos": [(bx0, fy0), (bx1, fy0), (bx1, fy1), (bx0, fy1), (bx0, fy0)]}).draw(line)
    gpu.state.blend_set('NONE')


class PLASTRON_OT_shorts_drag(bpy.types.Operator):
    """Drag the Shorts box left / right: what this shot shows in the Short"""
    bl_idname = "plastron.shorts_drag"
    bl_label = "Reframe for Shorts"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return on(context) and is_preview(context.space_data)

    def invoke(self, context, event):
        scene = context.scene
        strip = shot_at(scene, scene.frame_current)
        if strip is None or travel(scene) <= 0:
            return {'PASS_THROUGH'}
        self.strip_name = strip.name
        self.x0 = context.region.view2d.region_to_view(event.mouse_region_x, 0)[0]
        self.orig = short_x(strip)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        scene = context.scene
        strip = scene.sequence_editor.strips_all.get(self.strip_name)
        if strip is None:
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            x = context.region.view2d.region_to_view(event.mouse_region_x, 0)[0]
            strip[KEY] = max(-1.0, min(1.0, self.orig + (x - self.x0) / travel(scene)))
            context.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            strip[KEY] = self.orig
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


def draw_preview_button(layout, context):
    layout.prop(context.window_manager, "plastron_shorts", text="Shorts", toggle=True, icon='GRIP_V')


def _on_split(scene, original=None, new=None, **_info):
    if original is not None and new is not None and KEY in original:
        new[KEY] = original[KEY]


# --- The Shorts render -------------------------------------------------------------------------

def render(context, path, size, frames=None, **kw):
    """Render the Short: the edit itself at size (9:16), every picture clip
    scaled to fill the height and slid to the Shorts box of the shot it's
    seen in (keyed at the cuts, held between), then all put back."""
    from ..export import animatic
    from ...timeline import fades
    main = context.scene
    W, H = main.render.resolution_x, main.render.resolution_y
    k = size[1] / H
    cuts = sorted({main.frame_start} | {e for s in clips.top_clips(main) for e in (clips.start(s), clips.end(s))})
    shown = [s for s in clips.top_clips(main) if s.type not in {'SOUND', 'ADJUSTMENT'} and hasattr(s, "transform")]
    saved = {s.name: (s.transform.offset_x, s.transform.offset_y, s.transform.scale_x, s.transform.scale_y)
             for s in shown}
    paths = set()
    try:
        for s in shown:
            ox, oy, sx, sy = saved[s.name]
            t = s.transform
            t.scale_x, t.scale_y, t.offset_y = sx * k, sy * k, oy * k
            for f in sorted({clips.start(s)} | {c for c in cuts if clips.start(s) < c < clips.end(s)}):
                t.offset_x = ox * k - offset_at(main, f) * k
                t.keyframe_insert("offset_x", frame=f, group="Plastron Shorts")
            paths.add(t.path_from_id("offset_x"))
        action = main.animation_data.action if main.animation_data else None
        for bag in fades._bags(action) if action else []:
            for fc in bag.fcurves:
                if fc.data_path in paths:
                    for kp in fc.keyframe_points:
                        kp.interpolation = 'CONSTANT'
        return animatic.export(context, path, size=size, frames=frames, panel_size=(W, H), **kw)
    finally:
        for p_ in paths:
            fades._remove(main, p_)
        for s in shown:
            if s.name in saved:
                t = s.transform
                t.offset_x, t.offset_y, t.scale_x, t.scale_y = saved[s.name]


def _redraw(_self, context):
    for area in context.screen.areas:
        area.tag_redraw()


classes = (PLASTRON_OT_shorts_drag,)
_handle = [None]


def register():
    bpy.types.WindowManager.plastron_shorts = bpy.props.BoolProperty(
        name="Shorts", description="Show the 9:16 Shorts box: drag it to choose what each shot shows",
        update=_redraw)
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle[0] = bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'PREVIEW', 'POST_PIXEL')
    from ...timeline import header
    header.add_preview_section(draw_preview_button)
    events.listen("clip_split", _on_split)


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handle[0], 'PREVIEW')
        _handle[0] = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.plastron_shorts
