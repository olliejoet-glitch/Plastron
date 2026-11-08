"""Fades: each clip can fade in and out (its picture's opacity, its
sound's volume). Drag the little handles at a clip's top corners on the
timeline inward to set them (the ramp shows over the clip); Ctrl+D puts a
dip (fade out + fade in) on the cut at the playhead.

The lengths are stored on the clip (strip.plastron.fade_in / fade_out, in
frames) and written as a few keyframes Blender plays itself (no Python per
frame), rewritten only when a clip's place, fades or base value change.
A clip's own opacity is strip.plastron.opacity (what the fades go up to);
a sound's volume comes from the mix (mix.py calls write()).
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..config import timeline as cfg
from . import clips, events

GROUP = "Fades"
SIG = "plastron_fade_sig"


# --- Keyframes ------------------------------------------------------------------------

def _action(scene):
    ad = scene.animation_data
    return ad.action if ad else None


def _bags(action):
    if hasattr(action, "fcurves"):
        return [action]
    out = []
    for layer in action.layers:
        for st in layer.strips:
            out.extend(getattr(st, "channelbags", []))
    return out


def _remove(scene, path):
    action = _action(scene)
    if action is None:
        return
    for bag in _bags(action):
        for fc in [fc for fc in bag.fcurves if fc.data_path == path]:
            bag.fcurves.remove(fc)


def prop_of(strip):
    return "volume" if strip.type == 'SOUND' else "blend_alpha"


GAIN = "plastron_gain"       # extra gain curve on a clip: [(frame, gain)...] (e.g. ducking)


def gain_points(strip):
    raw = strip.get(GAIN)
    return [tuple(p) for p in raw] if raw else []


def set_gain(strip, points):
    """An extra gain curve (frames, 0-1 gains) multiplied into the clip's
    volume / opacity (e.g. ducking). Empty: none. True if it changed."""
    points = [(round(float(f), 2), round(float(g), 4)) for f, g in points]
    if points == gain_points(strip):
        return False
    if points:
        strip[GAIN] = points
    elif GAIN in strip:
        del strip[GAIN]
    return True


def has_fades(strip):
    return strip.plastron.fade_in > 0 or strip.plastron.fade_out > 0 or bool(strip.get(GAIN))


def _interp(points, f):
    if not points:
        return 1.0
    if f <= points[0][0]:
        return points[0][1]
    for (f0, g0), (f1, g1) in zip(points, points[1:]):
        if f <= f1:
            return g0 if f1 == f0 else g0 + (g1 - g0) * (f - f0) / (f1 - f0)
    return points[-1][1]


def write(scene, strip, base=None):
    """Write strip's fades (and extra gain curve) as keyframes, or its plain
    value if it has neither."""
    prop = prop_of(strip)
    if base is None:
        base = strip.plastron.opacity if prop == "blend_alpha" else strip.get("plastron_volume_now", strip.volume)
    s, e = clips.start(strip), clips.end(strip)
    fin, fout = strip.plastron.fade_in, strip.plastron.fade_out
    if fin + fout > e - s:                                 # (fades can't be longer than the clip)
        k = (e - s) / max(1, fin + fout)
        fin, fout = int(fin * k), int(fout * k)
    extra = [(f, g) for f, g in gain_points(strip) if s <= f <= e]
    sig = repr((strip.name, s, e, fin, fout, round(base, 5), extra))
    if strip.get(SIG) == sig:
        return
    path = strip.path_from_id(prop)
    _remove(scene, path)
    if prop == "volume":
        strip["plastron_volume_now"] = base
    if not fin and not fout and not extra:
        setattr(strip, prop, base)
        if SIG in strip:
            del strip[SIG]
        return
    shape = [(s, 0.0), (s + fin, 1.0)] if fin else [(s, 1.0)]
    shape += [(e - fout, 1.0), (e, 0.0)] if fout else [(e, 1.0)]
    whole = [(s, _interp(gain_points(strip), s))] + extra + [(e, _interp(gain_points(strip), e))]
    frames = sorted({f for f, _v in shape} | {f for f, _v in whole})
    for frame in frames:
        setattr(strip, prop, base * _interp(shape, frame) * _interp(whole, frame))
        strip.keyframe_insert(prop, frame=frame, group=GROUP)
    action = _action(scene)
    for bag in _bags(action) if action else []:
        for fc in bag.fcurves:
            if fc.data_path == path:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
    strip[SIG] = sig


def refresh(scene, **_info):
    """Rewrite the fades of picture clips whose place changed (sounds: mix.py)."""
    sed = scene.sequence_editor if scene else None
    if sed is None:
        return
    names = set()
    for strip in clips.all_clips(scene):
        names.add(strip.name)
        if strip.type != 'SOUND' and (has_fades(strip) or SIG in strip):
            write(scene, strip)
    _forget_gone(scene, names)


def _forget_gone(scene, names):
    """Fade keyframes of clips that are gone (deleted, renamed)."""
    action = _action(scene)
    if action is None:
        return
    for bag in _bags(action):
        for fc in list(bag.fcurves):
            p = fc.data_path
            if p.startswith('sequence_editor.strips_all["') and fc.group and fc.group.name == GROUP:
                name = p.split('"')[1]
                if name not in names:
                    bag.fcurves.remove(fc)


def set_fade(scene, strip, side, frames):
    """side 'IN' / 'OUT'; its linked clips (same span) get the same."""
    frames = max(0, int(frames))
    for s in [strip] + [o for o in clips.linked(strip) if (clips.start(o), clips.end(o)) ==
                        (clips.start(strip), clips.end(strip))]:
        if side == 'IN':
            s.plastron.fade_in = frames
        else:
            s.plastron.fade_out = frames
    events.emit("mix_changed", scene)          # (sounds: written with the mix volume)
    refresh(scene)


def dip(scene, frame, frames, channel=None):
    """A dip on the cut at frame: the clip ending there fades out, the one
    starting there fades in (each half the length). Returns the clips."""
    done = []
    for strip in clips.top_clips(scene):
        if channel is not None and strip.channel != channel:
            continue
        if clips.end(strip) == frame:
            set_fade(scene, strip, 'OUT', frames // 2)
            done.append(strip)
        elif clips.start(strip) == frame:
            set_fade(scene, strip, 'IN', frames - frames // 2)
            done.append(strip)
    return done


def _on_split(scene, original=None, new=None, **_info):
    if original is None or new is None:
        return
    new.plastron.fade_out = original.plastron.fade_out
    new.plastron.fade_in = 0
    original.plastron.fade_out = 0
    for s in (original, new):
        if SIG in s:
            del s[SIG]


# --- Handles on the timeline ----------------------------------------------------------------

def _ui(px):
    return px * bpy.context.preferences.system.ui_scale


def handle_points(region, strip):
    """((x, y) of the fade-in handle, (x, y) of the fade-out handle) in region pixels."""
    v2d = region.view2d
    top = strip.channel + cfg.FADE_HANDLE_Y
    xin = v2d.view_to_region(clips.start(strip) + strip.plastron.fade_in, top, clip=False)
    xout = v2d.view_to_region(clips.end(strip) - strip.plastron.fade_out, top, clip=False)
    return xin, xout


def handle_at(region, scene, x, y):
    """(strip, 'IN' / 'OUT') under the pen, or None."""
    reach = _ui(cfg.FADE_HANDLE_PX)
    best = None
    for strip in clips.top_clips(scene):
        a = region.view2d.view_to_region(clips.start(strip), strip.channel, clip=False)
        b = region.view2d.view_to_region(clips.end(strip), strip.channel, clip=False)
        if b[0] - a[0] < _ui(cfg.FADE_MIN_CLIP_PX):
            continue
        for side, (hx, hy) in zip(('IN', 'OUT'), handle_points(region, strip)):
            d = abs(hx - x) + abs(hy - y)
            if d <= reach and (best is None or d < best[0]):
                best = (d, strip, side)
    return best[1:] if best else None


def draw():
    from ..core.views import is_timeline
    context = bpy.context
    if not is_timeline(context.space_data) or context.region is None:
        return
    scene = context.scene
    if scene is None or scene.sequence_editor is None:
        return
    region = context.region
    from ..core.theme import _color
    line = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    line.uniform_float("viewportSize", (region.width, region.height))
    line.uniform_float("lineWidth", 1.5)
    fill = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    r = _ui(cfg.FADE_HANDLE_PX) * 0.45
    for strip in clips.top_clips(scene):
        v2d = region.view2d
        x0, yb = v2d.view_to_region(clips.start(strip), strip.channel + cfg.FADE_RAMP_BOTTOM, clip=False)
        x1, _ = v2d.view_to_region(clips.end(strip), strip.channel, clip=False)
        if x1 < 0 or x0 > region.width or x1 - x0 < _ui(cfg.FADE_MIN_CLIP_PX):
            continue
        (hin, ytop), (hout, _y) = handle_points(region, strip)
        line.uniform_float("color", _color(cfg.FADE_COLOR))
        if strip.plastron.fade_in:
            batch_for_shader(line, 'LINES', {"pos": [(x0, yb), (hin, ytop)]}).draw(line)
        if strip.plastron.fade_out:
            batch_for_shader(line, 'LINES', {"pos": [(hout, ytop), (x1, yb)]}).draw(line)
        fill.uniform_float("color", _color(cfg.FADE_COLOR))
        for hx in (hin, hout):
            batch_for_shader(fill, 'TRIS', {"pos": [(hx - r, ytop - r), (hx + r, ytop - r), (hx + r, ytop + r),
                                                    (hx - r, ytop + r)]},
                             indices=[(0, 1, 2), (0, 2, 3)]).draw(fill)
    gpu.state.blend_set('NONE')


class PLASTRON_OT_fade_drag(bpy.types.Operator):
    """Drag a clip's corner handle inward to fade it in / out"""
    bl_idname = "plastron.fade_drag"
    bl_label = "Fade"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..core.views import is_timeline
        if getattr(context.window_manager, "plastron_board", False):     # (the board covers the timeline)
            return False
        return is_timeline(context.space_data) and context.region is not None and context.region.type == 'WINDOW'

    def invoke(self, context, event):
        found = handle_at(context.region, context.scene, event.mouse_region_x, event.mouse_region_y)
        if found is None:
            return {'PASS_THROUGH'}
        strip, self.side = found
        self.strip_name = strip.name
        self.orig = strip.plastron.fade_in if self.side == 'IN' else strip.plastron.fade_out
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        scene = context.scene
        strip = scene.sequence_editor.strips_all.get(self.strip_name)
        if strip is None:
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            f = round(context.region.view2d.region_to_view(event.mouse_region_x, 0)[0])
            other = strip.plastron.fade_out if self.side == 'IN' else strip.plastron.fade_in
            room = clips.length(strip) - other
            frames = f - clips.start(strip) if self.side == 'IN' else clips.end(strip) - f
            set_fade(scene, strip, self.side, max(0, min(room, frames)))
            context.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            set_fade(scene, strip, self.side, self.orig)
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class PLASTRON_OT_fade_dip(bpy.types.Operator):
    """Dip on the cut at the playhead: the clip before fades out, the one after fades in"""
    bl_idname = "plastron.fade_dip"
    bl_label = "Dip at Cut"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        fps = scene.render.fps / scene.render.fps_base
        frames = max(2, round(cfg.DIP_SECONDS * fps))
        from . import edit_keys, tracks
        frame = scene.frame_current
        cuts = edit_keys.cuts(scene)
        if frame not in cuts and cuts:
            frame = min(cuts, key=lambda c: abs(c - frame))         # the nearest cut
        track = tracks.active(scene)
        channel = tracks.channel_of(scene, track) if track else None
        if not dip(scene, frame, frames, channel) and not dip(scene, frame, frames):
            self.report({'INFO'}, "No cut at the playhead")
            return {'CANCELLED'}
        context.area.tag_redraw()
        return {'FINISHED'}


classes = (PLASTRON_OT_fade_drag, PLASTRON_OT_fade_dip)
_handle = [None]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    events.listen("clips_changed", refresh)
    events.listen("clip_split", _on_split)
    _handle[0] = bpy.types.SpaceSequenceEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(_handle[0], 'WINDOW')
        _handle[0] = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
