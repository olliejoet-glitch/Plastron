"""Record at playhead (Ctrl+R starts and stops).

Records the microphone onto the active audio track (else the top audio
track) from the playhead, while the timeline plays so you can watch the
panels. Recording where a voice clip already is records a new take of it
(from the clip's start; the old take is muted meanwhile). Stopping
playback (Space) stops recording too. Each recording is transcribed after.
"""

import os
import time
import uuid

import bpy

from ...config import voice as cfg
from ...core import deps
from ...timeline import clips, tracks
from . import recorder, takes, transcribe

_rec = {"mic": None, "scene": None, "track": None, "frame": 0, "retake": None,
        "started": 0.0, "muted": None}


def recording():
    return _rec["mic"] is not None


def elapsed():
    return time.monotonic() - _rec["started"] if recording() else 0.0


def _window_override():
    wm = bpy.context.window_manager
    window = bpy.context.window or (wm.windows[0] if wm.windows else None)
    return bpy.context.temp_override(window=window, screen=window.screen)


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'SEQUENCE_EDITOR', 'TOPBAR'}:
                area.tag_redraw()


def start(context):
    """Start recording. Returns an error message or None."""
    scene = context.scene
    if not recorder.ready():
        deps.ensure(cfg.PACKAGES, "voice recording")
        return deps.status() or "Voice recording is being set up; try again in a moment"
    track = takes.target_track(scene)
    if track is None:
        return "There's no audio track to record onto"
    if tracks.is_locked(scene, track):
        return "That track is locked"
    frame = scene.frame_current
    retake = takes.clip_for_retake(scene, track, frame)
    if retake is not None:
        frame = clips.start(retake)
        scene.frame_current = frame
        if not retake.mute:
            retake.mute = True
            _rec["muted"] = retake.name
    try:
        mic = recorder.start()
    except Exception as err:               # no microphone, device busy...
        _unmute(scene)
        return f"Couldn't open the microphone: {err}"
    _rec.update(mic=mic, scene=scene.name, track=track.uid, frame=frame,
                retake=retake.name if retake else None, started=time.monotonic())
    if not context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()
    bpy.app.timers.register(_watch, first_interval=0.2)
    _redraw()
    return None


def _unmute(scene):
    name = _rec.get("muted")
    if name and scene.sequence_editor and name in scene.sequence_editor.strips_all:
        scene.sequence_editor.strips_all[name].mute = False
    _rec["muted"] = None


def stop(context=None):
    """Stop recording and put the take on the timeline. Returns the strip,
    an error message, or None if nothing was recorded."""
    mic = _rec["mic"]
    if mic is None:
        return None
    samples = mic.stop()
    _rec["mic"] = None
    with _window_override():
        if bpy.context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
    scene = bpy.data.scenes.get(_rec["scene"])
    if scene is None:
        return None
    _unmute(scene)
    if len(samples) < cfg.SAMPLE_RATE * 0.2:
        _redraw()
        return None                         # too short to be a take
    wav = os.path.join(bpy.app.tempdir, "plastron_recordings", uuid.uuid4().hex[:10] + ".wav")
    duration = recorder.write_wav(wav, samples)
    track = next((t for t in tracks.all_tracks(scene) if t.uid == _rec["track"]), None)
    strip = None
    if _rec["retake"] and _rec["retake"] in scene.sequence_editor.strips_all:
        strip = takes.add_take(scene, scene.sequence_editor.strips_all[_rec["retake"]], wav, duration)
    elif track is not None:
        strip = takes.new_clip(scene, track, _rec["frame"], wav, duration)
    if isinstance(strip, str) or strip is None:
        _redraw()
        return strip
    for s in clips.all_clips(scene):
        s.select = False
    strip.select = True
    scene.sequence_editor.active_strip = strip
    transcribe.queue(takes.active_take(strip), wav)
    try:
        with _window_override():
            bpy.ops.ed.undo_push(message="Record voice")
    except RuntimeError:
        pass
    _redraw()
    return strip


def _watch():
    """While recording: keep the elapsed time fresh; stopping playback stops it."""
    if not recording():
        return None
    screen = bpy.context.window_manager.windows[0].screen if bpy.context.window_manager.windows else None
    if screen is not None and not screen.is_animation_playing:
        stop()
        return None
    _redraw()
    return 0.2


class PLASTRON_OT_voice_record(bpy.types.Operator):
    """Record your voice at the playhead (again to stop). Recording over a
    voice clip records a new take of it"""
    bl_idname = "plastron.voice_record"
    bl_label = "Record Voice"

    def execute(self, context):
        if recording():
            result = stop(context)
            if isinstance(result, str):
                self.report({'WARNING'}, result)
            return {'FINISHED'}
        problem = start(context)
        if problem:
            self.report({'WARNING'}, problem)
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_voice_take(bpy.types.Operator):
    """Switch the selected voice clip to its previous / next take"""
    bl_idname = "plastron.voice_take"
    bl_label = "Switch Take"
    bl_options = {'REGISTER', 'UNDO'}

    step: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        sed = context.scene.sequence_editor
        return sed is not None and takes.is_voice(sed.active_strip)

    def execute(self, context):
        strip = context.scene.sequence_editor.active_strip
        v = strip.plastron_voice
        index = (v.active + self.step) % len(v.takes)
        if index == v.active or not takes.use_take(context.scene, strip, index):
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_voice_transcribe(bpy.types.Operator):
    """Transcribe the selected voice clip's take again"""
    bl_idname = "plastron.voice_transcribe"
    bl_label = "Transcribe Again"

    @classmethod
    def poll(cls, context):
        sed = context.scene.sequence_editor
        return sed is not None and takes.is_voice(sed.active_strip)

    def execute(self, context):
        take = takes.active_take(context.scene.sequence_editor.active_strip)
        return {'FINISHED'} if transcribe.queue_again(take) else {'CANCELLED'}


classes = (PLASTRON_OT_voice_record, PLASTRON_OT_voice_take, PLASTRON_OT_voice_transcribe)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    if recording():
        stop()
    if bpy.app.timers.is_registered(_watch):
        bpy.app.timers.unregister(_watch)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
