"""Which clips may go on which track, kept after Blender's own clip drags.

Sound goes on audio tracks, everything else on video tracks, never on a
channel that isn't a track; features add their own rules (RULES; e.g. Edit
mode: footage and panels don't share a track). Blender's drag-move knows
nothing of this, so after every timeline change a clip that has landed
where it can't go goes back to its last track: at its new time if there's
room there, else back where it was. Linked clips go back together.
"""

import bpy

from . import clips, events, tracks

RULES = []      # func(scene, strip, track) -> False if strip may not go on track
_last = {}      # scene name -> {strip name: (channel, start, end)} after the last check


def allowed(scene, strip, track):
    if track is None:
        return False
    if track.kind != ('AUDIO' if strip.type == 'SOUND' else 'VIDEO'):
        return False
    return all(rule(scene, strip, track) for rule in RULES)


def _dragging():
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        if any(op.bl_idname.startswith("TRANSFORM_OT") for op in window.modal_operators):
            return True
    return False


def _free(scene, strip, channel, start, end):
    return all(o == strip or not (clips.start(o) < end and start < clips.end(o))
               for o in clips.on_channel(scene, channel))


def _spare(scene):
    return max([s.channel for s in clips.editor(scene).strips_all] + [len(tracks.all_tracks(scene))]) + 1


def _put_back(scene, group, last):
    """Each clip of group to its old channel (new time if free there, else old time)."""
    spare = _spare(scene)
    for i, strip in enumerate(group):                   # all out of each other's way first
        strip.channel = spare + i
    keep_time = all(_free(scene, s, last[s.name][0], clips.start(s), clips.end(s)) for s in group)
    for strip in group:
        channel, start, end = last[strip.name]
        if not keep_time:
            clips.apply(scene, {strip: (start, end)})
        strip.channel = channel


def check(scene, **_info):
    if scene is None or scene.sequence_editor is None or not hasattr(scene, "plastron_timeline"):
        return
    if _dragging():                      # (Blender is still moving them: look again later)
        name = scene.name
        if not bpy.app.timers.is_registered(_retry):
            _pending.add(name)
            bpy.app.timers.register(_retry, first_interval=0.2)
        return
    last = _last.get(scene.name, {})
    # Only clips that moved (a panel isn't wrong because footage landed next to it).
    bad = [s for s in clips.top_clips(scene)
           if s.name in last and last[s.name] != (s.channel, clips.start(s), clips.end(s))
           and not allowed(scene, s, tracks.track_of_channel(scene, s.channel))]
    moved = False
    done = set()
    for strip in bad:
        if strip in done:
            continue
        group = [s for s in clips.with_linked([strip], clips.top_clips(scene)) if s.name in last]
        done.update(group)
        _put_back(scene, group, last)
        moved = True
    _last[scene.name] = {s.name: (s.channel, clips.start(s), clips.end(s)) for s in clips.top_clips(scene)
                         if allowed(scene, s, tracks.track_of_channel(scene, s.channel))}
    if moved:
        events.clips_changed(scene)


_pending = set()


def _retry():
    if _dragging():
        return 0.2
    for name in list(_pending):
        scene = bpy.data.scenes.get(name)
        if scene is not None:
            check(scene)
    _pending.clear()
    return None


def _on_load(scene):
    _last.clear()
    if scene is not None:
        check(scene)


def register():
    events.listen("clips_changed", check)
    from ..core import handlers
    handlers.on_load(_on_load)


def unregister():
    if bpy.app.timers.is_registered(_retry):
        bpy.app.timers.unregister(_retry)
