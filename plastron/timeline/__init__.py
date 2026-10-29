"""The one shared timeline and track system (every mode uses it).

    tracks.py         track model over Blender's channels
    clips.py          clip timing helpers, overlap-safe repositioning
    ripple.py         trim / delete / insert / split with per-track ripple
    snapping.py       playhead, clip edges, markers (beats)
    mix.py            audio mix (clip × track volume, solo), written on edit
    track_headers.py  ripple / solo / volume widgets in the channel column
    header.py         timeline header bar
    ops.py            operators
    edit_tools.py     Move / Slice tools (S / A)
    events.py         events features listen to
"""

import bpy

from ..config import project_defaults
from ..core import handlers
from . import clips, edit_tools, events, header, mix, ops, snapping, track_headers, tracks

_MODULES = (tracks, mix, header, track_headers, ops, edit_tools)
_pending = set()   # scene names waiting for a debounced clips_changed


def _update_frame_range(scene, **_info):
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


def _flush():
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
