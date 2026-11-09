"""Putting footage, sound and pictures on the timeline.

place() makes the clips on a spare channel first (Blender bumps a clip
that lands on another), makes room on the track like New Panel does
(ripple tracks move along; others: the clip fits the gap), then moves them
onto their tracks. A video's sound goes on the "Video Sound" track.

Blender's own drop (a file dragged from the media bin or from Windows onto
the timeline) makes its clips wherever the mouse was: right after Blender's
add-a-clip operator, its new clips are placed again properly at the same
frame, on the track under the drop.
"""

import os

import bpy

from ...config import edit as cfg
from ...timeline import clips, events, ripple, tracks

MARK = "plastron_media"
ADOPTED = "plastron_media_adopted"
DROP_OPS = {"SEQUENCER_OT_movie_strip_add", "SEQUENCER_OT_sound_strip_add", "SEQUENCER_OT_image_strip_add"}
_seen = [None]      # the last add operator already dealt with


def kind_of(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in bpy.path.extensions_movie:
        return 'MOVIE'
    if ext in bpy.path.extensions_audio:
        return 'SOUND'
    if ext in bpy.path.extensions_image:
        return 'IMAGE'
    return None


def is_media(strip):
    return bool(strip.get(MARK))


def owned(strip):
    """Made by Plastron (a panel, voice clip, temp sound or placed media)."""
    if is_media(strip) or strip.get("plastron_temp_sound"):
        return True
    panel = getattr(strip, "plastron_panel", None)
    if panel is not None and panel.uid:
        return True
    voice = getattr(strip, "plastron_voice", None)
    return voice is not None and len(voice.takes) > 0


def sound_track(scene):
    for track in tracks.all_tracks(scene):
        if track.kind == 'AUDIO' and tracks.name(scene, track) == cfg.VIDEO_SOUND_TRACK:
            return track
    return tracks.add(scene, 'AUDIO', track_name=cfg.VIDEO_SOUND_TRACK)


FOOTAGE_TYPES = {'MOVIE', 'IMAGE'}       # (+ 'SCENE': info windows)


def is_footage(strip):
    from ..storyboard.panels import is_panel
    return strip.type in FOOTAGE_TYPES and not is_panel(strip)


def _holds(scene, track, test, besides=None):
    return any(test(s) and s != besides for s in clips.on_channel(scene, tracks.channel_of(scene, track)))


def footage_rule(scene, strip, track):
    """placement rule: footage and panels never share a track."""
    from ..storyboard.panels import is_panel
    if is_panel(strip):
        return not _holds(scene, track, is_footage, strip)
    if is_footage(strip):
        return not _holds(scene, track, is_panel, strip)
    return True


def footage_track(scene):
    """A video track for footage: the Video track (made if missing)."""
    from ..storyboard.panels import is_panel
    for track in tracks.video_tracks(scene):
        if tracks.name(scene, track) == cfg.VIDEO_TRACK and not _holds(scene, track, is_panel):
            return track
    return tracks.add(scene, 'VIDEO', track_name=cfg.VIDEO_TRACK, ripple=cfg.VIDEO_TRACK_RIPPLE)


def _pick_track(scene, track, kind):
    """The track a clip of this kind goes on: the one given if it fits, else
    the active track if it fits, else the first of that kind (footage: never
    a track with panels on it, else the Video track)."""
    from ..storyboard.panels import is_panel
    want = 'AUDIO' if kind == 'SOUND' else 'VIDEO'

    def fits(t):
        return t is not None and t.kind == want and (want == 'AUDIO' or not _holds(scene, t, is_panel))

    for t in (track, tracks.active(scene)):
        if fits(t):
            return t
    if want == 'VIDEO':
        return footage_track(scene)
    same = [t for t in tracks.all_tracks(scene) if t.kind == want]
    return same[0] if same else None


def _spare(scene):
    return max([s.channel for s in clips.editor(scene).strips_all] + [len(tracks.all_tracks(scene))]) + 1


def _fit(scene, strip, channel, frame):
    """Make room on channel at frame for strip; trim it to fit and move it
    there. False if there's no room (the strip is left where it is)."""
    room = ripple.make_room(scene, channel, frame, clips.length(strip))
    if room is None:
        return False
    start, length = room
    if clips.end(strip) != start + length:
        strip.right_handle = start + length
    strip.channel = channel
    return True


def _proxies(strip):
    if strip.type != 'MOVIE' or cfg.PREVIEW_SIZE == 'SCENE':
        return
    strip.use_proxy = True
    for attr in ("build_25", "build_50", "build_75", "build_100"):
        setattr(strip.proxy, attr, attr in cfg.PROXY_BUILD)


def place(scene, path, frame=None, track=None):
    """Put the file at frame (default: the playhead) on track (default: the
    active / first track of its kind). Returns the new clips, or a message."""
    kind = kind_of(path)
    if kind is None:
        return f"Plastron can't use {os.path.basename(path)} (not a video, sound or picture)"
    frame = scene.frame_current if frame is None else int(frame)
    target = _pick_track(scene, track, kind)
    if target is None:
        return "There's no track for that"
    if tracks.is_locked(scene, target):
        return "That track is locked"
    sed = clips.editor(scene)
    spare = _spare(scene)
    name = os.path.splitext(os.path.basename(path))[0]
    made = []
    if kind == 'MOVIE':
        main = sed.strips.new_movie(name, path, spare, frame, fit_method='FIT')
        try:
            sound = sed.strips.new_sound(name, path, spare + 1, frame)
            if clips.length(sound) < 2:                  # (a video without sound: an empty clip)
                sed.strips.remove(sound)
            else:
                made.append(sound)
        except (RuntimeError, TypeError):
            pass                                     # (no sound in it)
    elif kind == 'SOUND':
        main = sed.strips.new_sound(name, path, spare, frame)
    else:
        main = sed.strips.new_image(name, path, spare, frame, fit_method='FIT')
        fps = scene.render.fps / scene.render.fps_base
        main.right_handle = frame + max(1, round(cfg.STILL_SECONDS * fps))
    made.insert(0, main)
    for strip in made:
        strip[MARK] = True
    if not _fit(scene, main, tracks.channel_of(scene, target), frame):
        for strip in made:
            sed.strips.remove(strip)
        return "No room here: turn on ripple for this track, or make a gap"
    for sound in made[1:]:
        if clips.length(sound) > clips.length(main):
            sound.right_handle = clips.end(main)
        if not _fit(scene, sound, tracks.channel_of(scene, sound_track(scene)), clips.start(main)):
            sed.strips.remove(sound)
            made.remove(sound)
    _proxies(main)
    if len(made) > 1:
        clips.link(made)          # the video and its sound move / trim / cut together
    for s in clips.all_clips(scene):
        s.select = s in made
    sed.active_strip = main
    events.clips_changed(scene)
    events.emit("media_placed", scene, strips=made)
    return made


# --- Blender's own drops ------------------------------------------------------------------

def adopt(scene, *_args):
    """At load: clips already in the project count as placed."""
    sed = scene.sequence_editor if scene else None
    if sed is not None:
        for strip in sed.strips_all:
            if not owned(strip):
                strip[MARK] = True
    if scene is not None:
        scene[ADOPTED] = True


def _on_split(scene, original=None, new=None, **_info):
    if original is not None and new is not None and is_media(original):
        new[MARK] = True


def take_drops(scene, **_info):
    """Clips Blender's own drop just made: placed again properly."""
    sed = scene.sequence_editor if scene else None
    if sed is None or not scene.get(ADOPTED):         # (not before adopt() at load)
        return
    # Only right after Blender's own add-a-clip operator (what a drop runs),
    # once each: clips other code makes are left alone.
    wm = bpy.context.window_manager
    last = wm.operators[-1] if wm and len(wm.operators) else None
    if last is None or last.bl_idname not in DROP_OPS or last.as_pointer() == _seen[0]:
        return
    _seen[0] = last.as_pointer()
    dropped = [s for s in sed.strips if s.type in {'MOVIE', 'SOUND', 'IMAGE'} and s.select and not owned(s)]
    if not dropped:
        return
    groups = {}
    for strip in dropped:
        path = bpy.path.abspath(strip.filepath if strip.type == 'MOVIE' else
                                strip.sound.filepath if strip.type == 'SOUND' else
                                os.path.join(strip.directory, strip.elements[0].filename))
        groups.setdefault(os.path.normpath(path), []).append(strip)
    for path, group in groups.items():
        main = next((s for s in group if s.type != 'SOUND'), group[0])
        # Blender drops a video's sound on the channel under the mouse and the
        # picture just above it: the lowest channel is where it was dropped.
        frame, channel = clips.start(main), min(s.channel for s in group)
        for strip in group:
            sed.strips.remove(strip)
        result = place(scene, path, frame, tracks.track_of_channel(scene, channel))
        if isinstance(result, str):
            print("Plastron:", result)


def register():
    from ...timeline import placement
    placement.RULES.append(footage_rule)
    events.listen("clips_changed", take_drops)
    events.listen("clip_split", _on_split)
    from ...core import handlers
    handlers.on_load(adopt)


def unregister():
    from ...timeline import placement
    if footage_rule in placement.RULES:
        placement.RULES.remove(footage_rule)
