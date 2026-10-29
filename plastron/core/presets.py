"""Shared presets store: named bundles of settings, of any kind (brushes now;
motion, drop warp, export... later).

Built-in presets are JSON files in plastron/presets/<kind>/. Presets saved
from inside Plastron are JSON files in Blender's config folder
(plastron_presets/<kind>/), which updates keep. A feature registers a kind
with how to apply a preset and how to capture the current settings as one.
"""

import json
import os
import re

import bpy

BUILT_IN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets")

_kinds = {}   # kind -> {"apply": func(context, values), "capture": func(context) -> dict}
_cache = {}   # kind -> list of presets (read once; menus draw often)


def register_kind(kind, apply, capture):
    _kinds[kind] = {"apply": apply, "capture": capture}


def user_dir(kind):
    return os.path.join(bpy.utils.user_resource('CONFIG'), "plastron_presets", kind)


def _read(folder, built_in):
    out = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                values = json.load(f)
        except (OSError, ValueError) as err:
            print(f"Plastron: skipping preset {name}: {err}")
            continue
        values.setdefault("name", os.path.splitext(name)[0])
        values["built_in"] = built_in
        values["file"] = os.path.join(folder, name)
        out.append(values)
    return out


def all_presets(kind):
    """Built-in presets (by "order"), then saved ones (by name). A saved
    preset with a built-in's name replaces it."""
    if kind not in _cache:
        _cache[kind] = _load(kind)
    return _cache[kind]


def _load(kind):
    built = sorted(_read(os.path.join(BUILT_IN, kind), True), key=lambda p: (p.get("order", 99), p["name"]))
    saved = sorted(_read(user_dir(kind), False), key=lambda p: p["name"].lower())
    names = {p["name"] for p in saved}
    return [p for p in built if p["name"] not in names] + saved


def get(kind, name):
    return next((p for p in all_presets(kind) if p["name"] == name), None)


def apply(kind, name, context):
    preset = get(kind, name)
    if preset is None:
        return False
    _kinds[kind]["apply"](context, preset)
    return True


def _file_name(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_").lower() or "preset"


def save(kind, name, context):
    """Save the current settings as a preset called name."""
    values = _kinds[kind]["capture"](context)
    values["name"] = name
    folder = user_dir(kind)
    os.makedirs(folder, exist_ok=True)
    existing = next((p for p in _read(folder, False) if p["name"] == name), None)
    path = existing["file"] if existing else os.path.join(folder, _file_name(name) + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(values, f, indent=1)
    _cache.pop(kind, None)
    return path


def delete(kind, name):
    """Delete a saved preset (built-in ones stay)."""
    preset = next((p for p in all_presets(kind) if p["name"] == name and not p["built_in"]), None)
    if preset is None:
        return False
    os.remove(preset["file"])
    _cache.pop(kind, None)
    return True


# --- operators + menu (shared by every kind) ----------------------------------------

class PLASTRON_OT_preset_apply(bpy.types.Operator):
    """Use this preset"""
    bl_idname = "plastron.preset_apply"
    bl_label = "Use Preset"
    bl_options = {'REGISTER', 'UNDO'}
    kind: bpy.props.StringProperty()
    name: bpy.props.StringProperty()

    def execute(self, context):
        if not apply(self.kind, self.name, context):
            self.report({'WARNING'}, f"No preset called {self.name}")
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_preset_save(bpy.types.Operator):
    """Save the current settings as a preset"""
    bl_idname = "plastron.preset_save"
    bl_label = "Save Preset"
    kind: bpy.props.StringProperty(options={'HIDDEN'})
    name: bpy.props.StringProperty(name="Name", default="My preset")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if not self.name.strip():
            return {'CANCELLED'}
        save(self.kind, self.name.strip(), context)
        return {'FINISHED'}


class PLASTRON_OT_preset_delete(bpy.types.Operator):
    """Delete this saved preset"""
    bl_idname = "plastron.preset_delete"
    bl_label = "Delete Preset"
    kind: bpy.props.StringProperty()
    name: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        return {'FINISHED'} if delete(self.kind, self.name) else {'CANCELLED'}


def draw_menu(layout, kind):
    """A preset list for any kind: click to use; save the current settings."""
    for preset in all_presets(kind):
        row = layout.row(align=True)
        op = row.operator("plastron.preset_apply", text=preset["name"])
        op.kind, op.name = kind, preset["name"]
        if not preset["built_in"]:
            op = row.operator("plastron.preset_delete", text="", icon='X')
            op.kind, op.name = kind, preset["name"]
    layout.separator()
    layout.operator("plastron.preset_save", text="Save current as preset...", icon='ADD').kind = kind


classes = (PLASTRON_OT_preset_apply, PLASTRON_OT_preset_save, PLASTRON_OT_preset_delete)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _kinds.clear()
    _cache.clear()
