"""Timeline editing tools: Move (Blender's: click / drag clips, drag edges to
retime) and Slice (click a clip to cut it there; Shift+click cuts every
track). S / A switch between them (config/keymap.py).

Slice is a Blender workspace tool, so the timeline shows a knife cursor
while it's on.
"""

import bpy

from ..config import timeline as cfg
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
        area.tag_redraw()
        return {'FINISHED'}


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
        frame = round(fx)
        if snapping.enabled(scene) and not event.ctrl:      # hold Ctrl to not snap
            frame = snapping.snap(frame, snapping.targets(scene),
                                  cfg.SNAP_PX * snapping.frames_per_pixel(region))
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
        ("plastron.clip_slice", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("plastron.clip_slice", {"type": 'LEFTMOUSE', "value": 'PRESS', "shift": True},
         {"properties": [("all_tracks", True)]}),
    )


classes = (PLASTRON_OT_timeline_tool, PLASTRON_OT_clip_slice)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(PLASTRON_WT_timeline_slice)


def unregister():
    bpy.utils.unregister_tool(PLASTRON_WT_timeline_slice)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
