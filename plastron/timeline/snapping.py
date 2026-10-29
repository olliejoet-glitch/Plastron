"""Snapping while dragging: to the playhead, other clip edges and markers.

Markers are where beat detection will put beats, so snapping to beats
will work as soon as that exists.
"""

from ..config import timeline as cfg
from . import clips


def enabled(scene):
    return scene.tool_settings.use_snap_sequencer


def targets(scene, exclude=()):
    frames = set()
    if cfg.SNAP_TO_PLAYHEAD:
        frames.add(scene.frame_current)
    if cfg.SNAP_TO_CLIP_EDGES:
        for strip in clips.top_clips(scene):
            if strip not in exclude:
                frames.update((clips.start(strip), clips.end(strip)))
    if cfg.SNAP_TO_MARKERS:
        frames.update(m.frame for m in scene.timeline_markers)
    return sorted(frames)


def frames_per_pixel(region):
    v2d = region.view2d
    return abs(v2d.region_to_view(1, 0)[0] - v2d.region_to_view(0, 0)[0])


def snap(frame, candidates, threshold):
    """Nearest candidate within threshold frames, else frame unchanged."""
    best, best_dist = frame, threshold
    for c in candidates:
        d = abs(c - frame)
        if d <= best_dist:
            best, best_dist = c, d
    return best


def configure_native(scene):
    """Blender's own snapping (used when moving clips) matches Plastron's."""
    ts = scene.tool_settings
    sts = ts.sequencer_tool_settings
    sts.snap_to_current_frame = cfg.SNAP_TO_PLAYHEAD
    sts.snap_to_borders = cfg.SNAP_TO_CLIP_EDGES
    sts.snap_to_markers = cfg.SNAP_TO_MARKERS
    sts.snap_distance = cfg.SNAP_PX
