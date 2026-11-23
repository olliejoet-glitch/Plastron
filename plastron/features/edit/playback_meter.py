"""How fast the video preview really plays (Ollie: "it's still low fps, and
janky"): while playing, the preview header shows the frames actually drawn
per second (red when well under the project's rate), and "Making preview
copies..." while footage's half-size copies are still being built (Plastron
hides Blender's status bar, where that job's progress would show; playing
before they're done decodes the full-size video).

The count is a draw handler on the preview picture (one increment per
drawn frame); the header reads it twice a second.
"""

import time

import bpy

from ...config import edit as cfg
from ...timeline import header
from . import proxies

_meter = {"frames": 0, "since": 0.0, "fps": None}
_handles = []


def _count():
    if bpy.context.screen is not None and bpy.context.screen.is_animation_playing:
        _meter["frames"] += 1


def fps():
    """Frames drawn per second over the last half second or so (None when
    not playing)."""
    screen = bpy.context.screen
    if screen is None or not screen.is_animation_playing:
        _meter.update(frames=0, since=0.0, fps=None)
        return None
    now = time.monotonic()
    if not _meter["since"]:
        _meter.update(frames=0, since=now)
    elif now - _meter["since"] >= 0.5:
        _meter["fps"] = _meter["frames"] / (now - _meter["since"])
        _meter.update(frames=0, since=now)
    return _meter["fps"]


def draw_header(layout, context):
    scene = context.scene
    n = proxies.building(scene)
    if n:
        row = layout.row()
        row.alert = True
        row.label(text=f"Making preview copies ({n})... playback is slow until they're done", icon='SORTTIME')
    rate = fps()
    if rate is not None:
        want = scene.render.fps / scene.render.fps_base
        row = layout.row()
        row.alert = rate < want * cfg.PLAYBACK_WARN
        row.label(text=f"{rate:.0f} / {want:g} fps")


def _tick():
    """Redraw the preview header while playing or building (its numbers change)."""
    wm = bpy.context.window_manager
    busy = bool(proxies._building)
    for window in wm.windows:
        if window.screen.is_animation_playing or busy:
            for area in window.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    for region in area.regions:
                        if region.type == 'HEADER':
                            region.tag_redraw()
    return 0.5


def register():
    header.add_preview_section(draw_header)
    _handles.append(bpy.types.SpaceSequenceEditor.draw_handler_add(_count, (), 'PREVIEW', 'POST_PIXEL'))
    bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    while _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handles.pop(), 'PREVIEW')
