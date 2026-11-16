"""Choosing the microphone (Ollie: "can I select audio input manually?").

The ▾ next to Record lists the computer's inputs; the choice is remembered
(Plastron's settings, by name: device numbers change when things are
plugged in). If the chosen one isn't there, recording uses the system's
default and says so. While recording, a level meter shows next to Stop.
"""

import os

import bpy

from ...config import voice as cfg
from ...core import user_settings
from . import recorder

KEY = "mic_device"


def pick(devices, default, hidden=()):
    """[(name, is default, device index)] worth listing, from sounddevice's
    query_devices() list: inputs only, on the default input's audio system
    only (Windows repeats each one per system), full names (from another
    system's copy when this one cut it short), no stand-ins / virtual inputs
    (MIC_HIDE), none hidden by hand, each name once."""
    api = devices[default].get("hostapi") if 0 <= default < len(devices) else None
    others = [d["name"] for d in devices if d.get("max_input_channels", 0) > 0]
    out = []
    for i, d in enumerate(devices):
        name = d["name"]
        if d.get("max_input_channels", 0) <= 0 or (api is not None and d.get("hostapi") != api):
            continue
        longer = [n for n in others if n.startswith(name) and len(n) > len(name)]
        if longer and len(name) >= 31:
            name = min(longer, key=len)
        if any(word in name.lower() for word in cfg.MIC_HIDE) or name in hidden \
                or name in [n for n, _d, _i in out]:
            continue
        out.append((name, i == default, i))
    return out


HIDDEN_KEY = "mic_hidden"


def hidden():
    return list(user_settings.get(HIDDEN_KEY) or [])


def _found():
    if recorder.fake():
        names = [n for n in os.environ.get("PLASTRON_FAKE_MIC_DEVICES", "Fake Mic").split(";") if n]
        return [(n, i == 0, n) for i, n in enumerate(names) if n not in hidden()]
    try:
        import sounddevice
        return pick(list(sounddevice.query_devices()), sounddevice.default.device[0], hidden())
    except Exception as err:                       # (not installed yet, no audio system)
        print("Plastron: couldn't list microphones:", err)
        return []


def inputs():
    """[(name, is the system default)] of the computer's microphones."""
    return [(n, d) for n, d, _i in _found()]


def chosen():
    """The chosen input's name, or None for the system default."""
    return user_settings.get(KEY) or None


def device_for_recording():
    """(device for the recorder or None = default, a note if the chosen one is missing)."""
    name = chosen()
    if name is None:
        return None, None
    for n, _d, device in _found():
        if n == name:
            return device, None        # (by number: a name can match several audio systems)
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


class PLASTRON_OT_mic_hide(bpy.types.Operator):
    """Hide this input from the list (not a microphone you use)"""
    bl_idname = "plastron.mic_hide"
    bl_label = "Hide Input"
    name: bpy.props.StringProperty()
    show: bpy.props.BoolProperty(default=False, description="Show every hidden input again")

    def execute(self, context):
        names = hidden()
        if self.show:
            names = []
        elif self.name and self.name not in names:
            names.append(self.name)
            if chosen() == self.name:
                user_settings.set(KEY, None)
        user_settings.set(HIDDEN_KEY, names)
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
            row = col.row(align=True)
            row.operator("plastron.mic_choose", text=label, depress=current == name,
                         icon='RADIOBUT_ON' if current == name else 'RADIOBUT_OFF').name = name
            row.operator("plastron.mic_hide", text="", icon='X').name = name
        if current is not None and current not in [n for n, _d in found]:
            layout.label(text=f"{current} isn't connected", icon='ERROR')
        if not found:
            layout.label(text="No microphones found (yet)", icon='INFO')
        if hidden():
            layout.operator("plastron.mic_hide", text=f"Show {len(hidden())} hidden", icon='HIDE_OFF').show = True


classes = (PLASTRON_OT_mic_choose, PLASTRON_OT_mic_hide, PLASTRON_PT_mic)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
