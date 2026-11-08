"""Auto-ducking: audio tracks with Duck on dip under the voice (the voice
tracks in config/audio.py) wherever someone is talking. Worked out from the
voice clips' loudness on edits (envelopes cached per file) and written as
keyframes with the clips' fades and mix volume (timeline/fades.py)."""

import math

import bpy

from ...config import audio as cfg
from ...timeline import clips, events, fades, tracks
from . import analysis


def talking(scene):
    """[(start, end)] seconds where any voice track's clips are louder than the threshold."""
    regions = []
    for track in tracks.all_tracks(scene):
        if track.kind != 'AUDIO' or tracks.name(scene, track) not in cfg.VOICE_TRACKS or getattr(track, "duck", False):
            continue
        if clips.editor(scene).channels[tracks.channel_of(scene, track)].mute:
            continue
        for strip in clips.on_channel(scene, tracks.channel_of(scene, track)):
            if strip.type != 'SOUND' or strip.mute:
                continue
            env, t0 = analysis.clip_envelope(scene, strip, cfg.DUCK_HOP)
            gain_db = 20 * math.log10(max(strip.plastron.volume, 1e-6))
            loud = (env + gain_db) > cfg.DUCK_THRESHOLD_DB
            i = 0
            while i < len(loud):
                if loud[i]:
                    j = i
                    while j < len(loud) and loud[j]:
                        j += 1
                    regions.append((t0 + i * cfg.DUCK_HOP, t0 + j * cfg.DUCK_HOP))
                    i = j
                else:
                    i += 1
    regions.sort()
    merged = []
    for a, b in regions:
        if merged and a - merged[-1][1] < cfg.DUCK_GAP:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def duck_points(regions, fps):
    """Gain curve [(frame, gain)] dipping in each region (with attack / release)."""
    g = 10 ** (cfg.DUCK_DB / 20.0)
    out = []
    for a, b in regions:
        out += [((a - cfg.DUCK_ATTACK) * fps, 1.0), (a * fps, g), (b * fps, g), ((b + cfg.DUCK_RELEASE) * fps, 1.0)]
    # overlapping ramps: keep it monotonic in time
    out.sort()
    clean = []
    for f, v in out:
        if clean and f <= clean[-1][0]:
            clean[-1] = (clean[-1][0], min(clean[-1][1], v))
        else:
            clean.append((f, v))
    return clean


_busy = [False]


def update(scene, **_info):
    """Re-work the ducking of every clip on a ducking track (only writes what changed)."""
    if _busy[0] or scene is None or scene.sequence_editor is None:
        return
    ducking = [t for t in tracks.all_tracks(scene) if t.kind == 'AUDIO' and getattr(t, "duck", False)]
    changed = False
    _busy[0] = True
    try:
        regions = talking(scene) if ducking else []
        fps = scene.render.fps / scene.render.fps_base
        points = duck_points(regions, fps)
        duck_channels = {tracks.channel_of(scene, t) for t in ducking}
        for strip in clips.top_clips(scene):
            if strip.type != 'SOUND':
                continue
            if strip.channel in duck_channels:
                s, e = clips.start(strip), clips.end(strip)
                mine = [(f, v) for f, v in points if s - 1 <= f <= e + 1]
                # (the curve's values just outside the clip matter at its edges)
                changed = fades.set_gain(strip, mine or [(s, 1.0)]) or changed
            elif fades.gain_points(strip):
                changed = fades.set_gain(strip, []) or changed
        if changed:
            events.emit("mix_changed", scene)
    finally:
        _busy[0] = False


def _duck_changed(self, context):
    update(context.scene)


def register():
    tracks.PLASTRON_PG_track.duck = bpy.props.BoolProperty(
        name="Duck", description="Dip this track under the voice when someone is talking",
        update=_duck_changed)
    events.listen("clips_changed", update)
    events.listen("mix_changed", update)


def unregister():
    pass
