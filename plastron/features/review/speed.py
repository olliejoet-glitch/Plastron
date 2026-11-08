"""Speed playback (the brief's "play at 1.5x or 2x with the voice kept at
normal pitch"). Timeline header: 1x / 1.5x / 2x.

At 1.5x / 2x: the project's sound is mixed down, time-stretched with its
pitch kept (Blender's own audio library, Audaspace), and played from the
playhead while the picture plays at fps x speed with the project's own
sound muted. When playback stops everything is put back as it was. Nothing
in the project changes.
"""

import os

import bpy

from ...config import review as cfg
from ...core import handlers

_state = {"active": False, "handle": None, "fps_base": 1.0, "use_audio": True, "sync": 'AUDIO_SYNC',
          "speed": 1.0}


def mix_path():
    return os.path.join(bpy.app.tempdir, "plastron_speed_mix.wav")


def mixdown(context):
    """The project's sound as one WAV (fast: no picture)."""
    path = mix_path()
    with context.temp_override(scene=context.scene):
        bpy.ops.sound.mixdown(filepath=path, check_existing=False, container='WAV', codec='PCM',
                              format='S16', mixrate=48000, channels='STEREO')
    return path


def stretched(path, speed, offset_seconds):
    """The mixdown from offset, sped up with the pitch kept (an aud.Sound)."""
    import aud
    sound = aud.Sound(path)
    if offset_seconds > 0:
        sound = sound.limit(offset_seconds, 10 ** 6)
    return sound.timeStretchPitchScale(1.0 / speed, 1.0)


def start(context, speed):
    scene = context.scene
    fps = scene.render.fps / scene.render.fps_base
    offset = max(0.0, (scene.frame_current - scene.frame_start) / fps)
    handle = None
    try:
        sound = stretched(mixdown(context), speed, offset)
        import aud
        handle = aud.Device().play(sound)
    except Exception as err:             # no sound device / nothing to mix: picture only
        print("Plastron: speed playback without sound:", err)
    _state.update(active=True, handle=handle, fps_base=scene.render.fps_base,
                  use_audio=scene.use_audio, sync=scene.sync_mode, speed=speed)
    scene.render.fps_base = scene.render.fps_base / speed
    scene.use_audio = False
    scene.sync_mode = 'FRAME_DROP'
    bpy.ops.screen.animation_play()


def stop(scene=None):
    """Put the project back as it was (playback stopped)."""
    if not _state["active"]:
        return
    scene = scene or bpy.context.scene
    handle = _state["handle"]
    if handle is not None:
        try:
            handle.stop()
        except Exception:
            pass
    scene.render.fps_base = _state["fps_base"]
    scene.use_audio = _state["use_audio"]
    scene.sync_mode = _state["sync"]
    _state.update(active=False, handle=None, speed=1.0)


def current():
    return _state["speed"] if _state["active"] else 1.0


class PLASTRON_OT_play_speed(bpy.types.Operator):
    """Play at this speed (the voice keeps its pitch); again: stop"""
    bl_idname = "plastron.play_speed"
    bl_label = "Play at Speed"
    speed: bpy.props.FloatProperty(default=1.5)

    def execute(self, context):
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
            stop(context.scene)
            return {'FINISHED'}
        if abs(self.speed - 1.0) < 1e-6:
            bpy.ops.screen.animation_play()
        else:
            start(context, self.speed)
        return {'FINISHED'}


def draw_header(layout, context):
    row = layout.row(align=True)
    for speed in cfg.SPEEDS:
        label = f"{speed:g}×"
        op = row.operator("plastron.play_speed", text=label, depress=abs(current() - speed) < 1e-6
                          and _state["active"])
        op.speed = speed


def _after_playback(scene, *_args):
    stop(scene)


def register():
    bpy.utils.register_class(PLASTRON_OT_play_speed)
    handlers.add("animation_playback_post", _after_playback)
    from ...timeline import header
    header.add_section(draw_header)


def unregister():
    stop()
    bpy.utils.unregister_class(PLASTRON_OT_play_speed)
