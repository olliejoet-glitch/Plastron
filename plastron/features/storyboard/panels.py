"""Storyboard panels: each panel is an image clip on a video track (showing
its cached image) linked to its own drawing (a grease pencil datablock).

strip.plastron_panel.drawing -> the panel's drawing
strip.plastron_panel.uid     -> names its cache image
"""

import os
import uuid

import bpy

from ...config import project_defaults as defaults, timeline as timeline_cfg
from ...core import handlers
from ...timeline import clips, events, ripple, tracks
from . import panel_cache

INK = "Ink"
# Drawings hold one keyframe far in the past, so they show at any frame the
# panel clip is placed at (panel timing lives in the clip, not in keyframes).
HOLD_FRAME = -100000


class PLASTRON_PG_panel(bpy.types.PropertyGroup):
    uid: bpy.props.StringProperty()
    drawing: bpy.props.PointerProperty(type=bpy.types.GreasePencil)


def is_panel(strip):
    return strip.type == 'IMAGE' and bool(strip.plastron_panel.uid)


def all_panels(scene):
    return [s for s in clips.top_clips(scene) if is_panel(s)]


def ink():
    mat = bpy.data.materials.get(INK)
    if mat is None:
        mat = bpy.data.materials.new(INK)
        bpy.data.materials.create_gpencil_data(mat)
        mat.grease_pencil.color = defaults.STROKE_COLOR
    return mat


def new_drawing(name):
    gp = bpy.data.grease_pencils.new(name)
    layer = gp.layers.new("Layer")
    layer.frames.new(HOLD_FRAME)
    gp.materials.append(ink())
    return gp


def _next_number(scene):
    numbers = [0]
    for s in all_panels(scene):
        tail = s.name.rsplit(" ", 1)[-1]
        if tail.isdigit():
            numbers.append(int(tail))
    return max(numbers) + 1


def create(scene, channel, start, length):
    """Make a panel clip on channel covering [start, start + length)."""
    uid = uuid.uuid4().hex[:10]
    folder = panel_cache.cache_dir()
    path = os.path.join(folder, panel_cache.file_name(uid))
    panel_cache.write_placeholder(path)
    name = f"Panel {_next_number(scene)}"
    strip = clips.editor(scene).strips.new_image(name, path, channel, start, fit_method='FIT')
    strip.right_handle = start + length
    strip.plastron_panel.uid = uid
    strip.plastron_panel.drawing = new_drawing(name)
    return strip


def new_at_playhead(scene):
    """New panel at the playhead on the active video track. Returns the strip
    or an error message."""
    track = tracks.active(scene)
    if track is None or track.kind != 'VIDEO':
        videos = tracks.video_tracks(scene)
        track = videos[-1] if videos else None
    if track is None:
        return "There's no video track"
    if tracks.is_locked(scene, track):
        return "That track is locked"
    channel = tracks.channel_of(scene, track)
    length = max(1, round(timeline_cfg.NEW_PANEL_SECONDS * scene.render.fps / scene.render.fps_base))
    room = ripple.make_room(scene, channel, scene.frame_current, length)
    if room is None:
        return "No room here: turn on ripple for this track, or make a gap"
    strip = create(scene, channel, *room)
    for s in clips.all_clips(scene):
        s.select = False
    strip.select = True
    scene.sequence_editor.active_strip = strip
    scene.frame_current = clips.start(strip)
    events.clips_changed(scene)
    return strip


class PLASTRON_OT_panel_new(bpy.types.Operator):
    """Add a new panel at the playhead"""
    bl_idname = "plastron.panel_new"
    bl_label = "New Panel"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        result = new_at_playhead(context.scene)
        if isinstance(result, str):
            self.report({'WARNING'}, result)
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Reacting to timeline edits ---------------------------------------------

def _on_split(scene, original, new):
    """The right half of a split panel gets its own copy of the drawing."""
    if not is_panel(original):
        return
    uid = uuid.uuid4().hex[:10]
    panel_cache.copy_for(original.plastron_panel.uid, uid)
    new.plastron_panel.uid = uid
    panel_cache.point_at(new, panel_cache.cache_dir(), uid)
    drawing = original.plastron_panel.drawing
    if drawing:
        copy = drawing.copy()
        copy.name = new.name
        new.plastron_panel.drawing = copy


def _on_project_created(scene):
    if defaults.STARTER_PANEL and not all_panels(scene):
        new_at_playhead(scene)


def ensure_cache(scene, folder=None):
    """Every panel clip shows its image from the project's cache folder."""
    folder = folder or panel_cache.cache_dir()
    for strip in all_panels(scene):
        panel_cache.point_at(strip, folder, strip.plastron_panel.uid)


def _on_load(scene):
    if scene is not None:
        ensure_cache(scene)


def _save_pre(filepath, *_args):
    from ...core import autosave
    if autosave.saving:      # autosave copies keep pointing at the real cache
        return
    for scene in bpy.data.scenes:
        if hasattr(scene, "plastron_timeline"):
            ensure_cache(scene, panel_cache.cache_dir(filepath))


classes = (PLASTRON_PG_panel, PLASTRON_OT_panel_new)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Strip.plastron_panel = bpy.props.PointerProperty(type=PLASTRON_PG_panel)
    events.listen("clip_split", _on_split)
    events.listen("project_created", _on_project_created)
    handlers.on_load(_on_load)
    handlers.add("save_pre", _save_pre)


def unregister():
    del bpy.types.Strip.plastron_panel
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
