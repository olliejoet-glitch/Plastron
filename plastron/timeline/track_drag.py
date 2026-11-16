"""Drag a track by its header, up or down, to move the whole track (Ollie:
"drag and move around entire tracks themselves"). Its clips, name, mute,
lock and ripple go with it; video tracks stay above audio ones. Starts only
once the pen moves while held ("LMB drag"), so clicks on the header still
reach Blender's name / mute / lock and Plastron's R / S / volume. An orange
line shows where it will go; Esc / right-click cancels. One undo step."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..config import timeline as cfg
from ..core.theme import _color
from . import track_headers, tracks

_drag = {"from": None, "to": None}
_handle = []


def target_index(area, region, scene, index, y):
    """Where a track dragged to pixel y (channel column) would go."""
    tl = tracks.data(scene)
    kind = tl.tracks[index].kind
    same = [i for i, t in enumerate(tl.tracks) if t.kind == kind]
    main = next(r for r in area.regions if r.type == 'WINDOW')
    ch = main.view2d.region_to_view(0, y + region.y - main.y)[1]
    to = int(ch) - 1
    return max(min(same), min(max(same), to))


class PLASTRON_OT_track_drag(bpy.types.Operator):
    """Drag a track's header up or down to move the track"""
    bl_idname = "plastron.track_drag"
    bl_label = "Move Track"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        region = context.region
        if region is None or region.type != 'CHANNELS':
            return {'PASS_THROUGH'}
        scene = context.scene
        y = event.mouse_prev_press_y - region.y
        x = event.mouse_prev_press_x - region.x
        if track_headers.hit(context.area, region, scene, x, y) is not None:
            return {'PASS_THROUGH'}                     # (R / S / volume)
        index = track_headers.row_at(context.area, region, scene, y)
        if index is None:
            return {'PASS_THROUGH'}
        self.area, self.region = context.area, region
        _drag.update({"from": index, "to": index})
        context.window.cursor_modal_set('MOVE_Y')
        context.window_manager.modal_handler_add(self)
        region.tag_redraw()
        return {'RUNNING_MODAL'}

    def _end(self, context):
        context.window.cursor_modal_restore()
        _drag.update({"from": None, "to": None})
        for area in context.screen.areas:
            area.tag_redraw()

    def modal(self, context, event):
        scene = context.scene
        if event.type == 'MOUSEMOVE':
            _drag["to"] = target_index(self.area, self.region, scene, _drag["from"],
                                       event.mouse_y - self.region.y)
            self.region.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            src, to = _drag["from"], _drag["to"]
            self._end(context)
            if to is None or to == src:
                return {'CANCELLED'}
            tracks.move(scene, src, to)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


def draw():
    """While dragging: the track's row outlined, a line where it will land."""
    if _drag["from"] is None:
        return
    context = bpy.context
    area, region = context.area, context.region
    src, to = _drag["from"], _drag["to"]
    y0, y1 = track_headers.row_span(area, region, tracks.channel(src))
    t0, t1 = track_headers.row_span(area, region, tracks.channel(to))
    y = t1 if to > src else t0                     # (lands above / below the row it's over)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    colour = list(_color(cfg.HEADER_COLORS["active_track"]))
    for pts in ([(0, y - 2), (region.width, y - 2), (region.width, y + 2), (0, y + 2)],):
        shader.uniform_float("color", colour)
        batch_for_shader(shader, 'TRI_FAN', {"pos": pts}).draw(shader)
    colour[3] = 0.25
    shader.uniform_float("color", colour)
    batch_for_shader(shader, 'TRI_FAN', {"pos": [(0, y0), (region.width, y0),
                                                 (region.width, y1), (0, y1)]}).draw(shader)
    gpu.state.blend_set('NONE')


def register():
    bpy.utils.register_class(PLASTRON_OT_track_drag)
    _handle.append(bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'CHANNELS', 'POST_PIXEL'))


def unregister():
    while _handle:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handle.pop(), 'CHANNELS')
    bpy.utils.unregister_class(PLASTRON_OT_track_drag)
