"""Creature voices: a voice clip baked into a stack of pitched copies of
itself (same length: the pitch changes, not the timing), from presets in
config/audio.py CREATURES. The baked clip goes on the "Creature" track,
linked to the voice (they move / trim / cut together) and packed into the
project; the plain voice is muted (unmute it to hear it again)."""

import os
import uuid
import wave

import aud
import bpy
import numpy as np

from ...config import audio as cfg
from ...timeline import clips, events, ripple, tracks
from . import analysis

RATE = 48000


def stack(path, preset):
    """The voice (mono samples at RATE) with its pitched layers mixed in."""
    base = aud.Sound(path).rechannel(1).resample(RATE, False)
    dry = base.data()[:, 0].astype(np.float32)
    out = dry * 10 ** (preset["dry_db"] / 20.0)
    for semitones, db in preset["layers"]:
        layer = base.timeStretchPitchScale(1.0, 2 ** (semitones / 12.0)).data()[:, 0]
        n = min(len(out), len(layer))
        out[:n] += layer[:n] * 10 ** (db / 20.0)
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0.98:
        out *= 0.98 / peak
    return out


def _write_wav(path, x):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def creature_track(scene):
    for track in tracks.all_tracks(scene):
        if track.kind == 'AUDIO' and tracks.name(scene, track) == cfg.CREATURE_TRACK:
            return track
    return tracks.add(scene, 'AUDIO', track_name=cfg.CREATURE_TRACK)


def bake(scene, strip, name):
    """Bake the voice clip into creature preset `name`. Returns the new clip or a message."""
    if strip.type != 'SOUND' or strip.sound is None:
        return "Select a voice clip"
    from ..storyboard import panel_cache
    preset = cfg.CREATURES[name]
    x = stack(analysis.sound_path(strip.sound), preset)
    path = os.path.join(panel_cache.cache_dir(), f"creature_{uuid.uuid4().hex[:8]}.wav")
    _write_wav(path, x)
    track = creature_track(scene)
    sed = clips.editor(scene)
    spare = max([s.channel for s in sed.strips_all] + [len(tracks.all_tracks(scene))]) + 1
    s, e = clips.start(strip), clips.end(strip)
    new = sed.strips.new_sound(f"{strip.name} ({name})", path, spare, int(round(strip.content_start)))
    new.sound.pack()                                       # (kept in the project, like voice takes)
    new.left_handle, new.right_handle = s, e
    room = ripple.make_room(scene, tracks.channel_of(scene, track), s, e - s)
    if room is None:
        sed.strips.remove(new)
        return "No room on the Creature track there"
    if room[1] < e - s:
        new.right_handle = s + room[1]
    new.channel = tracks.channel_of(scene, track)
    new["plastron_creature"] = name
    if strip.get(clips.LINK):
        new[clips.LINK] = strip[clips.LINK]
        clips._connect([strip, new])
    else:
        clips.link([strip, new])
    strip.mute = True                                       # (the creature plays instead)
    events.clips_changed(scene)
    return new


def _preset_items(_self, _context):
    return [(n, n, f"Bake the voice as a {n}") for n in cfg.CREATURES]


class PLASTRON_OT_creature_bake(bpy.types.Operator):
    """Bake the selected voice clip into a creature voice (a stack of pitched copies)"""
    bl_idname = "plastron.creature_bake"
    bl_label = "Creature Voice"
    bl_options = {'REGISTER', 'UNDO'}
    preset: bpy.props.EnumProperty(name="Creature", items=_preset_items)

    def execute(self, context):
        sed = context.scene.sequence_editor
        strip = sed.active_strip if sed else None
        if strip is None or not strip.select or strip.type != 'SOUND' or strip.get("plastron_creature"):
            self.report({'INFO'}, "Select a voice clip first")
            return {'CANCELLED'}
        result = bake(context.scene, strip, self.preset)
        if isinstance(result, str):
            self.report({'WARNING'}, result)
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_MT_creature(bpy.types.Menu):
    bl_label = "Creature Voice"

    def draw(self, context):
        for name in cfg.CREATURES:
            self.layout.operator("plastron.creature_bake", text=name).preset = name


def draw_tools(layout, context):
    layout.label(text="Creature voice (selected voice clip)")
    layout.menu("PLASTRON_MT_creature", icon='GHOST_ENABLED')


classes = (PLASTRON_OT_creature_bake, PLASTRON_MT_creature)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from . import panel
    panel.EXTRA.append(draw_tools)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
