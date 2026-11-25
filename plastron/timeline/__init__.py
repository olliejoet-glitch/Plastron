"""The one shared timeline and track system (every mode uses it).

    tracks.py         track model over Blender's channels
    clips.py          clip timing helpers, overlap-safe repositioning
    ripple.py         trim / delete / insert / split with per-track ripple
    snapping.py       playhead, clip edges, markers (beats)
    mix.py            audio mix (clip × track volume, solo), written on edit
    track_headers.py  ripple / solo / volume widgets in the channel column
    sections.py       video above / audio below: tints, the line, empty channels hidden
    header.py         timeline header bar
    ops.py            operators
    edit_tools.py     Move / Slice tools (S / A)
    edit_keys.py      Q / W trim to playhead, Up / Down jump to cuts, J / K / L
    placement.py      which clips may go on which track (kept after Blender's drags)
    ripple_move.py    ripple for whole-clip drags (gap closes, drop inserts at a cut)
    duplicate.py      Alt+drag a clip: drag a copy
    track_drag.py     drag a track's header to move the track
    fades.py          fade in / out per clip (corner handles; Ctrl+D dip at a cut)
    colors.py         clip colours (header colour button, Clip panel swatches)
    link.py           link / unlink clips by hand (Ctrl+Alt+L, header chain button)
    track_edit.py     remove a track; the Script lane hidden in Edit mode
    mute.py           mute / unmute clips (H, header speaker button)
    rate.py           the project's frame rate (header fps menu): everything keeps its time
    events.py         events features listen to
"""

import bpy

from ..config import project_defaults
from ..core import handlers
from . import clips, colors, duplicate, gaps, link, mute, rate, track_edit, edit_keys, edit_tools, events, fades, header, mix, ops, placement, sections, snapping, track_drag, track_headers, tracks

_MODULES = (tracks, mix, header, sections, track_headers, ops, edit_tools, edit_keys, placement, fades, colors, link, mute, rate, track_edit, duplicate, track_drag, gaps)
_pending = set()   # scene names waiting for a debounced clips_changed


def _update_frame_range(scene, **_info):
    if not scene.plastron_timeline.range_auto:      # (set by hand)
        return
    ends = [clips.end(s) for s in clips.top_clips(scene)]
    if ends and scene.frame_end != max(ends) - 1:
        scene.frame_end = max(ends) - 1


def _on_load(scene):
    if scene is None:
        return
    created = not scene.plastron_timeline.tracks
    tracks.ensure_default_tracks(scene)
    if created:
        scene.tool_settings.use_snap_sequencer = project_defaults.SNAPPING
        snapping.configure_native(scene)
        events.emit("project_created", scene)
    events.clips_changed(scene)


_held = {"since": None}
HOLD_MAX = 30.0          # s: never hold a refresh back longer than this


def dragging():
    """Is a drag running (Blender's or one of Plastron's boxes)?"""
    wm = bpy.context.window_manager
    return any(len(w.modal_operators) for w in (wm.windows if wm else []))


def _flush():
    # A drag (a title / picture moved in the preview, an edge...) changes the
    # scene on every mouse move: the timeline is refreshed once, when it ends
    # (Ollie: dragging titles and pictures was slow on a big project).
    import time
    if dragging():
        now = time.monotonic()
        _held["since"] = _held["since"] or now
        if now - _held["since"] < HOLD_MAX:
            return 0.1
    _held["since"] = None
    for scene in bpy.data.scenes:
        if scene.name in _pending:
            events.clips_changed(scene)
    _pending.clear()
    return None


def _on_depsgraph(scene, depsgraph):
    # O(1): only notes that the scene (and so maybe its clips) changed.
    # Never fires during playback; debounced so a drag doesn't flood it.
    if depsgraph.id_type_updated('SCENE') and scene.name not in _pending:
        _pending.add(scene.name)
        if not bpy.app.timers.is_registered(_flush):
            bpy.app.timers.register(_flush, first_interval=0.1)


def register():
    for module in _MODULES:
        module.register()
    events.listen("clips_changed", _update_frame_range)
    handlers.on_load(_on_load)
    handlers.add("depsgraph_update_post", _on_depsgraph)


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
    events.clear()
