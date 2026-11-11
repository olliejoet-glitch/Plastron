"""Choosing the microphone (Ollie: "can I select audio input manually?").

The ▾ next to Record lists the computer's inputs; the choice is remembered
(Plastron's settings, by name: device numbers change when things are
plugged in). If the chosen one isn't there, recording uses the system's
default and says so. While recording, a level meter shows next to Stop.
"""

import os

import bpy

from ...core import user_settings
from . import recorder

KEY = "mic_device"


def inputs():
    """[(name, is the system default)] of the computer's audio inputs."""
    if recorder.fake():
        names = [n for n in os.environ.get("PLASTRON_FAKE_MIC_DEVICES", "Fake Mic").split(";") if n]
        return [(n, i == 0) for i, n in enumerate(names)]
    try:
        import sounddevice
        default = sounddevice.default.device[0]
        out = []
        for i, d in enumerate(sounddevice.query_devices()):
            if d.get("max_input_channels", 0) > 0 and d["name"] not in [n for n, _ in out]:
                out.append((d["name"], i == default))
        return out
    except Exception as err:                       # (not installed yet, no audio system)
        print("Plastron: couldn't list microphones:", err)
        return []


def chosen():
    """The chosen input's name, or None for the system default."""
    return user_settings.get(KEY) or None


def device_for_recording():
    """(device for the recorder or None = default, a note if the chosen one is missing)."""
    name = chosen()
    if name is None:
        return None, None
    if name in [n for n, _d in inputs()]:
        return name, None
    return None, f"{name} isn't connected: recording from the default microphone"


class PLASTRON_OT_mic_choose(bpy.types.Operator):
    """Record from this microphone"""
    bl_idname = "plastron.mic_choose"
    bl_label = "Choose Microphone"
    name: bpy.props.StringProperty()

    def execute(self, context):
        user_settings.set(KEY, self.name or None)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_PT_mic(bpy.types.Panel):
    """Which microphone Record uses"""
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'HEADER'
    bl_label = "Microphone"
    bl_ui_units_x = 14

    def draw(self, context):
        layout = self.layout
        layout.label(text="Record from:")
        col = layout.column(align=True)
        current = chosen()
        col.operator("plastron.mic_choose", text="System default", icon='RADIOBUT_ON' if current is None
                     else 'RADIOBUT_OFF', depress=current is None).name = ""
        found = inputs()
        for name, is_default in found:
            label = name + ("  (default)" if is_default else "")
            col.operator("plastron.mic_choose", text=label, depress=current == name,
                         icon='RADIOBUT_ON' if current == name else 'RADIOBUT_OFF').name = name
        if current is not None and current not in [n for n, _d in found]:
            layout.label(text=f"{current} isn't connected", icon='ERROR')
        if not found:
            layout.label(text="No microphones found (yet)", icon='INFO')


classes = (PLASTRON_OT_mic_choose, PLASTRON_PT_mic)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
