"""Copy / paste clip attributes (Ollie: "copy and paste clip attributes,
like size, position, grading").

Ctrl+C over the timeline / preview (or Copy in the Clip panel) copies the
selected clip's attributes; Ctrl+V (or Paste...) opens a small box listing
what was copied, ticked as last time, and pastes the ticked ones onto every
selected clip (each takes what it can: a sound takes volume / fades /
speed, a picture position / size / grade...). One undo step. The list and
first ticks: PASTE_ATTRIBUTES in config/edit.py; ticks remembered in
user_settings "paste_attributes".

A picture copied on the computer AFTER that (a screenshot, a frame from a
browser) wins: Ctrl+V then puts it on the timeline at the playhead as a
picture clip (like one from the media bin), saved as a PNG next to the
project (<project>_cache/pasted/; untitled: Plastron's plastron_pasted/).

A video's linked sound counts with it: copying a video copies its sound's
volume too. Panels keep their own size / place (their painting is fitted
to the frame), so they never take position / size / rotation / crop.
"""

import bpy

from ...config import edit as cfg
from ...core import user_settings
from ...timeline import clips, events, ripple

SETTING = "paste_attributes"
_clipboard = {}            # {group: value}; "_from": the clip's name


def _is_panel(strip):
    from ..storyboard.panels import is_panel
    return is_panel(strip)


def _is_block(strip):
    return bool(strip.get("plastron_line"))


def _visual(strip):
    return strip.type != 'SOUND' and not _is_block(strip)


def _placeable(strip):
    return _visual(strip) and not _is_panel(strip) and hasattr(strip, "transform")


# --- Reading / writing each group -----------------------------------------------------------------
# read(strip) -> value or None (the clip has none of it); write(scene, strip, value) -> True if set.

def _read_position(s):
    return (s.transform.offset_x, s.transform.offset_y) if _placeable(s) else None


def _write_position(_scene, s, v):
    if not _placeable(s):
        return False
    s.transform.offset_x, s.transform.offset_y = v
    return True


def _read_size(s):
    return (s.transform.scale_x, s.transform.scale_y) if _placeable(s) else None


def _write_size(_scene, s, v):
    if not _placeable(s):
        return False
    s.transform.scale_x, s.transform.scale_y = v
    return True


def _read_rotation(s):
    return s.transform.rotation if _placeable(s) else None


def _write_rotation(_scene, s, v):
    if not _placeable(s):
        return False
    s.transform.rotation = v
    return True


def _read_crop(s):
    if not _placeable(s) or not hasattr(s, "crop"):
        return None
    c = s.crop
    return (c.min_x, c.max_x, c.min_y, c.max_y)


def _write_crop(_scene, s, v):
    if not _placeable(s) or not hasattr(s, "crop"):
        return False
    s.crop.min_x, s.crop.max_x, s.crop.min_y, s.crop.max_y = v
    return True


def _read_opacity(s):
    return (s.plastron.opacity, s.blend_type) if _visual(s) else None


def _write_opacity(_scene, s, v):
    if not _visual(s):
        return False
    s.blend_type = v[1]
    s.plastron.opacity = v[0]
    return True


def _read_flip(s):
    return (s.use_flip_x, s.use_flip_y) if _visual(s) and hasattr(s, "use_flip_x") else None


def _write_flip(_scene, s, v):
    if not (_visual(s) and hasattr(s, "use_flip_x")):
        return False
    s.use_flip_x, s.use_flip_y = v
    return True


def _read_grade(s):
    from ..grade import grade
    return grade.values(s) if grade.gradable(s) and grade.is_graded(s) else None


def _write_grade(_scene, s, v):
    from ..grade import grade
    if not grade.gradable(s) or _is_block(s):
        return False
    grade.apply(s, dict(v), reset=True)
    return True


def _read_title(s):
    from .titles import is_title, style_of
    return style_of(bpy.context.scene, s) if is_title(s) else None


def _write_title(scene, s, v):
    from .titles import is_title, apply_style
    if not is_title(s):
        return False
    apply_style(scene, s, v)
    return True


def _read_fades(s):
    return None if _is_block(s) else (s.plastron.fade_in, s.plastron.fade_out)


