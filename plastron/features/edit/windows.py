"""Info windows (Ollie: "an easy way to add little info windows using this
UI ... a nested timeline feature: clips that auto-crop to the UI").

A window is a clip whose inside is its own little timeline (a Blender
scene of its own, shown by a scene clip). Inside: a Content track (clips
you put there fill the window's opening, cropped to fit), its sound track,
and a locked Frame track on top holding the window's picture (a PNG whose
middle is see-through; config/edit.py WINDOW_* and the window styles
folders). Edit Inside / Back (Tab) switch the timeline and preview between
the main timeline and the window's own. Back on the main timeline the
window clip's length follows what's inside (ripple tracks make room).
"""

import os

import bpy
import numpy as np

from ...config import edit as cfg
from ...timeline import clips, events, ripple, tracks
from . import media

OF = "plastron_window_of"          # on a window's scene: the scene it's shown in
STYLE = "plastron_window_style"    # ...and its frame picture
WINDOW = "plastron_window"         # on the clip showing a window

FRAME_TRACK = "Frame"
CONTENT_TRACK = "Content"


# --- Styles (the frame pictures) -----------------------------------------------------

def style_folders():
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "presets", "windows")
    user = os.path.join(bpy.utils.user_resource('CONFIG'), cfg.WINDOW_USER_FOLDER)
    os.makedirs(user, exist_ok=True)
    return [here, user]


def styles():
    """[(name, path)] of every window style (built-in, then your own)."""
    out = []
    for folder in style_folders():
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith((".png", ".webp", ".tga", ".tif", ".tiff")):
                out.append((os.path.splitext(f)[0], os.path.join(folder, f)))
    return out


_openings = {}      # path -> (mtime, (x0, y0, x1, y1) fractions from the bottom-left, (w, h))


def opening(path):
    """Where a frame picture is see-through: the rectangle around its middle
    (fractions of its size, bottom-left origin) and its pixel size."""
    mtime = os.path.getmtime(path)
    cached = _openings.get(path)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    clear = px.reshape(h, w, 4)[..., 3] < cfg.WINDOW_CLEAR_ALPHA
    cy, cx = h // 2, w // 2
    row, col = clear[cy], clear[:, cx]

    def run(line, mid):
        a = b = mid
        while a > 0 and line[a - 1]:
            a -= 1
        while b < len(line) - 1 and line[b + 1]:
            b += 1
        return a, b + 1

    x0, x1 = run(row, cx)
    y0, y1 = run(col, cy)
    rect = (x0 / w, y0 / h, x1 / w, y1 / h)
    _openings[path] = (mtime, rect, (w, h))
    return rect, (w, h)


# --- Window scenes ----------------------------------------------------------------------

def is_window_scene(scene):
    return scene is not None and bool(scene.get(OF))


def is_window_clip(strip):
    return strip is not None and strip.type == 'SCENE' and bool(strip.get(WINDOW))


def main_scene(scene):
    while is_window_scene(scene):
        parent = bpy.data.scenes.get(scene[OF])
        if parent is None:
            break
        scene = parent
    return scene


def _track_named(scene, name):
    return next((t for t in tracks.all_tracks(scene) if tracks.name(scene, t) == name), None)


def frame_clip(ws):
    track = _track_named(ws, FRAME_TRACK)
    if track is None:
        return None
    on = clips.on_channel(ws, tracks.channel_of(ws, track))
    return on[0] if on else None


def opening_rect(ws):
    """The window's opening in its scene's picture: (x0, y0, x1, y1) in the
    preview's pixels ((0, 0) = the middle)."""
    path = bpy.path.abspath(ws.get(STYLE, ""))
    (fx0, fy0, fx1, fy1), (iw, ih) = opening(path)
    r = ws.render
    s = min(r.resolution_x / iw, r.resolution_y / ih)          # the picture fits the frame
    w, h = iw * s, ih * s
    return (-w / 2 + fx0 * w, -h / 2 + fy0 * h, -w / 2 + fx1 * w, -h / 2 + fy1 * h)


def window_size(ws):
    """The size of the window's frame picture in its scene's picture (pixels);
    the scene's whole picture if it isn't a window."""
    r = ws.render
    path = bpy.path.abspath(ws.get(STYLE, ""))
    if not is_window_scene(ws) or not os.path.exists(path):
        return r.resolution_x, r.resolution_y
    _rect, (iw, ih) = opening(path)
    s = min(r.resolution_x / iw, r.resolution_y / ih)
    return iw * s, ih * s


