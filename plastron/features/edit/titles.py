"""Titles: text over the picture (Ollie: "I need an add text tool", for the
video: titles, labels, lower thirds).

Text in the preview header (or T over the timeline / preview) adds a title
at the playhead on a "Titles" track (made on top of the video tracks if
missing), TITLE_SECONDS long, and starts typing in it right away: the words
are typed in the picture itself (Blender's text editing in the preview:
arrows, Home / End, Shift to select, Ctrl+A / C / V / X, Enter = new line).
Tab or Esc finishes. Editing the words is only ever done in the picture
(Ollie: "I really don't want text editing to be in side menus, just let me
edit the text directly in the text box"): click a title to select it, click
its text again to type there (the caret goes where you clicked); double-click
or Tab work too. While typing, Plastron's own preview keys stand aside
(core/views.typing).

A selected title has a box in the preview: drag inside to move it (a click
without moving types instead), a corner to size it (the font grows /
shrinks), a side to set where it wraps. Its look (font, size, colour,
outline, shadow, box behind it, alignment) is in the Clip panel, with
styles (presets/titles/: Big Title, Lower Third, Caption, + your own).
Titles are clips like any other: fades, cuts, ripple, copy / paste
attributes (Text Style). Blender's own Text strip, so it renders as is.
"""

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import edit as cfg
from ...core import presets
from ...core.theme import _color
from ...core.views import is_preview, typing
from ...timeline import clips, events, tracks

MARK = "plastron_title"
KIND = "titles"
STYLE = ("color", "use_bold", "use_italic", "use_outline", "outline_color", "outline_width",
         "use_shadow", "shadow_color", "use_box", "box_color", "box_margin", "alignment_x",
         "anchor_x", "anchor_y", "location", "wrap_width")


_fonts = {}        # font file -> blf id (measuring a title in its own font)


def _font_path(strip):
    """The file of the font the title renders with."""
    import os
    font = strip.font
    if font is not None and font.filepath and not font.filepath.startswith("<"):
        return bpy.path.abspath(font.filepath)
    name = "DejaVuSansMono.woff2" if font is None else cfg.TITLE_FONT
    return os.path.join(bpy.utils.system_resource('DATAFILES'), "fonts", name)


def _blf_id(strip):
    path = _font_path(strip)
    if path not in _fonts:
        try:
            _fonts[path] = blf.load(path)
        except Exception:
            _fonts[path] = 0
        if _fonts[path] < 0:
            _fonts[path] = 0
    return _fonts[path]


def default_font():
    """Blender's Inter (the sans its interface uses), for new titles."""
    import os
    path = os.path.join(bpy.utils.system_resource('DATAFILES'), "fonts", cfg.TITLE_FONT)
    if not os.path.exists(path):
        return None
    try:
        return bpy.data.fonts.load(path, check_existing=True)
    except RuntimeError:
        return None


def is_title(strip):
    return strip is not None and strip.type == 'TEXT' and not strip.get("plastron_line")


def active_title(context):
    sed = context.scene.sequence_editor if context.scene else None
    strip = sed.active_strip if sed else None
    return strip if is_title(strip) and strip.select else None


def title_track(scene):
    for track in tracks.video_tracks(scene):
        if tracks.name(scene, track) == cfg.TITLE_TRACK:
            return track
    return tracks.add(scene, 'VIDEO', track_name=cfg.TITLE_TRACK)


# --- Style -------------------------------------------------------------------------------------

def _height(scene):
    return scene.render.resolution_y


def style_of(scene, strip):
    """A title's look as a plain dict (size in % of the frame's height)."""
    out = {"size": round(strip.font_size / _height(scene) * 100, 3)}
    for key in STYLE:
        value = getattr(strip, key)
        out[key] = list(value) if hasattr(value, "__len__") and not isinstance(value, str) else value
    return out


def apply_style(scene, strip, style):
    for key, value in style.items():
        if key == "size":
            strip.font_size = max(1.0, value / 100 * _height(scene))
        elif key in STYLE and hasattr(strip, key):
            try:
                setattr(strip, key, value)
            except (TypeError, ValueError) as err:
                print(f"Plastron titles: style {key}: {err}")


