"""Ripple delete a gap (Ollie: "like in DaVinci Resolve").

Click an empty stretch of a track (between two clips, or before the first)
to select that gap (tinted); Delete / Backspace closes it: what comes after
moves up. With GAP_ALL_TRACKS (config/timeline.py) every unlocked track
moves by the same amount, as far as all of them have room, so picture and
sound stay in step; if another track has no room at all, only the clicked
track closes up, its moved clips' linked clips going along (as far as they
have room). Clicking a clip, or any edit that fills the gap, lets it go.
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..config import timeline as cfg
from ..core.theme import _color
from . import clips, events, tracks

_gap = {"scene": None, "channel": None, "start": 0, "end": 0}
_handles = []


def find(scene, channel, frame):
    """(start, end) of the empty stretch on channel around frame, or None
    (frame on a clip, or after the track's last clip)."""
    prev_end, next_start = None, None
    for s in clips.on_channel(scene, channel):
        a, b = clips.start(s), clips.end(s)
        if a <= frame < b:
            return None
        if b <= frame:
            prev_end = b if prev_end is None else max(prev_end, b)
        elif next_start is None or a < next_start:
            next_start = a
    if next_start is None:
        return None
    start = prev_end if prev_end is not None else min(scene.frame_start, next_start)
    return (start, next_start) if next_start > start else None


def selected(scene):
    if scene is None or _gap["scene"] != scene.name or _gap["channel"] is None:
        return None
    return _gap["channel"], _gap["start"], _gap["end"]


def clear():
    _gap.update(scene=None, channel=None)


def _locked(scene, channel):
    return clips.editor(scene).channels[channel].lock


def plan(scene, channel, start, end, all_tracks=None):
    """{strip: (new_start, new_end)} closing the gap, and the frames closed.

    Pure apart from reading clips: moving clips = those starting at / after
    the gap's end (on every unlocked track, or the gap's track + the linked
    clips of those); each affected track must have room for the shift."""
    all_tracks = cfg.GAP_ALL_TRACKS if all_tracks is None else all_tracks
    every = clips.top_clips(scene)

    def shift_for(moving):
        width = end - start
        by_channel = {}
        for s in moving:
            by_channel.setdefault(s.channel, []).append(s)
        for ch, group in by_channel.items():
            first = min(clips.start(s) for s in group)
            stay = [clips.end(s) for s in every if s.channel == ch and s not in moving and clips.start(s) < first]
            room = first - max(stay) if stay else width
            width = min(width, room)
        return max(0, width)

    if all_tracks:
        channels = {tracks.channel_of(scene, t) for t in tracks.all_tracks(scene)}
        moving = [s for s in every if s.channel in channels and not _locked(scene, s.channel)
                  and clips.start(s) >= end]
        d = shift_for(moving)
        if d > 0:
            return {s: (clips.start(s) - d, clips.end(s) - d) for s in moving}, d
    own = [s for s in every if s.channel == channel and clips.start(s) >= end]
    moving = [s for s in clips.with_linked(own, every) if not _locked(scene, s.channel)]
    d = shift_for(moving)
    if d <= 0:
        return {}, 0
    return {s: (clips.start(s) - d, clips.end(s) - d) for s in moving}, d


def close(scene):
    """Close the selected gap. Returns the frames closed (0: nothing)."""
    gap = selected(scene)
    if gap is None:
        return 0
    channel, start, end = gap
    changes, d = plan(scene, channel, start, end)
    clear()
    if not changes:
        return 0
    clips.apply(scene, changes)
    events.clips_changed(scene)
    return d


def _delete(context):
    """Delete / Backspace with a gap selected (ops.delete_handlers)."""
    if selected(context.scene) is None:
        return False
    if not close(context.scene):
        return False
    for area in context.screen.areas:
        area.tag_redraw()
    return True


def _check(scene, **_info):
    """A gap that has been filled (or its clips moved) is let go."""
    gap = selected(scene)
    if gap is None:
        return
    channel, start, end = gap
    if find(scene, channel, start) != (start, end):
        clear()


class PLASTRON_OT_gap_select(bpy.types.Operator):
    """Click an empty stretch of a track: select the gap (Delete closes it)"""
    bl_idname = "plastron.gap_select"
    bl_label = "Select Gap"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        from ..core.views import is_timeline
        region = context.region
        if region is None or region.type != 'WINDOW' or not is_timeline(context.space_data):
            return {'PASS_THROUGH'}
        scene = context.scene
        had = selected(scene) is not None
        clear()
        frame, chan = region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        channel = int(chan)
        track = tracks.track_of_channel(scene, channel)
        if track is not None and not getattr(track, "hidden", False):
            gap = find(scene, channel, frame)
            if gap is not None:
                _gap.update(scene=scene.name, channel=channel, start=gap[0], end=gap[1])
        if had or selected(scene) is not None:
            region.tag_redraw()
        return {'PASS_THROUGH'}             # (Blender's own click still deselects the clips)


def draw():
    context = bpy.context
    gap = selected(context.scene)
    if gap is None:
        return
    from ..core.views import is_timeline
    if not is_timeline(context.space_data):
        return
    channel, start, end = gap
    v2d = context.region.view2d
    x0, y0 = v2d.view_to_region(start, channel, clip=False)
    x1, y1 = v2d.view_to_region(end, channel + 1, clip=False)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.uniform_float("color", (*_color(cfg.GAP_COLOR)[:3], cfg.GAP_ALPHA))
    batch_for_shader(shader, 'TRIS', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]}).draw(shader)
    shader.uniform_float("color", (*_color(cfg.GAP_COLOR)[:3], 0.9))
    batch_for_shader(shader, 'LINE_LOOP', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(shader)
    gpu.state.blend_set('NONE')


def register():
    bpy.utils.register_class(PLASTRON_OT_gap_select)
    from . import ops
    ops.delete_handlers.insert(0, _delete)
    events.listen("clips_changed", _check)
    _handles.append(bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
    from . import ops
    if _delete in ops.delete_handlers:
        ops.delete_handlers.remove(_delete)
    bpy.utils.unregister_class(PLASTRON_OT_gap_select)
