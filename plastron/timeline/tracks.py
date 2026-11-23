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

KINDS = [('VIDEO', "Video", ""), ('AUDIO', "Audio", ""), ('SCRIPT', "Script", "")]


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
    hidden: bpy.props.BoolProperty(
        name="Hidden", description="Parked above the other tracks, out of view (the Script lane in Edit mode)")
    collapse: bpy.props.BoolProperty(
        name="Collapse Transcript", description="Show this track's transcript as one line",
        update=lambda self, context: events.emit("tracks_changed", context.scene))


def _range_get(side):
    return lambda self: getattr(self.id_data, "frame_" + side)


def _range_set(side):
    def setter(self, value):
        """Set by hand: the range stops following the clips."""
        scene = self.id_data
        self.range_auto = False
        if side == "start":
            scene.frame_start = value
            scene.frame_end = max(scene.frame_end, value)
        else:
            scene.frame_end = max(value, scene.frame_start)
    return setter


def _range_auto_changed(self, context):
    if self.range_auto:
        events.clips_changed(self.id_data)


class PLASTRON_PG_timeline(bpy.types.PropertyGroup):
    tracks: bpy.props.CollectionProperty(type=PLASTRON_PG_track)
    active_track: bpy.props.IntProperty(name="Active Track", default=-1)
    script_hidden_edit: bpy.props.BoolProperty(
        name="Hide Script in Edit Mode",
        description="Hide the Script lane while editing (it stays in Storyboard mode)",
        update=lambda self, context: __import__(__package__ + ".track_edit", fromlist=["x"])._flag_changed(self, context))
    # The project's range (what plays and exports): follows the clips' end
    # unless set by hand (Ollie: "I need to be able to set the frame range myself").
    range_auto: bpy.props.BoolProperty(
        name="Auto Range", default=True, update=_range_auto_changed,
        description="The project's range ends where the last clip ends (off: the range you set)")
    range_start: bpy.props.IntProperty(
        name="Start", description="Where the project starts (plays and exports from here)",
        min=0, get=_range_get("start"), set=_range_set("start"))
    range_end: bpy.props.IntProperty(
        name="End", description="Where the project ends (plays and exports to here)",
        min=0, get=_range_get("end"), set=_range_set("end"))


def _fades_changed(self, context):
    events.emit("mix_changed", context.scene)
    events.clips_changed(context.scene)