def _write_fades(_scene, s, v):
    if _is_block(s):
        return False
    s.plastron.fade_in, s.plastron.fade_out = v
    return True


def _speedable(s):
    return s.type in {'MOVIE', 'SOUND'}


def _read_speed(s):
    return float(s.get("plastron_speed", 1.0)) if _speedable(s) else None


def _write_speed(scene, s, v):
    if not _speedable(s):
        return False
    ripple.set_speed(scene, s, v)
    return True


def _read_volume(s):
    return s.plastron.volume if s.type == 'SOUND' else None


def _write_volume(_scene, s, v):
    if s.type != 'SOUND':
        return False
    s.plastron.volume = v
    return True


def _read_shorts(s):
    from .shorts import KEY
    return float(s.get(KEY, 0.0)) if _placeable(s) else None


def _write_shorts(_scene, s, v):
    from .shorts import KEY
    if not _placeable(s):
        return False
    s[KEY] = v
    return True


GROUPS = {name: (globals()[f"_read_{name}"], globals()[f"_write_{name}"])
          for name, _label, _on in cfg.PASTE_ATTRIBUTES}
LABELS = {name: label for name, label, _on in cfg.PASTE_ATTRIBUTES}


def read(scene, strip):
    """{group: value} of everything the clip (and, for sound-only groups,
    its linked sound) has."""
    out = {}
    partners = [strip] + [s for s in clips.linked(strip, clips.top_clips(scene))]
    for name, (get, _put) in GROUPS.items():
        for s in partners:              # (a video: its sound's volume / speed too)
            value = get(s)
            if value is not None:
                out[name] = value
                break
    return out


def paste(scene, targets, values, groups):
    """Write the chosen groups onto the targets. Returns how many clips took
    something."""
    took = set()
    sped = set()
    with events.batch():
        for s in targets:
            for name in groups:
                if name not in values or name == "speed":
                    continue
                if GROUPS[name][1](scene, s, values[name]):
                    took.add(s.name)
        if "speed" in groups and "speed" in values:      # (last: it moves clips; linked ones go together)
            for s in targets:
                if s.name in sped or not _speedable(s):
                    continue
                group = clips.with_linked([s], clips.top_clips(scene))
                sped.update(x.name for x in group)
                if _write_speed(scene, s, values["speed"]):
                    took.add(s.name)
        events.emit("mix_changed", scene)
        events.clips_changed(scene)
    return len(took)


# --- Operators ----------------------------------------------------------------------------------

def _source(context):
    scene = context.scene
    sed = scene.sequence_editor if scene else None
    if sed is None:
        return None
    active = sed.active_strip
    if active is not None and active.select and not _is_block(active):
        return active
    return next((s for s in clips.top_clips(scene) if s.select and not _is_block(s)), None)


def _targets(context):
    return [s for s in clips.top_clips(context.scene) if s.select and not _is_block(s)]


def ticked():
    saved = user_settings.get(SETTING) or {}
    return {name: bool(saved.get(name, on)) for name, _label, on in cfg.PASTE_ATTRIBUTES}


def _pasted_folder():
    import os
    if bpy.data.filepath:
        from ..storyboard.panel_cache import cache_dir
        return os.path.join(cache_dir(), "pasted")
    return os.path.join(bpy.utils.user_resource('CONFIG'), "plastron_pasted")


def save_picture(picture, folder=None):
    """A clipboard picture (RGBA floats, rows bottom-up) as a new PNG. Returns its path."""
    import os
    import time
    folder = folder or _pasted_folder()
    os.makedirs(folder, exist_ok=True)
    name = time.strftime("Pasted %Y-%m-%d %H%M%S")
    path, n = os.path.join(folder, name + ".png"), 2
    while os.path.exists(path):
        path, n = os.path.join(folder, f"{name} {n}.png"), n + 1
    h, w = picture.shape[:2]
    img = bpy.data.images.new("plastron_pasted", w, h, alpha=True)
    try:
        img.pixels.foreach_set(picture.astype("float32").ravel())
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    finally:
        bpy.data.images.remove(img)
    return path