def _preset_apply(context, preset):
    scene = context.scene
    style = {k: v for k, v in preset.items() if k not in ("name", "order", "built_in", "file")}
    for s in [s for s in clips.top_clips(scene) if s.select and is_title(s)]:
        apply_style(scene, s, style)


def _preset_capture(context):
    strip = active_title(context)
    return style_of(context.scene, strip) if strip else {}


# --- Adding -------------------------------------------------------------------------------------

def add(scene, frame=None, text=None):
    """A new title at frame (the playhead) on the Titles track. Returns it,
    or a message if there's no room."""
    from .media import _fit, _spare
    frame = scene.frame_current if frame is None else int(frame)
    track = title_track(scene)
    if tracks.is_locked(scene, track):
        return "The Titles track is locked"
    fps = scene.render.fps / scene.render.fps_base
    length = max(1, round(cfg.TITLE_SECONDS * fps))
    sed = clips.editor(scene)
    strip = sed.strips.new_effect(name=text or cfg.TITLE_TEXT, type='TEXT', channel=_spare(scene),
                                  frame_start=frame, length=length)
    strip.text = text or cfg.TITLE_TEXT
    strip.blend_type = 'ALPHA_OVER'
    font = default_font()
    if font is not None:
        strip.font = font
    strip[MARK] = True
    look = presets.get(KIND, cfg.TITLE_STYLE)
    if look:
        apply_style(scene, strip, {k: v for k, v in look.items() if k not in ("name", "order", "built_in", "file")})
    with events.batch():
        if not _fit(scene, strip, tracks.channel_of(scene, track), frame):
            from ...timeline import ripple
            ripple.remove(scene, strip)
            return "No room for a title here: turn on ripple for the Titles track, or make a gap"
        events.clips_changed(scene)
    return strip


def _preview_area(context):
    wm = bpy.context.window_manager
    window = context.window or bpy.context.window or (wm.windows[0] if wm and wm.windows else None)   # (timers: no window)
    for area in (window.screen.areas if window else []):
        if area.type == 'SEQUENCE_EDITOR' and is_preview(area.spaces.active):
            region = next((r for r in area.regions if r.type == 'PREVIEW'), None)
            if region is not None:
                return window, area, region
    return None


def start_typing(context, strip, select_all=False, caret=None):
    """Type in the title in the preview (Blender's text editing). False if
    there's no preview to type in."""
    where = _preview_area(context)
    if where is None:
        return False
    window, area, region = where
    scene = context.scene
    for s in clips.top_clips(scene):
        s.select = s == strip
    scene.sequence_editor.active_strip = strip
    if not (clips.start(strip) <= scene.frame_current < clips.end(strip)):
        scene.frame_current = clips.start(strip)
    area.tag_redraw()
    name = strip.name
    tries = [0]

    def go():
        # (Blender lets a title be typed in only once the preview has drawn
        # it: a brand-new one waits a moment.)
        where = _preview_area(bpy.context)
        sed = bpy.context.scene.sequence_editor
        title = sed.strips_all.get(name) if sed else None
        if where is None or title is None:
            return None
        window, area, region = where
        with bpy.context.temp_override(window=window, area=area, region=region):
            if typing(bpy.context):
                return None
            if bpy.ops.sequencer.text_edit_mode_toggle.poll():
                bpy.ops.sequencer.text_edit_mode_toggle()
                if select_all and typing(bpy.context):
                    bpy.ops.sequencer.text_select_all()
                elif caret is not None and typing(bpy.context):
                    place_caret(caret)                  # (the caret where you clicked)
                area.tag_redraw()
                return None
        tries[0] += 1
        area.tag_redraw()
        return 0.05 if tries[0] < 40 else None

    if go() is not None:
        bpy.app.timers.register(go, first_interval=0.05)
    return True


def stop_typing(context):
    where = _preview_area(context)
    if where is None:
        return False
    window, area, region = where
    with bpy.context.temp_override(window=window, area=area, region=region):
        if typing(bpy.context):
            bpy.ops.sequencer.text_edit_mode_toggle()
            area.tag_redraw()
            return True
    return False


