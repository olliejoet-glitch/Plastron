"""Temp sound drops (the brief's "a small sound effects bin for dragging in
placeholder sounds, tagged so they're easy to find and replace later").

Timeline header: Sounds. The bin is a folder in Plastron's settings
("plastron_sounds/"; subfolders are tags, e.g. "doors/creak.wav" is tagged
"doors"). Search by name or tag; + puts the sound at the playhead on the
"Temp Sounds" track (made if missing). Temp sounds are pink, named
"TEMP ...", and marked, so Select Temp Sounds finds them all later.
Add Sounds... copies files into the bin.
"""

import os
import shutil

import bpy
from bpy_extras.io_utils import ImportHelper

from ...config import review as cfg
from ...timeline import clips, events, tracks


def folder():
    path = os.path.join(bpy.utils.user_resource('CONFIG'), "plastron_sounds")
    os.makedirs(path, exist_ok=True)
    return path


def library():
    """[(name, tag, path)] of every sound in the bin, sorted."""
    root = folder()
    out = []
    for here, _dirs, files in os.walk(root):
        tag = os.path.relpath(here, root)
        tag = "" if tag == "." else tag.replace(os.sep, " / ")
        for f in files:
            if f.lower().endswith(cfg.SOUND_TYPES):
                out.append((os.path.splitext(f)[0], tag, os.path.join(here, f)))
    return sorted(out, key=lambda s: (s[1].lower(), s[0].lower()))


def matching(query):
    q = query.strip().lower()
    return [s for s in library() if not q or q in s[0].lower() or q in s[1].lower()]


def temp_track(scene):
    for track in tracks.all_tracks(scene):
        if track.kind == 'AUDIO' and tracks.name(scene, track) == cfg.TEMP_SOUND_TRACK:
            return track
    return tracks.add(scene, 'AUDIO', track_name=cfg.TEMP_SOUND_TRACK)


def is_temp(strip):
    return bool(strip.get("plastron_temp_sound"))


def drop(scene, path, frame=None):
    """Put a temp sound on the Temp Sounds track at frame (or the next free spot)."""
    track = temp_track(scene)
    channel = tracks.channel_of(scene, track)
    frame = scene.frame_current if frame is None else frame
    blocking = clips.at(scene, channel, frame)
    while blocking is not None:                      # after whatever is already there
        frame = clips.end(blocking)
        blocking = clips.at(scene, channel, frame)
    name = cfg.TEMP_SOUND_PREFIX + os.path.splitext(os.path.basename(path))[0]
    # Made on a free channel first (a clip overlapping another gets bumped by
    # Blender), cut to the gap before the next sound, then moved onto the track.
    sed = clips.editor(scene)
    spare = max([s.channel for s in sed.strips_all] + [channel]) + 1
    strip = sed.strips.new_sound(name, path, spare, frame)
    nxt = clips.next_after(scene, channel, frame + 1)
    if nxt is not None and clips.start(nxt) < clips.end(strip):
        strip.right_handle = clips.start(nxt)        # don't run into the next sound
    strip.channel = channel
    strip.color_tag = cfg.TEMP_SOUND_COLOR
    strip["plastron_temp_sound"] = True
    events.clips_changed(scene)
    return strip


class PLASTRON_OT_sound_drop(bpy.types.Operator):
    """Put this sound at the playhead (on the Temp Sounds track)"""
    bl_idname = "plastron.sound_drop"
    bl_label = "Drop Temp Sound"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty()

    def execute(self, context):
        if not os.path.exists(self.filepath):
            self.report({'WARNING'}, "That sound isn't in the bin any more")
            return {'CANCELLED'}
        drop(context.scene, self.filepath)
        return {'FINISHED'}


class PLASTRON_OT_sounds_add(bpy.types.Operator, ImportHelper):
    """Copy sound files into the temp sounds bin"""
    bl_idname = "plastron.sounds_add"
    bl_label = "Add Sounds"
    filter_glob: bpy.props.StringProperty(default=";".join("*" + t for t in cfg.SOUND_TYPES),
                                          options={'HIDDEN'})
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN'})
    directory: bpy.props.StringProperty(subtype='DIR_PATH', options={'HIDDEN'})
    tag: bpy.props.StringProperty(name="Tag", description="Put them in this tag (a folder in the bin)")

    def execute(self, context):
        names = [f.name for f in self.files] or [os.path.basename(self.filepath)]
        target = os.path.join(folder(), bpy.path.clean_name(self.tag)) if self.tag.strip() else folder()
        os.makedirs(target, exist_ok=True)
        added = 0
        for name in names:
            src = os.path.join(self.directory or os.path.dirname(self.filepath), name)
            if os.path.isfile(src) and name.lower().endswith(cfg.SOUND_TYPES):
                shutil.copy2(src, os.path.join(target, name))
                added += 1
        self.report({'INFO'}, f"{added} sound{'s' if added != 1 else ''} added to the bin")
        return {'FINISHED'}


class PLASTRON_OT_sounds_select_temp(bpy.types.Operator):
    """Select every temp sound on the timeline (to find and replace them)"""
    bl_idname = "plastron.sounds_select_temp"
    bl_label = "Select Temp Sounds"

    def execute(self, context):
        n = 0
        for strip in clips.all_clips(context.scene):
            strip.select = is_temp(strip)
            n += strip.select
        self.report({'INFO'}, f"{n} temp sound{'s' if n != 1 else ''}")
        return {'FINISHED'}


class PLASTRON_OT_sounds_open_folder(bpy.types.Operator):
    """Open the temp sounds folder"""
    bl_idname = "plastron.sounds_open_folder"
    bl_label = "Open Sounds Folder"

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=folder())
        return {'FINISHED'}


class PLASTRON_PT_sounds(bpy.types.Panel):
    """Temp sounds: placeholder effects to drop in"""
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'HEADER'
    bl_label = "Temp Sounds"
    bl_ui_units_x = 14

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        layout.prop(wm, "plastron_sound_search", text="", icon='VIEWZOOM')
        found = matching(wm.plastron_sound_search)
        col = layout.column(align=True)
        if not found:
            col.label(text="No sounds yet: Add Sounds..." if not library() else "Nothing matches")
        for name, tag, path in found[:40]:
            row = col.row(align=True)
            row.label(text=f"{name}" + (f"  ({tag})" if tag else ""), icon='SOUND')
            row.operator("plastron.sound_drop", text="", icon='ADD').filepath = path
        layout.separator()
        row = layout.row(align=True)
        row.operator("plastron.sounds_add", text="Add Sounds...", icon='IMPORT')
        row.operator("plastron.sounds_open_folder", text="", icon='FILE_FOLDER')
        layout.operator("plastron.sounds_select_temp", icon='RESTRICT_SELECT_OFF')


def draw_header(layout, context):
    layout.popover("PLASTRON_PT_sounds", text="Sounds", icon='SOUND')


classes = (PLASTRON_OT_sound_drop, PLASTRON_OT_sounds_add, PLASTRON_OT_sounds_select_temp,
           PLASTRON_OT_sounds_open_folder, PLASTRON_PT_sounds)


def register():
    bpy.types.WindowManager.plastron_sound_search = bpy.props.StringProperty(
        name="Search", description="Find a sound by name or tag")
    for cls in classes:
        bpy.utils.register_class(cls)
    from ...timeline import header
    header.add_section(draw_header)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.plastron_sound_search
