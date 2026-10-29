"""Builds Plastron's keymap from config/keymap.py and strips Blender's.

Runs last in registration, so every feature's operators exist by then.
Shortcuts for actions that aren't built yet are skipped and listed in
`pending`.
"""

import fnmatch

import bpy

from ..config import keymap as cfg
from .util import operator_exists

_KEY_NAMES = {
    "=": 'EQUAL', "-": 'MINUS', "[": 'LEFT_BRACKET', "]": 'RIGHT_BRACKET',
    "Space": 'SPACE', "Esc": 'ESC', "Enter": 'RET', "Tab": 'TAB',
    "Delete": 'DEL', "Backspace": 'BACK_SPACE',
    "Left": 'LEFT_ARROW', "Right": 'RIGHT_ARROW', "Up": 'UP_ARROW', "Down": 'DOWN_ARROW',
    "Home": 'HOME', "End": 'END',
    "LMB": 'LEFTMOUSE', "MMB": 'MIDDLEMOUSE', "RMB": 'RIGHTMOUSE',
    "WheelUp": 'WHEELUPMOUSE', "WheelDown": 'WHEELDOWNMOUSE',
}
_DIGITS = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]
_MODIFIERS = {"Ctrl": "ctrl", "Alt": "alt", "Shift": "shift", "Cmd": "oskey"}

_added = []      # (keymap, keymap item) in the add-on keyconfig
_stripped = set()  # names of user keymaps we changed
pending = []     # shortcut entries whose action isn't built yet


def parse_key(text):
    """"Ctrl+Shift+Z" -> ('Z', {"ctrl": True, "shift": True})."""
    *mods, key = text.split("+")
    flags = {}
    for mod in mods:
        flags[_MODIFIERS[mod]] = True
    if key in _KEY_NAMES:
        key_type = _KEY_NAMES[key]
    elif key.isdigit() and len(key) == 1:
        key_type = _DIGITS[int(key)]
    else:
        key_type = key.upper()
    return key_type, flags


def entries():
    """Config shortcuts as dicts."""
    out = []
    for row in cfg.SHORTCUTS:
        where, key, action, description, *rest = row
        out.append({
            "where": where, "key": key, "action": action,
            "description": description, "settings": rest[0] if rest else {},
        })
    return out


def _signature(km_name, kmi):
    return (km_name, kmi.type, bool(kmi.ctrl), bool(kmi.alt), bool(kmi.shift), bool(kmi.oskey))


def _dropped(km_name, kmi):
    return any(fnmatch.fnmatchcase(km_name, name) and
               any(fnmatch.fnmatchcase(kmi.idname, p) for p in actions)
               for name, actions in cfg.BLENDER_DROP.items())


def _keep_patterns(km_name):
    patterns = []
    for name_pattern, actions in cfg.BLENDER_KEEP.items():
        if fnmatch.fnmatchcase(km_name, name_pattern):
            patterns += actions
    return patterns


def _add_plastron_keys(kc):
    taken = set()
    for entry in entries():
        if not operator_exists(entry["action"]):
            pending.append(entry)
            continue
        km_name, space, region = cfg.WHERE[entry["where"]]
        km = kc.keymaps.new(name=km_name, space_type=space, region_type=region)
        key_type, flags = parse_key(entry["key"])
        if key_type == 'MOUSEMOVE':      # hover: any movement, any modifiers
            kmi = km.keymap_items.new(entry["action"], key_type, 'ANY', any=True)
        else:
            kmi = km.keymap_items.new(entry["action"], key_type, 'PRESS', **flags)
        kmi.repeat = entry["key"] in cfg.REPEAT
        for prop, value in entry["settings"].items():
            setattr(kmi.properties, prop, value)
        _added.append((km, kmi))
        if entry["action"] not in cfg.PASSES_ON:
            taken.add(_signature(km_name, kmi))
    return taken


def _strip_blender_keys(user_kc, addon_kc, taken):
    ours = {(km.name, kmi.idname) + _signature(km.name, kmi)[1:] for km, kmi in _added}
    for km in user_kc.keymaps:
        if km.is_modal:
            continue
        keep = _keep_patterns(km.name)
        for kmi in km.keymap_items:
            if (km.name, kmi.idname) + _signature(km.name, kmi)[1:] in ours:
                continue
            kept = any(fnmatch.fnmatchcase(kmi.idname, p) for p in keep)
            # Plastron's keys fire on press; a kept Blender item on the same key
            # only clashes if it also fires on press (click / drag items don't).
            clashes = _signature(km.name, kmi) in taken and kmi.value in {'PRESS', 'ANY'}
            if kept and not clashes and not _dropped(km.name, kmi):
                continue
            if kmi.active:
                kmi.active = False
                _stripped.add(km.name)


def register():
    wm = bpy.context.window_manager
    kc_addon = wm.keyconfigs.addon
    kc_user = wm.keyconfigs.user
    if kc_addon is None or kc_user is None:
        return
    pending.clear()
    taken = _add_plastron_keys(kc_addon)
    # Blender finishes building its keymaps after Plastron registers, so
    # strip once startup is complete.
    def strip():
        wm.keyconfigs.update()
        _strip_blender_keys(wm.keyconfigs.user, kc_addon, taken)
    bpy.app.timers.register(strip, first_interval=0.01)


def unregister():
    wm = bpy.context.window_manager
    for km, kmi in _added:
        km.keymap_items.remove(kmi)
    _added.clear()
    kc_user = wm.keyconfigs.user
    if kc_user:
        for name in _stripped:
            km = kc_user.keymaps.get(name)
            if km:
                km.restore_to_default()
    _stripped.clear()