def fit_inside(ws, strip):
    """Fill the window's opening with strip, cropping what spills over."""
    if strip.type == 'SOUND' or not getattr(strip, "elements", None):
        return
    e = strip.elements[0]
    sw, sh = e.orig_width, e.orig_height
    if not sw or not sh:
        return
    x0, y0, x1, y1 = opening_rect(ws)
    rw, rh = x1 - x0, y1 - y0
    c = max(rw / sw, rh / sh)                    # cover the opening
    crop_x = max(0, int((sw - rw / c) / 2))
    crop_y = max(0, int((sh - rh / c) / 2))
    strip.crop.min_x = strip.crop.max_x = crop_x
    strip.crop.min_y = strip.crop.max_y = crop_y
    t = strip.transform
    t.scale_x = t.scale_y = c
    t.offset_x, t.offset_y = (x0 + x1) / 2, (y0 + y1) / 2
    t.rotation = 0.0


def new_window(scene, style_path, frame=None, track=None):
    """Make a window (its own little timeline) and put it on the main timeline
    at frame (default: the playhead). Returns its clip, or a message."""
    scene = main_scene(scene)
    frame = scene.frame_current if frame is None else int(frame)
    target = track if track is not None and track.kind == 'VIDEO' else None
    target = target if target is not None and not media._holds(scene, target, _is_panel) else media.footage_track(scene)
    if tracks.is_locked(scene, target):
        return "That track is locked"
    n = 1 + sum(1 for s in bpy.data.scenes if is_window_scene(s))
    name = f"{cfg.WINDOW_NAME} {n}"
    ws = bpy.data.scenes.new(name)
    r, wr = scene.render, ws.render
    wr.resolution_x, wr.resolution_y = r.resolution_x, r.resolution_y
    wr.resolution_percentage = r.resolution_percentage
    wr.fps, wr.fps_base = r.fps, r.fps_base
    ws[OF] = scene.name
    ws[STYLE] = style_path
    ws.sequence_editor_create()
    fps = r.fps / r.fps_base
    length = max(1, round(cfg.WINDOW_SECONDS * fps))
    ws.frame_start, ws.frame_end = 1, length
    tracks.add(ws, 'AUDIO', cfg.VIDEO_SOUND_TRACK)
    content = tracks.add(ws, 'VIDEO', CONTENT_TRACK, ripple=True)
    frame_track = tracks.add(ws, 'VIDEO', FRAME_TRACK)
    tracks.set_active(ws, content)
    sed_w = ws.sequence_editor
    pic = sed_w.strips.new_image(os.path.splitext(os.path.basename(style_path))[0], style_path,
                                 tracks.channel_of(ws, frame_track), 1, fit_method='FIT')
    pic.right_handle = 1 + length
    pic[media.MARK] = True
    sed_w.channels[tracks.channel_of(ws, frame_track)].lock = True     # (the frame isn't edited)

    sed = clips.editor(scene)
    spare = media._spare(scene)
    strip = sed.strips.new_scene(name, ws, spare, frame)
    strip.scene_input = 'SEQUENCER'
    strip.right_handle = frame + length
    strip[WINDOW] = True
    strip[media.MARK] = True
    strip.transform.scale_x = strip.transform.scale_y = cfg.WINDOW_SCALE
    if not media._fit(scene, strip, tracks.channel_of(scene, target), frame):
        sed.strips.remove(strip)
        bpy.data.scenes.remove(ws)
        return "No room here: turn on ripple for this track, or make a gap"
    for s in clips.all_clips(scene):
        s.select = s == strip
    sed.active_strip = strip
    events.clips_changed(scene)
    return strip


def _is_panel(strip):
    from ..storyboard.panels import is_panel
    return is_panel(strip)


def _frame_follows(scene, **_info):
    """In a window: the frame lasts as long as what's in it."""
    if not is_window_scene(scene):
        return
    pic = frame_clip(scene)
    if pic is None:
        return
    others = [s for s in clips.top_clips(scene) if s != pic]
    if not others:
        return
    end = max(clips.end(s) for s in others)
    start = min(clips.start(s) for s in others + [pic])
    if (clips.start(pic), clips.end(pic)) != (start, end):
        clips._set(pic, start, end)


def _fit_placed(scene, strips=(), **_info):
    content = _track_named(scene, CONTENT_TRACK) if is_window_scene(scene) else None
    if content is not None:
        for strip in strips:
            if strip.channel == tracks.channel_of(scene, content):
                fit_inside(scene, strip)


# --- Going inside and back --------------------------------------------------------------

def open_window(context, strip):
    """The timeline and preview show the window's own timeline."""
    ws = strip.scene
    main = context.scene
    window = context.window
    ws.frame_current = int(ws.frame_start + max(0, main.frame_current - int(strip.content_start)))
    window.scene = ws
    window.workspace.sequencer_scene = ws
    _redraw(window)