class PLASTRON_OT_title_add(bpy.types.Operator):
    """Add a title (text over the picture) at the playhead, and type it"""
    bl_idname = "plastron.title_add"
    bl_label = "Add Text"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.sequence_editor is not None and not typing(context)

    def execute(self, context):
        got = add(context.scene)
        if isinstance(got, str):
            self.report({'WARNING'}, got)
            return {'CANCELLED'}
        if not start_typing(context, got, select_all=True):
            self.report({'INFO'}, "Title added: open a video preview to type its words")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_OT_title_type(bpy.types.Operator):
    """Type in the selected title in the preview (again: finish typing)"""
    bl_idname = "plastron.title_type"
    bl_label = "Type in Title"
    bl_options = {'REGISTER', 'UNDO'}

    finish: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return typing(context) or active_title(context) is not None

    def execute(self, context):
        if typing(context) or self.finish:
            return {'FINISHED'} if stop_typing(context) else {'CANCELLED'}
        strip = active_title(context)
        if strip is None or not start_typing(context, strip):
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_title_finish(bpy.types.Operator):
    """Finish typing (Esc)"""
    bl_idname = "plastron.title_finish"
    bl_label = "Finish Typing"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return typing(context)

    def execute(self, context):
        return {'FINISHED'} if stop_typing(context) else {'CANCELLED'}


# --- The box: move / size a title in the preview ------------------------------------------------

def wrapped_lines(strip, fid, width):
    """The title's lines as Blender wraps them at width (px; 0: no wrap)."""
    out = []
    for para in strip.text.split("\n"):
        if width <= 0:
            out.append(para)
            continue
        line = ""
        for word in para.split(" "):
            test = (line + " " + word) if line else word
            if line and blf.dimensions(fid, test)[0] > width:
                out.append(line)
                line = word
            else:
                line = test
        out.append(line)
    return out or [""]


def rect(scene, strip):
    """(x0, y0, x1, y1) of the title's text box in preview (project pixel)
    coordinates, (0, 0) at the frame's middle: as wide as its wrap width
    (else its words), as tall as its wrapped lines. Measured with the
    title's own font: close enough to grab."""
    r = scene.render
    w_px, h_px = r.resolution_x, r.resolution_y
    size = strip.font_size
    fid = _blf_id(strip)
    blf.size(fid, size)
    bold = 1.06 if strip.use_bold else 1.0                 # (Blender makes bold by thickening)
    wrap = strip.wrap_width * w_px if strip.wrap_width > 0 else 0
    lines = wrapped_lines(strip, fid, wrap / bold if wrap else 0)
    if wrap:
        width = wrap
    else:
        width = max([blf.dimensions(fid, line or " ")[0] for line in lines] + [size * 0.6]) * bold
    height = size * (1.2 * (len(lines) - 1) + 1.0)
    lx = (strip.location[0] - 0.5) * w_px + strip.transform.offset_x
    ly = (strip.location[1] - 0.5) * h_px + strip.transform.offset_y
    x0 = {"LEFT": lx, "CENTER": lx - width / 2, "RIGHT": lx - width}.get(strip.anchor_x, lx - width / 2)
    y0 = {"BOTTOM": ly, "CENTER": ly - height / 2, "TOP": ly - height}.get(strip.anchor_y, ly - height / 2)
    m = strip.box_margin * w_px if strip.use_box else 0
    return x0 - m, y0 - m, x0 + width + m, y0 + height + m


