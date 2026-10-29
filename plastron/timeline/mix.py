"""Audio mix: each sound clip's volume = clip volume × track volume × solo.

Written into the clips whenever a volume or solo changes (never computed
during playback).
"""

from . import clips, events, tracks


def apply(scene, **_info):
    if scene.sequence_editor is None:
        return
    audio = [t for t in tracks.all_tracks(scene) if t.kind == 'AUDIO']
    any_solo = any(t.solo for t in audio)
    for strip in clips.all_clips(scene):
        if strip.type != 'SOUND':
            continue
        track = tracks.track_of_clip(scene, strip)
        track_volume = track.volume if track else 1.0
        silenced = any_solo and not (track and track.solo)
        volume = 0.0 if silenced else strip.plastron.volume * track_volume
        if abs(strip.volume - volume) > 1e-6:
            strip.volume = volume


def register():
    events.listen("mix_changed", apply)
    events.listen("clips_changed", apply)
    events.listen("tracks_changed", apply)


def unregister():
    pass
