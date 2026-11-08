"""Board view (the brief's "a toggle that switches the timeline to a grid of
panel thumbnails. Drag to reorder, then switch back with the timeline
updated").

Timeline header: Board. The timeline area shows the panels of the active
video track (else the first with panels) as cards in time order: picture,
name, length, status colour, the start of the note. Drag a card and drop
it between others: the panels are put in that order, one after another from
where the first started (their lengths and paintings stay). Click a card to
put the playhead on it; double-click goes back to the timeline there.
"""

import os

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import review as cfg
from ...core.theme import _color
from ...timeline import clips, events, tracks

B = cfg.BOARD
_images = {}         # cached image path -> (mtime, bpy image)
_drag = {"from": None, "to": None, "pos": None}


def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def on(context=None):
    return bool(getattr((context or bpy.context).window_manager, "plastron_board", False))


def board_track(scene):
    from ..storyboard.panels import is_panel
    active = tracks.active(scene)
    candidates = ([active] if active and active.kind == 'VIDEO' else []) + tracks.video_tracks(scene)
    for track in candidates:
        if any(is_panel(s) for s in clips.on_channel(scene, tracks.channel_of(scene, track))):
            return track
    return None


def board_panels(scene):
    """The board's panels, in time order."""
    from ..storyboard.panels import is_panel
    track = board_track(scene)
    if track is None:
        return []
    return [s for s in clips.on_channel(scene, tracks.channel_of(scene, track)) if is_panel(s)]


def layout(region, count):
    """[(x0, y0, x1, y1)] card rectangles (picture + caption), top-left first."""
    w, gap, cap = _ui(B["card_w"]), _ui(B["gap"]), _ui(B["caption"])
    h = w * 9 / 16 + cap
    cols = max(1, int((region.width - gap) // (w + gap)))
    out = []
    for i in range(count):
        r, c = divmod(i, cols)
        x0 = gap + c * (w + gap)
        y1 = region.height - gap - r * (h + gap)
        out.append((x0, y1 - h, x0 + w, y1))
    return out


def card_at(region, count, x, y):
    for i, (x0, y0, x1, y1) in enumerate(layout(region, count)):
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None


def drop_index(region, count, x, y):
    """Where a card dropped at (x, y) goes: the index it would take."""
    rects = layout(region, count)
    best, best_d = count, None
    for i, (x0, y0, x1, y1) in enumerate(rects):
        if y0 <= y <= y1 or best_d is None:
            mid = (x0 + x1) / 2
            row_d = 0 if y0 <= y <= y1 else min(abs(y - y0), abs(y - y1))
            idx = i if x < mid else i + 1
            d = (row_d, abs(x - mid))
            if best_d is None or d < best_d:
                best, best_d = idx, d
    return best


def reorder(scene, strips, order):
    """Put strips (time order) into the new order (list of indices), one after
    another from where the first started."""
    t = clips.start(strips[0])
    # A reorder is often a cycle (each wants another's place), which a move
    # without overlaps can't untangle: park them all past the end first.
    far = max(clips.end(s) for s in clips.all_clips(scene)) + 100
    for s in strips:
        clips.apply(scene, {s: (far, far + clips.length(s))})
        far += clips.length(s) + 10
    changes = {}
    for i in order:
        s = strips[i]
        length = clips.length(s)
        changes[s] = (t, t + length)
        t += length
    clips.apply(scene, changes)
    events.clips_changed(scene)


def _texture(strip):
    path = bpy.path.abspath(os.path.join(strip.directory, strip.elements[0].filename))
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cached = _images.get(path)
    if cached is None or cached[1].name not in bpy.data.images:
        img = bpy.data.images.load(path, check_existing=False)
        img.name = ".plastron board " + os.path.basename(path)
        _images[path] = (mtime, img)
    elif cached[0] != mtime:
        cached[1].reload()
        _images[path] = (mtime, cached[1])
    try:
        return gpu.texture.from_image(_images[path][1])
    except Exception:
        return None


def _rect(shader, r, colour):
    x0, y0, x1, y1 = r
    shader.uniform_float("color", colour)
    batch_for_shader(shader, 'TRIS', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]},
                     indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)


