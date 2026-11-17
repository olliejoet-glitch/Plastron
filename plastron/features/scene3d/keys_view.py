"""Each clip its own animation timeline (Ollie: "I need each clip to have
its own timeline, with the start and end of it being the start and end of
the clip"). The keyframe view (Dope Sheet under the 3D scene) is framed on
the clip being drawn on, start to end; outside it is dimmed, and the
clip's name and length show at the top. When the playhead moves to another
clip (scrubbing, playing) or the clip's length changes, it re-frames.
It lists only that clip's own channels (each clip owns its keys, shots.py;
Blender names them "... (<clip name>)", so the view's search filters by it).

Cost: the view's draw only compares the clip's (name, start, end) with the
last framed; re-framing (Blender's zoom_border) runs from a timer.
"""

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import scene3d as cfg
from ...core.theme import _color
from ...timeline import clips

_framed = {}       # area pointer -> (clip name, start, end) it was framed on
_handle = []


def current_clip(scene):
    from ..storyboard import canvas_sync
    name = canvas_sync._state.get("canvas_clip")
    sed = scene.sequence_editor if scene else None
    return sed.strips_all.get(name) if (sed and name) else None


def channel_filter(clip):
    return f"({clip.name})"


def _key_areas():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'DOPESHEET_EDITOR':
                yield window, area


def frame_on(window, area, start, end):
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None or region.width < 10:
        return
    margin = (end - start) * cfg.KEYS_VIEW_MARGIN
    v2d = region.view2d
    x0 = v2d.view_to_region(start - margin, 0, clip=False)[0]
    x1 = v2d.view_to_region(end + margin, 0, clip=False)[0]
    if x1 - x0 < 2:
        return
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.view2d.zoom_border(xmin=int(x0), xmax=int(x1), ymin=0, ymax=region.height,
                                   wait_for_input=False, zoom_out=False)
    area.tag_redraw()


def _refit():
    scene = bpy.context.scene
    clip = current_clip(scene)
    if clip is None:
        return None
    sig = (clip.name, clips.start(clip), clips.end(clip))
    for window, area in _key_areas():
        dopesheet = area.spaces.active.dopesheet
        if dopesheet.filter_text != channel_filter(clip):
            dopesheet.filter_text = channel_filter(clip)
        if _framed.get(area.as_pointer()) != sig:
            frame_on(window, area, sig[1], sig[2])
            _framed[area.as_pointer()] = sig
    return None


def draw():
    context = bpy.context
    scene, region, area = context.scene, context.region, context.area
    clip = current_clip(scene)
    if clip is None or region is None:
        return
    start, end = clips.start(clip), clips.end(clip)
    if (_framed.get(area.as_pointer()) != (clip.name, start, end)
            or context.space_data.dopesheet.filter_text != channel_filter(clip)) \
            and not bpy.app.timers.is_registered(_refit):
        bpy.app.timers.register(_refit, first_interval=0.01)
    v2d = region.view2d
    x0 = v2d.view_to_region(start, 0, clip=False)[0]
    x1 = v2d.view_to_region(end, 0, clip=False)[0]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    dim = list(_color(cfg.KEYS_VIEW_DIM[0]))
    dim[3] = cfg.KEYS_VIEW_DIM[1]
    shader.uniform_float("color", dim)
    for a, b in ((0, x0), (x1, region.width)):
        a, b = max(0, a), min(region.width, b)
        if b > a:
            batch_for_shader(shader, 'TRI_FAN', {"pos": [(a, 0), (b, 0), (b, region.height), (a, region.height)]}).draw(shader)
    gpu.state.blend_set('NONE')
    fps = scene.render.fps / scene.render.fps_base
    label = f"{clip.name}  ·  {(end - start) / fps:.1f} s"
    font = 0
    blf.size(font, 11 * context.preferences.system.ui_scale)
    blf.color(font, *_color(cfg.KEYS_VIEW_LABEL))
    blf.position(font, max(4, x0 + 4), region.height - 30 * context.preferences.system.ui_scale, 0)
    blf.draw(font, label)


def register():
    _handle.append(bpy.types.SpaceDopeSheetEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handle:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_handle.pop(), 'WINDOW')
    if bpy.app.timers.is_registered(_refit):
        bpy.app.timers.unregister(_refit)
