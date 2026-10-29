"""Timeline operators: add track, track header clicks, trim clip edges,
split, delete, loop range. Shortcuts: config/keymap.py."""

import bpy

from ..config import timeline as cfg
from . import clips, events, ripple, snapping, track_headers, tracks


def _timeline_window(context):
    return (context.area and context.area.type == 'SEQUENCE_EDITOR'
            and context.region and context.region.type == 'WINDOW')


def _frame_at(region, x):
    return round(region.view2d.region_to_view(x, 0)[0])


class PLASTRON_OT_track_add(bpy.types.Operator):
    """Add a track"""
    bl_idname = "plastron.track_add"
    bl_label = "Add Track"
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(items=tracks.KINDS, name="Kind")

    def execute(self, context):
        tracks.set_active(context.scene, tracks.add(context.scene, self.kind))
        return {'FINISHED'}


class PLASTRON_OT_track_header_click(bpy.types.Operator):
    """Track header: toggle ripple / solo, drag volume, or make a track active"""
    bl_idname = "plastron.track_header_click"
    bl_label = "Track Header"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        region = context.region
        if region is None or region.type != 'CHANNELS':
            return {'PASS_THROUGH'}
        scene = context.scene
        x, y = event.mouse_region_x, event.mouse_region_y
        found = track_headers.hit(context.area, region, scene, x, y)
        if found is None:
            index = track_headers.row_at(context.area, region, scene, y)
            if index is not None:
                tracks.set_active(scene, scene.plastron_timeline.tracks[index])
                context.area.tag_redraw()          # header and row highlight
            return {'PASS_THROUGH'}     # name rename, Blender's mute / lock
        index, wid, rect = found
        self.track = scene.plastron_timeline.tracks[index]
        if wid == "VOLUME":
            self.rect = rect
            self._set_volume(event.mouse_region_x)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        setattr(self.track, wid.lower(), not getattr(self.track, wid.lower()))
        region.tag_redraw()
        return {'FINISHED'}

    def _set_volume(self, x):
        x0, _y0, x1, _y1 = self.rect
        self.track.volume = max(0.0, min(2.0, (x - x0) / (x1 - x0) * 2.0))

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self._set_volume(event.mouse_region_x)
            context.region.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class PLASTRON_OT_clip_trim(bpy.types.Operator):
    """Drag a clip's edge to retime it (follows the track's ripple setting)"""
    bl_idname = "plastron.clip_trim"
    bl_label = "Trim Clip"
    bl_options = {'REGISTER', 'UNDO'}

    extend: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        from .edit_tools import active_tool
        return _timeline_window(context) and active_tool(context) == 'MOVE'

    def _select(self, event):
        """Not on an edge: Blender's own click (select; a drag then moves).
        Blender's version of this click is off: it grabbed edges itself."""
        pos = dict(mouse_x=event.mouse_region_x, mouse_y=event.mouse_region_y)
        if self.extend:
            bpy.ops.sequencer.select('EXEC_DEFAULT', toggle=True, **pos)
        else:
            bpy.ops.sequencer.select('EXEC_DEFAULT', deselect_all=True, **pos)
        return {'PASS_THROUGH'}       # a drag from here moves the clip (Blender)

    def invoke(self, context, event):
        scene, region = context.scene, context.region
        fx, fy = region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        index = tracks.index_of_channel(scene, int(fy))
        if index is not None:
            tracks.set_active(scene, scene.plastron_timeline.tracks[index])
        fpp = snapping.frames_per_pixel(region)
        outside, inside = cfg.EDGE_GRAB_PX * fpp, cfg.EDGE_GRAB_INSIDE_PX * fpp
        best = None
        for strip in clips.on_channel(scene, int(fy)):
            reach = min(inside, clips.length(strip) / 3)        # short clips can still be moved
            for side, edge in (('LEFT', clips.start(strip)), ('RIGHT', clips.end(strip))):
                into = fx - edge if side == 'LEFT' else edge - fx   # > 0: inside the clip
                d = abs(fx - edge)
                near = -into <= outside if into < 0 else into <= reach
                if near and (best is None or d < best[0]):
                    best = (d, strip, side)
        if best is None:
            return self._select(event)
        _d, self.strip, self.side = best
        if scene.sequence_editor.channels[self.strip.channel].lock:
            self.report({'WARNING'}, "That track is locked")
            return {'CANCELLED'}
        for s in clips.all_clips(scene):
            s.select = False
        self.strip.select = True
        scene.sequence_editor.active_strip = self.strip
        self.orig = ripple.snapshot(scene)
        self.targets = snapping.targets(scene, exclude={self.strip})
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _update(self, context, event):
        scene, region = context.scene, context.region
        frame = _frame_at(region, event.mouse_region_x)
        if snapping.enabled(scene) != event.ctrl:      # Ctrl flips snapping while held
            frame = snapping.snap(frame, self.targets,
                                  cfg.SNAP_PX * snapping.frames_per_pixel(region))
        plan = ripple.plan_trim(scene, self.orig, self.strip, self.side, frame)
        clips.apply(scene, {s: plan.get(s, se) for s, se in self.orig.items()})

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._update(context, event)
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            events.clips_changed(context.scene)
            return {'FINISHED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            clips.apply(context.scene, self.orig)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


delete_handlers = []    # features: func(context) -> True if it handled Delete


def _selected(scene):
    return [s for s in clips.top_clips(scene) if s.select]


class PLASTRON_OT_clip_split(bpy.types.Operator):
    """Cut the selected clips (or the active track's clip) at the playhead"""
    bl_idname = "plastron.clip_split"
    bl_label = "Split at Playhead"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        targets = [s for s in _selected(scene) if clips.start(s) < frame < clips.end(s)]
        if not targets:
            track = tracks.active(scene)
            clip = track and clips.at(scene, tracks.channel_of(scene, track), frame)
            targets = [clip] if clip else []
        if not ripple.split(scene, targets, frame):
            self.report({'INFO'}, "Nothing to split at the playhead")
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_clip_delete(bpy.types.Operator):
    """Delete the selected clips (ripple tracks close the gap), or selected transcript words"""
    bl_idname = "plastron.clip_delete"
    bl_label = "Delete Clips"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for handler in delete_handlers:      # e.g. selected transcript words
            if handler(context):
                return {'FINISHED'}
        if not ripple.delete(context.scene, _selected(context.scene)):
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_loop_set(bpy.types.Operator):
    """Set where the loop range starts or ends (at the playhead)"""
    bl_idname = "plastron.loop_set"
    bl_label = "Set Loop Range"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(items=[('IN', "Start", ""), ('OUT', "End", "")])

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        if not scene.use_preview_range:
            scene.use_preview_range = True
            scene.frame_preview_start, scene.frame_preview_end = scene.frame_start, scene.frame_end
        if self.side == 'IN':
            scene.frame_preview_start = frame
            scene.frame_preview_end = max(scene.frame_preview_end, frame + 1)
        else:
            scene.frame_preview_end = frame
            scene.frame_preview_start = min(scene.frame_preview_start, frame - 1)
        return {'FINISHED'}


classes = (
    PLASTRON_OT_track_add,
    PLASTRON_OT_track_header_click,
    PLASTRON_OT_clip_trim,
    PLASTRON_OT_clip_split,
    PLASTRON_OT_clip_delete,
    PLASTRON_OT_loop_set,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