def close_window(context):
    """Back to the timeline the window is in; its clip's length follows the inside."""
    window = context.window
    ws = window.scene
    if not is_window_scene(ws):
        return False
    main = bpy.data.scenes.get(ws[OF])
    if main is None:
        return False
    window.scene = main
    window.workspace.sequencer_scene = main
    strip = next((s for s in clips.all_clips(main) if s.type == 'SCENE' and s.scene == ws), None)
    if strip is not None:
        resize_to_inside(main, strip)
    _redraw(window)
    return True


def resize_to_inside(scene, strip):
    ws = strip.scene
    inside = ws.frame_end - ws.frame_start + 1
    want = int(strip.content_start) + inside          # (content_start = the inside's first frame)
    if clips.end(strip) != want:
        ripple.trim(scene, strip, 'RIGHT', want)


def _redraw(window):
    for area in window.screen.areas:
        area.tag_redraw()


def _back_on_load(_scene):
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        if is_window_scene(window.scene):
            main = main_scene(window.scene)
            window.scene = main
            window.workspace.sequencer_scene = main


# --- Operators / UI ----------------------------------------------------------------------

def _style_items(_self, _context):
    return [(path, name, f"A {name} window") for name, path in styles()] or [("", "(none)", "")]


class PLASTRON_OT_window_add(bpy.types.Operator):
    """Add an info window at the playhead: put clips inside it and they fill its opening"""
    bl_idname = "plastron.window_add"
    bl_label = "Add Window"
    bl_options = {'REGISTER', 'UNDO'}
    style: bpy.props.EnumProperty(name="Style", items=_style_items)

    def execute(self, context):
        if not self.style or not os.path.exists(self.style):
            self.report({'WARNING'}, "No window style: put a PNG in the window styles folder")
            return {'CANCELLED'}
        result = new_window(context.scene, self.style, track=tracks.active(context.scene))
        if isinstance(result, str):
            self.report({'WARNING'}, result)
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_window_toggle(bpy.types.Operator):
    """Edit inside the selected window (its own timeline), or go back out"""
    bl_idname = "plastron.window_toggle"
    bl_label = "Edit Inside / Back"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if is_window_scene(context.scene):
            close_window(context)
            return {'FINISHED'}
        sed = context.scene.sequence_editor
        strip = sed.active_strip if sed else None
        if not is_window_clip(strip) or strip.scene is None:
            self.report({'INFO'}, "Select a window clip to edit inside it")
            return {'CANCELLED'}
        open_window(context, strip)
        return {'FINISHED'}


class PLASTRON_OT_window_styles_folder(bpy.types.Operator):
    """Open the folder for your own window styles (PNG frames with a see-through middle)"""
    bl_idname = "plastron.window_styles_folder"
    bl_label = "Your Window Styles..."

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=style_folders()[1])
        return {'FINISHED'}


class PLASTRON_MT_window_add(bpy.types.Menu):
    bl_label = "Add Window"

    def draw(self, context):
        layout = self.layout
        for name, path in styles():
            layout.operator("plastron.window_add", text=name, icon='WINDOW').style = path
        layout.separator()
        layout.operator("plastron.window_styles_folder", icon='FILE_FOLDER')


def draw_inside_banner(layout, context):
    """Header: inside a window, where you are and the way back."""
    scene = context.scene
    if not is_window_scene(scene):
        return False
    row = layout.row(align=True)
    row.alert = True
    row.operator("plastron.window_toggle", text=f"◀ Back   (inside {scene.name})", icon='LOOP_BACK')
    return True


def draw_preview_button(layout, context):
    if not is_window_scene(context.scene):
        layout.menu("PLASTRON_MT_window_add", text="Window", icon='WINDOW')


classes = (PLASTRON_OT_window_add, PLASTRON_OT_window_toggle, PLASTRON_OT_window_styles_folder,
           PLASTRON_MT_window_add)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    events.listen("clips_changed", _frame_follows)
    events.listen("media_placed", _fit_placed)
    from ...core import handlers
    from ...timeline import header
    handlers.on_load(_back_on_load, first=True)     # (before anything uses the scene)
    from ...core import modes
    modes.before_switch.append(_out_before_switch)
    header.add_prefix(draw_inside_banner)
    header.add_preview_section(draw_preview_button)
    media.FOOTAGE_TYPES.add('SCENE')               # (a window never shares a track with panels)


def _out_before_switch(context):
    if context.window is not None and is_window_scene(context.window.scene):
        close_window(context)


def unregister():
    from ...core import modes
    if _out_before_switch in modes.before_switch:
        modes.before_switch.remove(_out_before_switch)
    media.FOOTAGE_TYPES.discard('SCENE')
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
