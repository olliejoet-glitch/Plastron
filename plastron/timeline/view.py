"""Framing the timeline: the whole project across, the tracks up the side
with rows tall enough to show panel pictures."""

import bpy

from ..config import timeline as cfg
from . import tracks


def row_height(region):
    v2d = region.view2d
    return v2d.view_to_region(0, 2, clip=False)[1] - v2d.view_to_region(0, 1, clip=False)[1]


def frame(window, area, region, scene):
    """Frame the project in a timeline area (region: its main region)."""
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.anim.scene_range_frame()      # whole project across
        target = cfg.ROW_HEIGHT_PX * bpy.context.preferences.system.ui_scale
        rows = len(tracks.all_tracks(scene)) + 1
        # Taller rows, but never so tall the tracks don't fit.
        target = min(target, region.height / rows)
        for _ in range(30):
            h = row_height(region)
            if h >= target * 0.97:
                break
            bpy.ops.view2d.zoom(deltax=0.0, deltay=min(1.0, (target - h) / max(h, 1.0)))
        # Bottom track at the bottom of the view.
        for _ in range(60):
            bottom = region.view2d.region_to_view(0, 0)[1]
            if 0.6 <= bottom <= 1.0:
                break
            step = max(1, int(abs(bottom - 0.8) * row_height(region)))
            if bottom > 1.0:
                bpy.ops.view2d.scroll_down(deltay=step)
            else:
                bpy.ops.view2d.scroll_up(deltay=step)
