"""Voice clips and their takes.

A voice clip is a sound clip whose strip.plastron_voice lists its takes;
the clip plays the active take. Every take is a sound packed into the project
(so recordings can't go missing), with its transcript: a word list with
times (seconds from the start of the take).

Recording onto a clip adds a take and switches to it; switching takes
changes the clip's length, following the track's ripple setting.
"""

import json
import uuid

import bpy

from ...timeline import clips, events, ripple, tracks

STATUS = [('NONE', "Not transcribed", ""), ('WAITING', "Waiting", ""),
          ('RUNNING', "Transcribing", ""), ('DONE', "Done", ""), ('FAILED', "Failed", "")]


def _take_changed(self, context):
    pass


class PLASTRON_PG_take(bpy.types.PropertyGroup):
    uid: bpy.props.StringProperty()
    sound: bpy.props.PointerProperty(type=bpy.types.Sound)
    duration: bpy.props.FloatProperty()              # seconds
    words_json: bpy.props.StringProperty()           # [[word, start s, end s], ...]
    status: bpy.props.EnumProperty(items=STATUS, default='NONE')
    error: bpy.props.StringProperty()


class PLASTRON_PG_voice(bpy.types.PropertyGroup):
    takes: bpy.props.CollectionProperty(type=PLASTRON_PG_take)
    active: bpy.props.IntProperty(default=0)


def is_voice(strip):
    return strip is not None and strip.type == 'SOUND' and len(strip.plastron_voice.takes) > 0


def active_take(strip):
    v = strip.plastron_voice
    return v.takes[v.active] if 0 <= v.active < len(v.takes) else None


def words(take):
    try:
        return [tuple(w) for w in json.loads(take.words_json)] if take.words_json else []
    except ValueError:
        return []


def set_words(take, word_list):
    take.words_json = json.dumps([[w, round(s, 3), round(e, 3)] for w, s, e in word_list])


def fps(scene):
    return scene.render.fps / scene.render.fps_base


def frames(scene, seconds):
    return max(1, round(seconds * fps(scene)))


def _add_take(strip, sound, duration):
    take = strip.plastron_voice.takes.add()
    take.uid = uuid.uuid4().hex[:10]
    take.sound = sound
    take.duration = duration
    return take


def target_track(scene):
    """Where recording goes: the active track if it's audio, else the top
    audio track."""
    track = tracks.active(scene)
    if track is not None and track.kind == 'AUDIO':
        return track
    audio = [t for t in tracks.all_tracks(scene) if t.kind == 'AUDIO']
    return audio[-1] if audio else None


def clip_for_retake(scene, track, frame):
    """The voice clip a recording at frame would be a new take of, or None."""
    clip = clips.at(scene, tracks.channel_of(scene, track), frame)
    return clip if is_voice(clip) else None


def new_clip(scene, track, frame, wav_path, duration):
    """A new voice clip from a recording at frame (makes room like New Panel).
    Returns the strip, or an error message."""
    channel = tracks.channel_of(scene, track)
    room = ripple.make_room(scene, channel, frame, frames(scene, duration))
    if room is None:
        return "No room on this track at the playhead"
    start, length = room
    name = f"{tracks.name(scene, track)} {_next_number(scene)}"
    strip = clips.editor(scene).strips.new_sound(name, wav_path, channel, start)
    if clips.end(strip) > start + length:
        strip.right_handle = start + length
    strip.sound.pack()
    _add_take(strip, strip.sound, duration)
    strip.plastron_voice.active = 0
    events.clips_changed(scene)
    return strip


def add_take(scene, strip, wav_path, duration):
    """A new take of strip from a recording; the clip switches to it."""
    sound = bpy.data.sounds.load(wav_path, check_existing=False)
    sound.pack()
    _add_take(strip, sound, duration)
    use_take(scene, strip, len(strip.plastron_voice.takes) - 1)
    return strip


def use_take(scene, strip, index):
    """Make strip play take index: it starts at the clip's start and the clip
    takes the take's length (following the track's ripple setting)."""
    v = strip.plastron_voice
    if not 0 <= index < len(v.takes):
        return False
    take = v.takes[index]
    orig = ripple.snapshot(scene)
    start = clips.start(strip)
    clips.apply(scene, {strip: (start, start + 1)})
    if strip.sound != take.sound:
        strip.sound = take.sound
    if strip.content_start != start:             # play the take from its beginning
        strip.content_start = start
        strip.left_handle = start
        strip.right_handle = start + 1
    v.active = index
    clips.apply(scene, ripple.plan_trim(scene, orig, strip, 'RIGHT',
                                        start + frames(scene, take.duration)))
    events.clips_changed(scene)
    return True


def _next_number(scene):
    numbers = [0]
    for s in clips.top_clips(scene):
        tail = s.name.rsplit(" ", 1)[-1]
        if is_voice(s) and tail.isdigit():
            numbers.append(int(tail))
    return max(numbers) + 1


def all_takes(scene):
    """[(strip, take)] for every voice clip's every take."""
    out = []
    for strip in clips.top_clips(scene):
        if is_voice(strip):
            out += [(strip, t) for t in strip.plastron_voice.takes]
    return out


def find_take(uid):
    for scene in bpy.data.scenes:
        if not hasattr(scene, "plastron_timeline") or scene.sequence_editor is None:
            continue
        for strip, take in all_takes(scene):
            if take.uid == uid:
                return scene, strip, take
    return None, None, None


classes = (PLASTRON_PG_take, PLASTRON_PG_voice)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Strip.plastron_voice = bpy.props.PointerProperty(type=PLASTRON_PG_voice)


def unregister():
    del bpy.types.Strip.plastron_voice
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