def char_at(scene, strip, vx, vy):
    """Index in strip.text of the letter gap nearest preview point (vx, vy):
    where a click in the picture puts the caret (laid out as rect() does)."""
    size = strip.font_size
    fid = _blf_id(strip)
    blf.size(fid, size)
    bold = 1.06 if strip.use_bold else 1.0
    x0, _y0, x1, y1 = rect(scene, strip)
    m = strip.box_margin * scene.render.resolution_x if strip.use_box else 0
    x0, x1, y1 = x0 + m, x1 - m, y1 - m
    wrap = strip.wrap_width * scene.render.resolution_x if strip.wrap_width > 0 else 0
    # Visual lines with where each starts in the text (a wrap eats its space).
    rows, offset = [], 0
    for para in strip.text.split("\n"):
        pieces = wrapped_lines(_Para(para, strip), fid, wrap / bold if wrap else 0)
        for k, piece in enumerate(pieces):
            rows.append((offset, piece))
            offset += len(piece) + (1 if k < len(pieces) - 1 else 0)
        offset += 1                                    # (the newline)
    row = min(len(rows) - 1, max(0, int((y1 - vy) / (size * 1.2))))
    start, line = rows[row]
    lw = blf.dimensions(fid, line)[0] * bold if line else 0
    lx = {"LEFT": x0, "RIGHT": x1 - lw}.get(strip.alignment_x, (x0 + x1 - lw) / 2)
    best, best_d = 0, abs(vx - lx)
    for i in range(1, len(line) + 1):
        d = abs(vx - (lx + blf.dimensions(fid, line[:i])[0] * bold))
        if d < best_d:
            best, best_d = i, d
    return start + best


class _Para:
    """One paragraph as wrapped_lines reads a title (its .text)."""
    def __init__(self, text, strip):
        self.text = text


def place_caret(index):
    """While typing in a title: the caret to index (Blender's caret keys)."""
    bpy.ops.sequencer.text_cursor_move(type='TEXT_BEGIN')
    for _ in range(index):
        bpy.ops.sequencer.text_cursor_move(type='NEXT_CHARACTER')


def boxed(context):
    """The selected title shown in the picture now (not while typing)."""
    strip = active_title(context)
    scene = context.scene
    if strip is None or strip.mute or typing(context):
        return None
    if not (clips.start(strip) <= scene.frame_current < clips.end(strip)):
        return None
    return strip


def _region_rect(region, r):
    v2d = region.view2d
    x0, y0 = v2d.view_to_region(r[0], r[1], clip=False)
    x1, y1 = v2d.view_to_region(r[2], r[3], clip=False)
    return x0, y0, x1, y1


def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def hit(context, x, y):
    """'MOVE', a corner index (0-3: bottom-left, bottom-right, top-right,
    top-left), 'LEFT' / 'RIGHT' (a side: the box's width = where the words
    wrap), or None."""
    strip = boxed(context)
    if strip is None:
        return None
    x0, y0, x1, y1 = _region_rect(context.region, rect(context.scene, strip))
    grab = _ui(cfg.TITLE_BOX["grab_px"])
    for i, (cx, cy) in enumerate(((x0, y0), (x1, y0), (x1, y1), (x0, y1))):
        if abs(x - cx) <= grab and abs(y - cy) <= grab:
            return i
    if y0 <= y <= y1:
        if abs(x - x0) <= grab:
            return 'LEFT'
        if abs(x - x1) <= grab:
            return 'RIGHT'
    if x0 - grab <= x <= x1 + grab and y0 - grab <= y <= y1 + grab:
        return 'MOVE'
    return None


