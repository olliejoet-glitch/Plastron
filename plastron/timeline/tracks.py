"""Tracks: Plastron's layer over Blender's sequencer channels.

scene.plastron_timeline.tracks is ordered bottom to top; track i lives on
channel i + 1. Audio tracks sit below video tracks. A track's name, mute and
lock ARE its Blender channel's (one source of truth; Blender's own channel
header buttons edit them). Plastron adds kind, ripple, solo and volume.
"""

import uuid

import bpy

from ..config import project_defaults as defaults
from . import clips, events

KINDS = [('VIDEO', "Video", ""), ('AUDIO', "Audio", "")]


def _mix_changed(self, context):
    events.mix_changed(context.scene)


class PLASTRON_PG_track(bpy.types.PropertyGroup):
    uid: bpy.props.StringProperty()
    kind: bpy.props.EnumProperty(items=KINDS, default='VIDEO')
    ripple: bpy.props.BoolProperty(
        name="Ripple", description="Edits on this track shift everything after them")
    solo: bpy.props.BoolProperty(
        name="Solo", description="Hear only soloed audio tracks", update=_mix_changed)
    volume: bpy.props.FloatProperty(
        name="Track Volume", default=1.0, min=0.0, max=2.0, subtype='FACTOR',
        update=_mix_changed)


class PLASTRON_PG_timeline(bpy.types.PropertyGroup):
    tracks: bpy.props.CollectionProperty(type=PLASTRON_PG_track)
    active_track: bpy.props.IntProperty(name="Active Track", default=-1)


class PLASTRON_PG_clip(bpy.types.PropertyGroup):
    """Plastron data on every timeline clip (strip.plastron)."""
    volume: bpy.props.FloatProperty(
        name="Clip Volume", default=1.0, min=0.0, max=2.0, subtype='FACTOR',
        update=_mix_changed)


# --- Queries ------------------------------------------------------------------

def data(scene):
    return scene.plastron_timeline


def all_tracks(scene):
    return list(scene.plastron_timeline.tracks)


def channel(index):
    return index + 1


def index_of_channel(scene, ch):
    i = ch - 1
    return i if 0 <= i < len(scene.plastron_timeline.tracks) else None


def track_of_channel(scene, ch):
    i = index_of_channel(scene, ch)
    return scene.plastron_timeline.tracks[i] if i is not None else None


def track_of_clip(scene, strip):
    return track_of_channel(scene, strip.channel)


def channel_of(scene, track):
    for i, t in enumerate(scene.plastron_timeline.tracks):
        if t.uid == track.uid:
            return channel(i)
    return None


def native(scene, track):
    """The Blender channel holding this track (name / mute / lock)."""
    return clips.editor(scene).channels[channel_of(scene, track)]


def name(scene, track):
    return native(scene, track).name


def is_locked(scene, track):
    return native(scene, track).lock


def video_tracks(scene):
    return [t for t in all_tracks(scene) if t.kind == 'VIDEO']


def active(scene):
    """The active track (where new panels go); defaults to the top video track."""
    tl = scene.plastron_timeline
    if 0 <= tl.active_track < len(tl.tracks):
        return tl.tracks[tl.active_track]
    videos = video_tracks(scene)
    return videos[-1] if videos else None


def set_active(scene, track):
    for i, t in enumerate(scene.plastron_timeline.tracks):
        if t.uid == track.uid:
            scene.plastron_timeline.active_track = i
            events.active_track_changed(scene)
            return


def ripple_channels(scene):
    """Channels whose clips shift in a ripple edit: ripple on, not locked."""
    return {channel(i) for i, t in enumerate(all_tracks(scene))
            if t.ripple and not clips.editor(scene).channels[channel(i)].lock}


# --- Changes ------------------------------------------------------------------

def _shift_channels_up(scene, from_channel):
    """Move every channel >= from_channel (clips and settings) up by one."""
    sed = clips.editor(scene)
    top = max([s.channel for s in clips.top_clips(scene)] + [len(data(scene).tracks)])
    settings = {ch: (sed.channels[ch].name, sed.channels[ch].lock, sed.channels[ch].mute)
                for ch in range(from_channel, top + 1)}
    for ch in settings:
        sed.channels[ch].lock = False
    for ch in range(top, from_channel - 1, -1):     # top down: target is always empty
        for strip in clips.on_channel(scene, ch):
            strip.channel = ch + 1
    # Channel names must be unique, so park them on temporary names first.
    for ch in range(from_channel, top + 2):
        sed.channels[ch].name = f"__plastron_tmp_{ch}"
    for ch, (nm, lock, mute) in settings.items():
        target = sed.channels[ch + 1]
        target.name, target.lock, target.mute = nm, lock, mute


def add(scene, kind, track_name=None, ripple=False):
    """Add a track: video on top of all tracks, audio on top of the audio tracks."""
    tl = data(scene)
    if kind == 'AUDIO':
        index = sum(1 for t in tl.tracks if t.kind == 'AUDIO')
    else:
        index = len(tl.tracks)
    if index < len(tl.tracks):
        _shift_channels_up(scene, channel(index))
    track = tl.tracks.add()
    track.uid = uuid.uuid4().hex[:8]
    track.kind = kind
    track.ripple = ripple
    tl.tracks.move(len(tl.tracks) - 1, index)
    if tl.active_track >= index:
        tl.active_track += 1
    track = tl.tracks[index]
    count = sum(1 for t in tl.tracks if t.kind == kind)
    sed = clips.editor(scene)
    sed.channels[channel(index)].name = track_name or f"{'Video' if kind == 'VIDEO' else 'Audio'} {count}"
    sed.channels[channel(index)].lock = False
    sed.channels[channel(index)].mute = False
    events.tracks_changed(scene)
    return track


def ensure_default_tracks(scene):
    """Give a project its starting tracks (config: project_defaults.DEFAULT_TRACKS)."""
    if data(scene).tracks:
        return
    for track_name, kind, ripple in reversed(defaults.DEFAULT_TRACKS):
        add(scene, kind, track_name, ripple)
    videos = video_tracks(scene)
    if videos:
        set_active(scene, videos[-1])


classes = (PLASTRON_PG_track, PLASTRON_PG_timeline, PLASTRON_PG_clip)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.plastron_timeline = bpy.props.PointerProperty(type=PLASTRON_PG_timeline)
    bpy.types.Strip.plastron = bpy.props.PointerProperty(type=PLASTRON_PG_clip)


def unregister():
    del bpy.types.Strip.plastron
    del bpy.types.Scene.plastron_timeline
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
