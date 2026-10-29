"""Every shortcut in config/keymap.py is bound; Blender's own are stripped."""

import fnmatch
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.keymap")
keymaps = h.module("core.keymaps")
util = h.module("core.util")

# Actions that are expected to be missing until later stages.
LATER_STAGES = {
    "plastron.transform", "plastron.strokes_copy", "plastron.strokes_paste",
    "plastron.strokes_flip", "plastron.eyedropper", "plastron.panel_new",
    "plastron.clip_split", "plastron.clip_delete", "plastron.loop_in", "plastron.loop_out",
}


def find(km, action, key):
    key_type, flags = keymaps.parse_key(key)
    for kmi in km.keymap_items:
        if (kmi.idname == action and kmi.type == key_type and kmi.active
                and all(bool(getattr(kmi, m)) == flags.get(m, False)
                        for m in ("ctrl", "alt", "shift", "oskey"))):
            return kmi
    return None


def steps():
    yield 1.0
    user = bpy.context.window_manager.keyconfigs.user

    # 1. Every built shortcut is bound, active, with its settings.
    missing = []
    for entry in keymaps.entries():
        if not util.operator_exists(entry["action"]):
            continue
        km = user.keymaps.get(cfg.WHERE[entry["where"]][0])
        kmi = km and find(km, entry["action"], entry["key"])
        ok = kmi is not None and all(
            h.close(getattr(kmi.properties, k), v) if isinstance(v, float)
            else getattr(kmi.properties, k) == v
            for k, v in entry["settings"].items())
        if not ok:
            missing.append(f'{entry["key"]} -> {entry["action"]}')
    h.check("all built shortcuts are bound", not missing, missing)

    pending = sorted({e["action"] for e in keymaps.pending})
    h.check("only later-stage shortcuts are pending", set(pending) <= LATER_STAGES, pending)

    # 2. No other active item in the same keymap uses a Plastron key
    #    (one of the two would never fire).
    clashes = []
    for entry in keymaps.entries():
        if not util.operator_exists(entry["action"]):
            continue
        km = user.keymaps.get(cfg.WHERE[entry["where"]][0])
        key_type, flags = keymaps.parse_key(entry["key"])
        for kmi in km.keymap_items:
            if (kmi.active and kmi.idname != entry["action"] and kmi.type == key_type
                    and kmi.value in {'PRESS', 'ANY', 'CLICK', 'CLICK_DRAG'}
                    and all(bool(getattr(kmi, m)) == flags.get(m, False)
                            for m in ("ctrl", "alt", "shift", "oskey"))):
                clashes.append(f'{km.name}: {entry["key"]} {entry["action"]} / {kmi.idname}')
    h.check("no clashing shortcuts", not clashes, clashes)

    # 3. Blender's own shortcuts are switched off.
    def active(km_name, action, key_type=None):
        km = user.keymaps.get(km_name)
        return any(k.active and k.idname == action and (key_type is None or k.type == key_type)
                   for k in km.keymap_items)

    stripped = [
        ("Window", "wm.search_menu"),                       # F3 search
        ("Screen", "screen.screen_full_area"),              # Ctrl+Space maximise
        ("Object Mode", "transform.translate"),             # G
        ("Object Non-modal", "object.mode_set"),            # Tab
        ("3D View", "view3d.rotate"),                       # orbit
        ("Grease Pencil Draw Mode", "grease_pencil.erase_box"),
        ("Frames", "screen.frame_offset"),
        ("Markers", "marker.add"),
        ("Region Context Menu", "screen.region_context_menu"),  # right-click menus
    ]
    still_on = [f"{km}: {op}" for km, op in stripped if active(km, op)]
    h.check("Blender shortcuts stripped", not still_on, still_on)

    kept = [
        ("Text", "text.insert"),                            # typing in the script
        ("Screen Editing", "screen.area_move"),             # resizing areas
        ("Screen", "screen.animation_step"),                # playback timer
        ("Time Scrub", "anim.change_frame"),                # scrubbing on the ruler
        ("Grease Pencil Brush Stroke", "grease_pencil.brush_stroke"),  # drawing
        ("User Interface", "ui.eyedropper_color"),
    ]
    off = [f"{km}: {op}" for km, op in kept if not active(km, op)]
    h.check("essential Blender shortcuts kept", not off, off)

    # 4. Everything else is off: any active Blender item must match BLENDER_KEEP.
    ours = {(cfg.WHERE[e["where"]][0], e["action"]) for e in keymaps.entries()}
    stray = []
    for km in user.keymaps:
        if km.is_modal:
            continue
        keep = keymaps._keep_patterns(km.name)
        for kmi in km.keymap_items:
            if not kmi.active or (km.name, kmi.idname) in ours:
                continue
            if not any(fnmatch.fnmatchcase(kmi.idname, p) for p in keep):
                stray.append(f"{km.name}: {kmi.type} -> {kmi.idname}")
    h.check("no stray Blender shortcuts", not stray, stray[:15])

    # 5. The key-string parser.
    h.check("parse 'Ctrl+Shift+Z'", keymaps.parse_key("Ctrl+Shift+Z") == ('Z', {"ctrl": True, "shift": True}))
    h.check("parse 'Ctrl+0' / 'Ctrl+='",
            keymaps.parse_key("Ctrl+0")[0] == 'ZERO' and keymaps.parse_key("Ctrl+=")[0] == 'EQUAL')


h.run(steps())