class PLASTRON_PG_clip(bpy.types.PropertyGroup):
    """Plastron data on every timeline clip (strip.plastron)."""
    volume: bpy.props.FloatProperty(
        name="Clip Volume", default=1.0, min=0.0, max=8.0, soft_max=2.0, subtype='FACTOR',
        update=_mix_changed)
    opacity: bpy.props.FloatProperty(
        name="Opacity", description="How see-through the clip's picture is (fades go up to this)",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR', update=_fades_changed)
    fade_in: bpy.props.IntProperty(name="Fade In", description="Frames it fades in over",
                                   default=0, min=0, update=_fades_changed)
    fade_out: bpy.props.IntProperty(name="Fade Out", description="Frames it fades out over",
                                    default=0, min=0, update=_fades_changed)


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
            if scene.plastron_timeline.active_track != i:
                scene.plastron_timeline.active_track = i
                for window in bpy.context.window_manager.windows:   # its highlight moves
                    for area in window.screen.areas:
                        if area.type == 'SEQUENCE_EDITOR':
                            area.tag_redraw()
            events.active_track_changed(scene)
            return


def ripple_channels(scene):
    """Channels whose clips shift in a ripple edit: ripple on, not locked."""
    return {channel(i) for i, t in enumerate(all_tracks(scene))
            if t.ripple and not clips.editor(scene).channels[channel(i)].lock}


# --- Changes ------------------------------------------------------------------

def visible_tracks(scene):
    """[(index, track)] of the tracks shown (hidden ones are parked on top)."""
    return [(i, t) for i, t in enumerate(all_tracks(scene)) if not t.hidden]


def hidden_count(scene):
    return sum(1 for t in all_tracks(scene) if t.hidden)


def move(scene, index, to, any_kind=False):
    """Move the track at index to position to (its clips, name, mute, lock
    and Plastron settings go with it). Video tracks stay above audio ones:
    to is kept inside the track's own section (any_kind: anywhere). Returns
    the new index."""
    tl = data(scene)
    kind = tl.tracks[index].kind
    if not any_kind:
        same = [i for i, t in enumerate(tl.tracks) if t.kind == kind and not t.hidden]
        to = max(min(same), min(max(same), to))
    if to == index:
        return index
    lo, hi = min(index, to), max(index, to)
    order = list(range(len(tl.tracks)))
    order.insert(to, order.pop(index))            # new position p holds old track order[p]
    sed = clips.editor(scene)
    span = range(lo, hi + 1)
    settings = {i: (sed.channels[channel(i)].name, sed.channels[channel(i)].lock,
                    sed.channels[channel(i)].mute) for i in span}
    held = {i: clips.on_channel(scene, channel(i)) for i in span}
    spare = max([st.channel for st in sed.strips_all] + [len(tl.tracks)]) + 1
    for i in span:
        sed.channels[channel(i)].lock = False
    for k, i in enumerate(span):                  # out of the way first...
        for strip in held[i]:
            strip.channel = spare + k
    for i in span:
        sed.channels[channel(i)].name = f"__plastron_tmp_{i}"
    for p in span:                                # ...then each into its new place
        old = order[p]
        for strip in held[old]:
            strip.channel = channel(p)
        nm, lock, mute = settings[old]
        target = sed.channels[channel(p)]
        target.name, target.mute = nm, mute
    for p in span:
        sed.channels[channel(p)].lock = settings[order[p]][1]
    active_uid = tl.tracks[tl.active_track].uid if 0 <= tl.active_track < len(tl.tracks) else None
    tl.tracks.move(index, to)
    if active_uid is not None:
        tl.active_track = next(i for i, t in enumerate(tl.tracks) if t.uid == active_uid)
    events.emit("tracks_moved", scene, moved={order[p]: p for p in span})   # old index -> new
    events.tracks_changed(scene)
    events.clips_changed(scene)
    return to


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


def script_track(scene):
    """The Script lane (between the audio and video tracks), or None."""
    return next((t for t in all_tracks(scene) if t.kind == 'SCRIPT'), None)


def add(scene, kind, track_name=None, ripple=False):
    """Add a track: video on top of all tracks, audio on top of the audio
    tracks, the Script lane between the audio and the video tracks."""
    tl = data(scene)
    if kind == 'AUDIO':
        index = sum(1 for t in tl.tracks if t.kind == 'AUDIO')
    elif kind == 'SCRIPT':
        index = sum(1 for t in tl.tracks if t.kind in {'AUDIO', 'SCRIPT'})
    else:
        index = len(tl.tracks) - hidden_count(scene)      # (below tracks parked out of view)
    if index < len(tl.tracks):
        _shift_channels_up(scene, channel(index))
        # (tracks above move up a place: their keys etc. follow)
        events.emit("tracks_moved", scene, moved={i: i + 1 for i in range(index, len(tl.tracks))})
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
    sed.channels[channel(index)].name = track_name or f"{dict((k, n) for k, n, _d in KINDS)[kind]} {count}"
    sed.channels[channel(index)].lock = False
    sed.channels[channel(index)].mute = False
    events.tracks_changed(scene)
    return track


def _shift_channels_down(scene, from_channel):
    """Move every channel > from_channel (clips and settings) down by one
    (from_channel itself must be empty)."""
    sed = clips.editor(scene)
    top = max([s.channel for s in clips.top_clips(scene)] + [len(data(scene).tracks)])
    settings = {ch: (sed.channels[ch].name, sed.channels[ch].lock, sed.channels[ch].mute)
                for ch in range(from_channel + 1, top + 1)}
    for ch in settings:
        sed.channels[ch].lock = False
    for ch in range(from_channel + 1, top + 1):     # bottom up: target is always empty
        for strip in clips.on_channel(scene, ch):
            strip.channel = ch - 1
    for ch in range(from_channel, top + 1):
        sed.channels[ch].name = f"__plastron_tmp_{ch}"
    for ch, (nm, lock, mute) in settings.items():
        target = sed.channels[ch - 1]
        target.name, target.lock, target.mute = nm, lock, mute
    sed.channels[top].name = f"Channel {top}"


def remove(scene, index):
    """Remove a track and its clips; the tracks above move down a place."""
    from . import ripple
    tl = data(scene)
    ch = channel(index)
    clips.editor(scene).channels[ch].lock = False
    for strip in clips.on_channel(scene, ch):
        ripple.remove(scene, strip)
    _shift_channels_down(scene, ch)
    active_uid = tl.tracks[tl.active_track].uid if 0 <= tl.active_track < len(tl.tracks) else None
    tl.tracks.remove(index)
    tl.active_track = next((i for i, t in enumerate(tl.tracks) if t.uid == active_uid),
                           min(index, len(tl.tracks) - 1))
    events.emit("tracks_moved", scene, moved={i: i - 1 for i in range(index + 1, len(tl.tracks) + 1)})
    events.tracks_changed(scene)
    events.clips_changed(scene)


def natural_index(scene, track):
    """Where a track belongs when shown: the Script lane between the audio and
    the video tracks."""
    tl = data(scene)
    if track.kind == 'SCRIPT':
        return sum(1 for t in tl.tracks if t.kind == 'AUDIO')
    return list(tl.tracks).index(track)


def set_hidden(scene, track, hide):
    """Park a track on top, out of view (hide) or put it back in its place."""
    tl = data(scene)
    if track.hidden == hide:
        return
    index = list(tl.tracks).index(track)
    uid = track.uid
    if hide:
        move(scene, index, len(tl.tracks) - 1, any_kind=True)
    else:
        target = sum(1 for t in tl.tracks if t.kind == 'AUDIO') if track.kind == 'SCRIPT' else index
        move(scene, index, target, any_kind=True)
    track = next(t for t in tl.tracks if t.uid == uid)
    track.hidden = hide
    events.tracks_changed(scene)


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