class PLASTRON_OT_title_box(bpy.types.Operator):
    """Drag the selected title: inside moves it, a corner sizes the text, a side sets where it wraps"""
    bl_idname = "plastron.title_box"
    bl_label = "Move / Size Title"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return context.region is not None and context.region.type == 'PREVIEW' and boxed(context) is not None

    def invoke(self, context, event):
        part = hit(context, event.mouse_region_x, event.mouse_region_y)
        if part is None:
            return {'PASS_THROUGH'}
        self.strip = boxed(context)
        self.part = part
        self.start_view = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        self.loc = tuple(self.strip.location)
        self.size = self.strip.font_size
        self.wrap = self.strip.wrap_width
        r = rect(context.scene, self.strip)
        self.centre = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        self.box = r
        self.last_xy = None
        self.press_xy = (event.mouse_region_x, event.mouse_region_y)
        self.moved = False
        from ... import timeline as _timeline
        _timeline.pause_prefetch(context.scene)       # (frames-ahead off while dragging)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        scene = context.scene
        if event.type == 'MOUSEMOVE':
            if (event.mouse_region_x, event.mouse_region_y) == self.last_xy:
                return {'RUNNING_MODAL'}
            if not self.moved:              # (a pen wobbles: a click is still a click)
                dx = event.mouse_region_x - self.press_xy[0]
                dy = event.mouse_region_y - self.press_xy[1]
                if dx * dx + dy * dy < cfg.TITLE_CLICK_PX ** 2:
                    return {'RUNNING_MODAL'}
                self.moved = True
            self.last_xy = (event.mouse_region_x, event.mouse_region_y)
            vx, vy = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
            r = scene.render
            if self.part in ('LEFT', 'RIGHT'):
                # The box's width = where the words wrap. Anchored in the
                # middle: both sides move; else the anchored side stays.
                x0, _y0, x1, _y1 = self.box
                m = self.strip.box_margin * r.resolution_x if self.strip.use_box else 0
                if self.strip.anchor_x == 'CENTER':
                    width = 2 * abs(vx - (x0 + x1) / 2)
                elif self.strip.anchor_x == 'LEFT':
                    width = vx - x0 if self.part == 'RIGHT' else x1 - vx
                else:
                    width = x1 - vx if self.part == 'LEFT' else vx - x0
                width -= 2 * m
                self.strip.wrap_width = min(1.0, max(0.03, width / r.resolution_x))
            elif self.part == 'MOVE':
                dx = (vx - self.start_view[0]) / r.resolution_x
                dy = (vy - self.start_view[1]) / r.resolution_y
                self.strip.location = (self.loc[0] + dx, self.loc[1] + dy)
            else:
                cx, cy = self.centre
                was = max(1.0, ((self.start_view[0] - cx) ** 2 + (self.start_view[1] - cy) ** 2) ** 0.5)
                now = ((vx - cx) ** 2 + (vy - cy) ** 2) ** 0.5
                self.strip.font_size = max(4.0, self.size * now / was)
            context.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if not self.moved and self.part == 'MOVE':
                vx, vy = context.region.view2d.region_to_view(*self.press_xy)
                start_typing(context, self.strip, caret=char_at(scene, self.strip, vx, vy))   # (type where clicked)
                return {'CANCELLED'}                             # (no undo step: nothing changed)
            return {'FINISHED'} if self.moved else {'CANCELLED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.strip.location = self.loc
            self.strip.font_size = self.size
            self.strip.wrap_width = self.wrap
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class PLASTRON_OT_title_double_click(bpy.types.Operator):
    """Double-click a title in the preview: type in it"""
    bl_idname = "plastron.title_double_click"
    bl_label = "Type in Title"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        strip = boxed(context)
        if strip is None or hit(context, event.mouse_region_x, event.mouse_region_y) is None:
            return {'PASS_THROUGH'}
        vx, vy = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        start_typing(context, strip, caret=char_at(context.scene, strip, vx, vy))
        return {'FINISHED'}


_outline_want = {}        # area pointer -> show Blender's outline (typing in a title there)


def _fix_outline():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            want = _outline_want.pop(area.as_pointer(), None)
            if want is not None and area.type == 'SEQUENCE_EDITOR':
                area.spaces.active.preview_overlay.show_image_outline = want
                area.tag_redraw()
    _outline_want.clear()
    return None


def typing_anywhere():
    """Is a title being typed in any preview? (timeline HOLDERS: each letter
    is a change; the timeline refreshes once when typing ends: Ollie's
    "text editing is slow af" on a big project)."""
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR' and is_preview(area.spaces.active):
                region = next((r for r in area.regions if r.type == 'PREVIEW'), None)
                if region is None:
                    continue
                with bpy.context.temp_override(window=window, area=area, region=region):
                    if typing(bpy.context):
                        return True
    return False


def _sync_outline(context):
    """Blender draws its text cursor (and the box being typed in) only with
    its outline of selected clips on, which Plastron keeps off (it lagged
    behind titles being dragged): on while typing, off again after (Ollie:
    "there's no cursor suggesting any editing is going on")."""
    want = typing(context)
    if want:
        from ... import timeline as _timeline
        _timeline.pause_prefetch(context.scene)    # (frames-ahead off while typing; back on after)
    if context.space_data.preview_overlay.show_image_outline != want:
        _outline_want[context.area.as_pointer()] = want
        if not bpy.app.timers.is_registered(_fix_outline):
            bpy.app.timers.register(_fix_outline, first_interval=0.0)    # (not from inside a draw)


def draw():
    context = bpy.context
    if not is_preview(context.space_data):
        return
    _sync_outline(context)
    strip = boxed(context)
    if strip is None:
        return
    x0, y0, x1, y1 = _region_rect(context.region, rect(context.scene, strip))
    look = cfg.TITLE_BOX
    rgb = _color(look["color"])[:3]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.uniform_float("color", (*rgb, look["alpha"]))
    batch_for_shader(shader, 'LINE_LOOP', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(shader)
    s = _ui(look["handle_px"]) / 2
    tris = []
    for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        tris += [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]
    my = (y0 + y1) / 2                                  # side handles: drag to set where the words wrap
    h2 = min(s * 3, (y1 - y0) / 2)
    for cx in (x0, x1):
        tris += [(cx - s * 0.6, my - h2), (cx + s * 0.6, my - h2), (cx + s * 0.6, my + h2),
                 (cx - s * 0.6, my - h2), (cx + s * 0.6, my + h2), (cx - s * 0.6, my + h2)]
    batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    gpu.state.blend_set('NONE')


# --- Panel / header ----------------------------------------------------------------------------

class PLASTRON_MT_title_styles(bpy.types.Menu):
    bl_idname = "PLASTRON_MT_title_styles"
    bl_label = "Title Styles"

    def draw(self, _context):
        presets.draw_menu(self.layout, KIND)


FONTS_FOLDER = "plastron_fonts"     # in Plastron's settings folder: fonts you've loaded


def fonts_folder():
    import os
    return os.path.join(bpy.utils.user_resource('CONFIG'), FONTS_FOLDER)


def your_fonts():
    """[(name, path)] of the font files in Plastron's fonts folder."""
    import os
    folder = fonts_folder()
    if not os.path.isdir(folder):
        return []
    return sorted(((os.path.splitext(n)[0], os.path.join(folder, n)) for n in os.listdir(folder)
                   if n.lower().endswith((".ttf", ".otf", ".ttc", ".woff", ".woff2"))), key=lambda t: t[0].lower())


def keep_font(path):
    """Copy a font file into Plastron's fonts folder (if it isn't there) and
    load it, packed into the project, so titles keep it if the file moves."""
    import os
    import shutil
    folder = fonts_folder()
    os.makedirs(folder, exist_ok=True)
    kept = os.path.join(folder, os.path.basename(path))
    if os.path.abspath(path) != os.path.abspath(kept) and not os.path.exists(kept):
        shutil.copy2(path, kept)
    font = bpy.data.fonts.load(kept, check_existing=True)
    if font.packed_file is None:
        try:
            font.pack()
        except RuntimeError as err:
            print("Plastron titles: couldn't pack the font:", err)
    return font


def _use_font(context, font):
    for s in clips.top_clips(context.scene):
        if s.select and is_title(s):
            s.font = font


class PLASTRON_OT_title_font(bpy.types.Operator):
    """Use a font file (.ttf / .otf) for the selected titles (kept in Plastron's fonts folder)"""
    bl_idname = "plastron.title_font"
    bl_label = "Load Font..."
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.ttf;*.otf;*.ttc;*.woff;*.woff2", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return active_title(context) is not None

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            font = keep_font(self.filepath)
        except (RuntimeError, OSError) as err:
            self.report({'WARNING'}, f"Couldn't use that font: {err}")
            return {'CANCELLED'}
        _use_font(context, font)
        self.report({'INFO'}, f"Font kept in {fonts_folder()}")
        return {'FINISHED'}


class PLASTRON_OT_title_font_pick(bpy.types.Operator):
    """Use one of your fonts for the selected titles"""
    bl_idname = "plastron.title_font_pick"
    bl_label = "Use Font"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    filepath: bpy.props.StringProperty()

    def execute(self, context):
        try:
            font = keep_font(self.filepath)
        except (RuntimeError, OSError) as err:
            self.report({'WARNING'}, f"Couldn't use that font: {err}")
            return {'CANCELLED'}
        _use_font(context, font)
        return {'FINISHED'}


class PLASTRON_OT_title_fonts_folder(bpy.types.Operator):
    """Open your fonts folder (font files put there show in the list)"""
    bl_idname = "plastron.title_fonts_folder"
    bl_label = "Open Fonts Folder"

    def execute(self, context):
        import os
        os.makedirs(fonts_folder(), exist_ok=True)
        bpy.ops.wm.path_open(filepath=fonts_folder())
        return {'FINISHED'}


class PLASTRON_MT_title_fonts(bpy.types.Menu):
    bl_idname = "PLASTRON_MT_title_fonts"
    bl_label = "Your Fonts"

    def draw(self, _context):
        layout = self.layout
        fonts = your_fonts()
        if not fonts:
            layout.label(text="No fonts yet: Load Font... keeps them here")
        for name, path in fonts:
            layout.operator("plastron.title_font_pick", text=name).filepath = path
        layout.separator()
        layout.operator("plastron.title_font", text="Load Font...", icon='FILEBROWSER')
        layout.operator("plastron.title_fonts_folder", icon='FILE_FOLDER')


def draw_panel(layout, context, strip):
    """The Clip panel's Text section for a selected title."""
    box = layout.box()
    row = box.row(align=True)
    row.label(text="Text", icon='FONT_DATA')
    row.menu("PLASTRON_MT_title_styles", text="Style", icon='PRESET')
    box.label(text="Click its text in the picture to edit it", icon='INFO')
    row = box.row(align=True)
    row.prop(strip, "font_size", text="Size")
    row.prop(strip, "use_bold", text="", icon='BOLD', toggle=True)
    row.prop(strip, "use_italic", text="", icon='ITALIC', toggle=True)
    row = box.row(align=True)
    row.label(text=strip.font.name if strip.font else "Default", icon='FONT_DATA')
    row.menu("PLASTRON_MT_title_fonts", text="Your Fonts")
    box.prop(strip, "color", text="")
    box.row().prop(strip, "alignment_x", expand=True)
    box.prop(strip, "wrap_width", text="Wrap Width", slider=True)
    for flag, colour, extra in (("use_outline", "outline_color", "outline_width"),
                                ("use_shadow", "shadow_color", "shadow_blur"),
                                ("use_box", "box_color", "box_margin")):
        row = box.row(align=True)
        row.prop(strip, flag, text={"use_outline": "Outline", "use_shadow": "Shadow", "use_box": "Box"}[flag],
                 toggle=True)
        sub = row.row(align=True)
        sub.active = getattr(strip, flag)
        sub.prop(strip, colour, text="")
        sub.prop(strip, extra, text="")


def draw_preview_button(layout, context):
    layout.operator("plastron.title_add", text="Text", icon='FONT_DATA')


classes = (PLASTRON_OT_title_add, PLASTRON_OT_title_type, PLASTRON_OT_title_finish, PLASTRON_OT_title_box,
           PLASTRON_OT_title_double_click, PLASTRON_MT_title_styles, PLASTRON_OT_title_font,
           PLASTRON_OT_title_font_pick, PLASTRON_OT_title_fonts_folder, PLASTRON_MT_title_fonts)
_handles = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    presets.register_kind(KIND, apply=_preset_apply, capture=_preset_capture)
    from ... import timeline as _timeline
    _timeline.HOLDERS.append(typing_anywhere)
    from ...timeline import header
    header.add_preview_section(draw_preview_button)
    _handles.append(bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'PREVIEW', 'POST_PIXEL'))


def unregister():
    from ... import timeline as _timeline
    if typing_anywhere in _timeline.HOLDERS:
        _timeline.HOLDERS.remove(typing_anywhere)
    if bpy.app.timers.is_registered(_fix_outline):
        bpy.app.timers.unregister(_fix_outline)
    while _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handles.pop(), 'PREVIEW')
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
