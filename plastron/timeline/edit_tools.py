"""Timeline editing tools: Move (Blender's: click / drag clips, drag edges to
retime) and Slice (click a clip to cut it there; Shift+click cuts every
track). S / A switch between them (config/keymap.py).

Slice is a Blender workspace tool. While it's on, moving over the timeline
shows a knife cursor and a line where the cut would go.
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..config import timeline as cfg
from ..core.theme import _color
from . import clips, ripple, snapping, tracks

SLICE = "plastron.timeline_slice"
_TOOL_IDS = {"MOVE": cfg.MOVE_TOOL, "SLICE": SLICE}


def active_tool(context):
    """'SLICE' or 'MOVE' for the timeline's current tool."""
    tool = context.workspace.tools.from_space_sequencer('SEQUENCER', create=False)
    return "SLICE" if tool is not None and tool.idname == SLICE else "MOVE"


def _timeline_area(context):
    if context.area and context.area.type == 'SEQUENCE_EDITOR':
        return context.area
    return next((a for a in context.window.screen.areas if a.type == 'SEQUENCE_EDITOR'), None)


class PLASTRON_OT_timeline_tool(bpy.types.Operator):
    """Switch the timeline between moving / resizing clips and slicing them"""
    bl_idname = "plastron.timeline_tool"
    bl_label = "Timeline Tool"
    bl_options = {'INTERNAL'}

    tool: bpy.props.EnumProperty(items=[('MOVE', "Move", "Move clips and drag their edges"),
                                        ('SLICE', "Slice", "Click a clip to cut it there")])

    @classmethod
    def description(cls, context, properties):
        return "Move clips and drag their edges" if properties.tool == 'MOVE' else \
            "Slice: click a clip to cut it there (Shift+click: every track)"

    def execute(self, context):
        area = _timeline_area(context)
        if area is None:
            return {'CANCELLED'}
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with context.temp_override(area=area, region=region):
            bpy.ops.wm.tool_set_by_id(name=_TOOL_IDS[self.tool], space_type='SEQUENCE_EDITOR')
        _hover["area"] = None
        area.tag_redraw()
        self.report({'INFO'}, "Slice: click a clip to cut it (A: back to Move)" if self.tool == 'SLICE'
                    else "Move: drag clips and their edges")
        return {'FINISHED'}


def cut_frame(scene, region, x, ctrl):
    """The frame a slice at region x would cut at (snapped if asked)."""
    frame = round(region.view2d.region_to_view(x, 0)[0])
    if snapping.enabled(scene) != ctrl:      # Ctrl flips snapping while held
        frame = snapping.snap(frame, snapping.targets(scene),
                              cfg.SNAP_PX * snapping.frames_per_pixel(region))
    return frame


_hover = {"area": None, "x": 0, "y": 0, "ctrl": False, "shift": False}


class PLASTRON_OT_slice_hover(bpy.types.Operator):
    """Slice tool: knife cursor and the cut line under the mouse"""
    bl_idname = "plastron.slice_hover"
    bl_label = "Slice Preview"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if context.area is None or context.region is None or context.region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        _hover.update(area=context.area.as_pointer(), x=event.mouse_region_x, y=event.mouse_region_y,
                      ctrl=event.ctrl, shift=event.shift)
        context.window.cursor_set('KNIFE')
        context.area.tag_redraw()
        return {'PASS_THROUGH'}


def _draw_cut_line():
    context = bpy.context
    area, region = context.area, context.region
    if area is None or _hover["area"] != area.as_pointer() or active_tool(context) != 'SLICE':
        return
    scene = context.scene
    frame = cut_frame(scene, region, _hover["x"], _hover["ctrl"])
    x = region.view2d.view_to_region(frame, 0, clip=False)[0]
    if _hover["shift"]:
        y0, y1 = 0, region.height
    else:
        channel = int(region.view2d.region_to_view(0, _hover["y"])[1])
        if clips.at(scene, channel, frame) is None:
            return
        y0 = region.view2d.view_to_region(0, channel, clip=False)[1]
        y1 = region.view2d.view_to_region(0, channel + 1, clip=False)[1]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": [(x - 1, y0), (x + 1, y0), (x + 1, y1),
                                                      (x - 1, y0), (x + 1, y1), (x - 1, y1)]})
    shader.uniform_float("color", _color(cfg.SLICE_LINE_COLOR))
    gpu.state.blend_set('ALPHA')
    batch.draw(shader)
    gpu.state.blend_set('NONE')


class PLASTRON_OT_clip_slice(bpy.types.Operator):
    """Cut the clip under the mouse there (Shift: every track)"""
    bl_idname = "plastron.clip_slice"
    bl_label = "Slice Clip"
    bl_options = {'REGISTER', 'UNDO'}

    all_tracks: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'SEQUENCE_EDITOR' and \
            context.region and context.region.type == 'WINDOW'

    def invoke(self, context, event):
        scene, region = context.scene, context.region
        fx, fy = region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        frame = cut_frame(scene, region, event.mouse_region_x, event.ctrl)
        if self.all_tracks:
            targets = [s for s in clips.top_clips(scene) if clips.start(s) < frame < clips.end(s)]
        else:
            clip = clips.at(scene, int(fy), frame)
            targets = [clip] if clip is not None else []
            index = tracks.index_of_channel(scene, int(fy))
            if index is not None:
                tracks.set_active(scene, scene.plastron_timeline.tracks[index])
        if not ripple.split(scene, targets, frame):
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_WT_timeline_slice(bpy.types.WorkSpaceTool):
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_context_mode = 'SEQUENCER'
    bl_idname = SLICE
    bl_label = "Slice"
    bl_description = "Click a clip to cut it there (Shift+click: every track)"
    bl_icon = "ops.sequencer.blade"
    bl_cursor = 'KNIFE'
    bl_keymap = (
        ("plastron.slice_hover", {"type": 'MOUSEMOVE', "value": 'ANY', "any": True}, None),
        ("plastron.clip_slice", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("plastron.clip_slice", {"type": 'LEFTMOUSE', "value": 'PRESS', "shift": True},
         {"properties": [("all_tracks", True)]}),
        # Ctrl: snap (or not, if snapping is switched on)
        ("plastron.clip_slice", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True}, None),
        ("plastron.clip_slice", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True, "shift": True},
         {"properties": [("all_tracks", True)]}),
    )


classes = (PLASTRON_OT_timeline_tool, PLASTRON_OT_clip_slice, PLASTRON_OT_slice_hover)
_draw_handle = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(PLASTRON_WT_timeline_slice)
    _draw_handle.append(bpy.types.SpaceSequenceEditor.draw_handler_add(
        _draw_cut_line, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    for handle in _draw_handle:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(handle, 'WINDOW')
    _draw_handle.clear()
    bpy.utils.unregister_tool(PLASTRON_WT_timeline_slice)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