def paste_picture(context):
    """The computer's clipboard picture on the timeline at the playhead, if
    there is one copied after Plastron's own Ctrl+C. Returns the clip, a
    message, or None (no picture: paste attributes instead)."""
    from ..canvas_edit import image_paste
    from . import media
    if not image_paste.clipboard_is_newer(bool(_clipboard)):
        return None
    picture = image_paste.read_system(context.window)
    if picture is None:
        return None
    made = media.place(context.scene, save_picture(picture))
    if isinstance(made, str):
        return made
    for s in clips.top_clips(context.scene):
        s.select = s in made
    context.scene.sequence_editor.active_strip = made[0]
    return made[0]


class PLASTRON_OT_attributes_copy(bpy.types.Operator):
    """Copy the selected clip's attributes (position, size, grade, fades...)"""
    bl_idname = "plastron.attributes_copy"
    bl_label = "Copy Attributes"

    @classmethod
    def poll(cls, context):
        from ...core.views import typing
        return _source(context) is not None and not typing(context)     # (typing a title: its own copy)

    def execute(self, context):
        strip = _source(context)
        values = read(context.scene, strip)
        _clipboard.clear()
        _clipboard.update(values)
        _clipboard["_from"] = strip.name
        from ..canvas_edit import image_paste
        image_paste.mark_copied()             # (a picture copied after this wins Ctrl+V)
        names = ", ".join(LABELS[n] for n in GROUPS if n in values)
        self.report({'INFO'}, f"Copied from {strip.name}: {names}")
        return {'FINISHED'}


def _bool_props():
    return {name: bpy.props.BoolProperty(name=label, default=on)
            for name, label, on in cfg.PASTE_ATTRIBUTES}


class PLASTRON_OT_attributes_paste(bpy.types.Operator):
    """Paste copied attributes onto the selected clips (choose which)"""
    bl_idname = "plastron.attributes_paste"
    bl_label = "Paste Attributes"
    bl_options = {'REGISTER', 'UNDO'}
    __annotations__ = _bool_props()

    @classmethod
    def poll(cls, context):
        from ...core.views import typing
        return context.scene is not None and context.scene.sequence_editor is not None and not typing(context)

    def invoke(self, context, _event):
        got = paste_picture(context)
        if isinstance(got, str):
            self.report({'WARNING'}, got)
            return {'CANCELLED'}
        if got is not None:
            self.report({'INFO'}, f"Pasted the picture: {got.name}")
            for area in context.screen.areas:
                area.tag_redraw()
            return {'FINISHED'}
        if not _clipboard:
            self.report({'INFO'}, "Nothing to paste: copy a clip (Ctrl+C) or a picture first")
            return {'CANCELLED'}
        if not _targets(context):
            self.report({'INFO'}, "Select the clips to paste onto")
            return {'CANCELLED'}
        for name, on in ticked().items():
            setattr(self, name, on)
        return context.window_manager.invoke_props_dialog(self, title="Paste Attributes", confirm_text="Paste")

    def draw(self, _context):
        layout = self.layout
        layout.label(text=f"From {_clipboard.get('_from', 'the copied clip')}:")
        col = layout.column(align=True)
        for name in GROUPS:
            if name in _clipboard:
                col.prop(self, name)

    def execute(self, context):
        groups = [n for n in GROUPS if n in _clipboard and getattr(self, n)]
        saved = dict(user_settings.get(SETTING) or {})
        saved.update({n: bool(getattr(self, n)) for n in GROUPS if n in _clipboard})
        user_settings.set(SETTING, saved)
        targets = _targets(context)
        if not targets or not groups:
            return {'CANCELLED'}
        n = paste(context.scene, targets, _clipboard, groups)
        self.report({'INFO'}, f"Pasted onto {n} clip{'s' if n != 1 else ''}")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def draw_buttons(layout, context):
    """Copy / Paste... (the Clip panel)."""
    row = layout.row(align=True)
    row.operator("plastron.attributes_copy", text="Copy Attributes", icon='COPYDOWN')
    row.operator("plastron.attributes_paste", text="Paste...", icon='PASTEDOWN')


classes = (PLASTRON_OT_attributes_copy, PLASTRON_OT_attributes_paste)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