def draw():
    context = bpy.context
    if not on(context) or context.region is None:
        return
    from ...core.views import is_timeline
    if not is_timeline(context.space_data):
        return
    region = context.region
    scene = context.scene
    strips = board_panels(scene)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    _rect(shader, (0, 0, region.width, region.height), _color(B["back"]))
    rects = layout(region, len(strips))
    status = {sid: hexc for sid, _l, _t, hexc in cfg.STATUS}
    fps = scene.render.fps / scene.render.fps_base
    cap = _ui(B["caption"])
    tex_shader = gpu.shader.from_builtin('IMAGE')
    for i, (strip, (x0, y0, x1, y1)) in enumerate(zip(strips, rects)):
        if _drag["from"] == i and _drag["pos"] is not None:
            continue                                   # drawn under the pen instead
        _rect(shader, (x0, y0, x1, y1), _color(B["card"]))
        pic = (x0, y0 + cap, x1, y1)
        tex = _texture(strip)
        if tex is not None:
            tex_shader.uniform_sampler("image", tex)
            batch_for_shader(tex_shader, 'TRI_FAN', {"pos": [(pic[0], pic[1]), (pic[2], pic[1]), (pic[2], pic[3]),
                                                             (pic[0], pic[3])],
                                                     "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)]}).draw(tex_shader)
        info = strip.plastron_panel
        _rect(shader, (x0, y0 + cap - _ui(4), x1, y0 + cap), _color(status.get(getattr(info, "status", ""), "#000000")))
        blf.size(0, _ui(11))
        blf.color(0, *_color(B["text"]))
        blf.position(0, x0 + _ui(4), y0 + cap - _ui(16), 0)
        blf.draw(0, f"{strip.name}   {clips.length(strip) / fps:.1f} s")
        note = getattr(info, "note", "") or info.script_text
        if note:
            blf.size(0, _ui(9))
            blf.color(0, *_color(B["text_dim"]))
            text = note
            while text and blf.dimensions(0, text)[0] > (x1 - x0) - _ui(8):
                text = text[:-2]
            blf.position(0, x0 + _ui(4), y0 + _ui(5), 0)
            blf.draw(0, text if text == note else text + "…")
    if _drag["from"] is not None and _drag["pos"] is not None and _drag["to"] is not None:
        to = _drag["to"]
        if rects:
            ref = rects[min(to, len(rects) - 1)]
            x = ref[0] - _ui(B["gap"]) / 2 if to < len(rects) else ref[2] + _ui(B["gap"]) / 2
            _rect(shader, (x - _ui(2), ref[1], x + _ui(2), ref[3]), _color(B["drop"]))
            mx, my = _drag["pos"]
            w, hh = (ref[2] - ref[0]) * 0.8, (ref[3] - ref[1]) * 0.8
            _rect(shader, (mx - w / 2, my - hh / 2, mx + w / 2, my + hh / 2), (*_color(B["drop"])[:3], 0.35))
    gpu.state.blend_set('NONE')


class PLASTRON_OT_board_click(bpy.types.Operator):
    """Board: drag a card to reorder; click to go to it; double-click to go back to the timeline"""
    bl_idname = "plastron.board_click"
    bl_label = "Board"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return on(context) and context.area is not None and context.area.type == 'SEQUENCE_EDITOR' \
            and context.region is not None and context.region.type == 'WINDOW'

    def invoke(self, context, event):
        scene = context.scene
        self.strips = board_panels(scene)
        i = card_at(context.region, len(self.strips), event.mouse_region_x, event.mouse_region_y)
        if i is None:
            return {'FINISHED'}            # (the board covers the timeline: nothing under it)
        strip = self.strips[i]
        scene.frame_current = clips.start(strip)
        for s in clips.all_clips(scene):
            s.select = s == strip
        scene.sequence_editor.active_strip = strip
        if event.value == 'DOUBLE_CLICK':
            context.window_manager.plastron_board = False
            return {'FINISHED'}
        self.start = (event.mouse_region_x, event.mouse_region_y)
        _drag.update({"from": i, "to": None, "pos": None})
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        region = context.region
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            x, y = event.mouse_region_x, event.mouse_region_y
            if _drag["pos"] is not None or abs(x - self.start[0]) + abs(y - self.start[1]) > 6:
                _drag["pos"] = (x, y)
                _drag["to"] = drop_index(region, len(self.strips), x, y)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            src, to = _drag["from"], _drag["to"]
            moved = _drag["pos"] is not None and to is not None and to not in (src, src + 1)
            _drag.update({"from": None, "to": None, "pos": None})
            if moved:
                order = list(range(len(self.strips)))
                order.pop(src)
                order.insert(to - 1 if to > src else to, src)
                reorder(context.scene, self.strips, order)
                try:
                    bpy.ops.ed.undo_push(message="Reorder panels")
                except RuntimeError:
                    pass
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            _drag.update({"from": None, "to": None, "pos": None})
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


def _toggled(_self, context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()


def draw_header(layout, context):
    layout.prop(context.window_manager, "plastron_board", text="Board", toggle=True, icon='IMGDISPLAY')


classes = (PLASTRON_OT_board_click,)
_handle = None


def register():
    global _handle
    bpy.types.WindowManager.plastron_board = bpy.props.BoolProperty(
        name="Board", description="The panels as a grid of cards: drag to reorder", update=_toggled)
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle = bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')
    from ...timeline import header
    header.add_section(draw_header)


def unregister():
    global _handle
    if _handle is not None:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.plastron_board
    for _mtime, img in _images.values():
        if img.name in bpy.data.images:
            bpy.data.images.remove(img)
    _images.clear()
