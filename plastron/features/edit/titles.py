"""Titles: text over the picture (Ollie: "I need an add text tool", for the
video: titles, labels, lower thirds).

Text in the preview header (or T over the timeline / preview) adds a title
at the playhead on a "Titles" track (made on top of the video tracks if
missing), TITLE_SECONDS long, and starts typing in it right away: the words
are typed in the picture itself (Blender's text editing in the preview:
arrows, Home / End, Shift to select, Ctrl+A / C / V / X, Enter = new line).
Tab or Esc finishes; Tab on a selected title (or double-clicking it in the
preview) types in it again. While typing, Plastron's own preview keys stand
aside (core/views.typing).

A selected title has a box in the preview: drag inside to move it, a corner
to size it (the font grows / shrinks). Its look (font, size, colour,
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
    window = context.window or bpy.context.window
    for area in (window.screen.areas if window else []):
        if area.type == 'SEQUENCE_EDITOR' and is_preview(area.spaces.active):
            region = next((r for r in area.regions if r.type == 'PREVIEW'), None)
            if region is not None:
                return window, area, region
    return None


def start_typing(context, strip, select_all=False):
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
            self.report({'INFO'}, "Title added: type its words in the Clip panel (no preview open)")
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

def rect(scene, strip):
    """(x0, y0, x1, y1) of the title's words in preview (project pixel)
    coordinates, (0, 0) at the frame's middle. Measured with Blender's font
    at the title's size: close enough to grab."""
    r = scene.render
    w_px, h_px = r.resolution_x, r.resolution_y
    size = strip.font_size
    fid = _blf_id(strip)
    blf.size(fid, size)
    lines = strip.text.split("\n") or [""]
    width = max([blf.dimensions(fid, line or " ")[0] for line in lines] + [size * 0.6])
    if strip.use_bold:
        width *= 1.06                                  # (Blender makes bold by thickening)
    if strip.wrap_width > 0:
        width = min(width, strip.wrap_width * w_px)
    height = size * (1.2 * (len(lines) - 1) + 1.0)
    lx = (strip.location[0] - 0.5) * w_px + strip.transform.offset_x
    ly = (strip.location[1] - 0.5) * h_px + strip.transform.offset_y
    x0 = {"LEFT": lx, "CENTER": lx - width / 2, "RIGHT": lx - width}.get(strip.anchor_x, lx - width / 2)
    y0 = {"BOTTOM": ly, "CENTER": ly - height / 2, "TOP": ly - height}.get(strip.anchor_y, ly - height / 2)
    m = strip.box_margin * w_px if strip.use_box else 0
    return x0 - m, y0 - m, x0 + width + m, y0 + height + m


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
    top-left), or None."""
    strip = boxed(context)
    if strip is None:
        return None
    x0, y0, x1, y1 = _region_rect(context.region, rect(context.scene, strip))
    grab = _ui(cfg.TITLE_BOX["grab_px"])
    for i, (cx, cy) in enumerate(((x0, y0), (x1, y0), (x1, y1), (x0, y1))):
        if abs(x - cx) <= grab and abs(y - cy) <= grab:
            return i
    if x0 - grab <= x <= x1 + grab and y0 - grab <= y <= y1 + grab:
        return 'MOVE'
    return None


class PLASTRON_OT_title_box(bpy.types.Operator):
    """Drag the selected title: inside moves it, a corner sizes it"""
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
        r = rect(context.scene, self.strip)
        self.centre = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        scene = context.scene
        if event.type == 'MOUSEMOVE':
            vx, vy = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
            r = scene.render
            if self.part == 'MOVE':
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
            return {'FINISHED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.strip.location = self.loc
            self.strip.font_size = self.size
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
        start_typing(context, strip)
        return {'FINISHED'}


def draw():
    context = bpy.context
    if not is_preview(context.space_data):
        return
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
    batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    gpu.state.blend_set('NONE')


# --- Panel / header ----------------------------------------------------------------------------

class PLASTRON_MT_title_styles(bpy.types.Menu):
    bl_idname = "PLASTRON_MT_title_styles"
    bl_label = "Title Styles"

    def draw(self, _context):
        presets.draw_menu(self.layout, KIND)


class PLASTRON_OT_title_font(bpy.types.Operator):
    """Use a font file (.ttf / .otf) for the selected titles"""
    bl_idname = "plastron.title_font"
    bl_label = "Load Font..."
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.ttf;*.otf;*.ttc", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return active_title(context) is not None

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            font = bpy.data.fonts.load(self.filepath, check_existing=True)
        except RuntimeError as err:
            self.report({'WARNING'}, f"Couldn't use that font: {err}")
            return {'CANCELLED'}
        for s in clips.top_clips(context.scene):
            if s.select and is_title(s):
                s.font = font
        return {'FINISHED'}


def draw_panel(layout, context, strip):
    """The Clip panel's Text section for a selected title."""
    box = layout.box()
    row = box.row(align=True)
    row.label(text="Text", icon='FONT_DATA')
    row.menu("PLASTRON_MT_title_styles", text="Style", icon='PRESET')
    box.prop(strip, "text", text="")
    box.operator("plastron.title_type", text="Type in the Picture (Tab)", icon='GREASEPENCIL')
    row = box.row(align=True)
    row.prop(strip, "font_size", text="Size")
    row.prop(strip, "use_bold", text="", icon='BOLD', toggle=True)
    row.prop(strip, "use_italic", text="", icon='ITALIC', toggle=True)
    row = box.row(align=True)
    row.template_ID(strip, "font", open="font.open")
    row.operator("plastron.title_font", text="", icon='FILEBROWSER')
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
           PLASTRON_OT_title_double_click, PLASTRON_MT_title_styles, PLASTRON_OT_title_font)
_handles = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    presets.register_kind(KIND, apply=_preset_apply, capture=_preset_capture)
    from ...timeline import header
    header.add_preview_section(draw_preview_button)
    _handles.append(bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'PREVIEW', 'POST_PIXEL'))


def unregister():
    while _handles:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handles.pop(), 'PREVIEW')
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
