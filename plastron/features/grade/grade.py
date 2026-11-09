"""A clip's grade: Blender's Color Balance (lift / gamma / gain), Bright /
Contrast and White Balance modifiers on the clip (added the first time it's
graded), plus its saturation and tint. Values as a plain dict for looks
(presets/grades/) and copy / paste. Grade Everything: one adjustment clip
on the Grade track over the whole project, kept as long as the project."""

import bpy

from ...config import grade as cfg
from ...core import presets
from ...timeline import clips, events, tracks

KIND = "grades"
EVERYTHING = "plastron_grade_all"


def gradable(strip):
    return strip is not None and strip.type != 'SOUND' and hasattr(strip, "modifiers") \
        and hasattr(strip, "color_saturation")


def mods(strip):
    return {t: strip.modifiers.get(n) for n, t in cfg.MODIFIERS}


def is_graded(strip):
    return all(m is not None for m in mods(strip).values())


def ensure(strip):
    """The clip's grading modifiers (made the first time)."""
    for name, kind in cfg.MODIFIERS:
        if strip.modifiers.get(name) is None:
            m = strip.modifiers.new(name, kind)
            if kind == 'COLOR_BALANCE':
                m.color_balance.correction_method = 'LIFT_GAMMA_GAIN'
    return mods(strip)


def values(strip):
    m = mods(strip)
    cb, bc, wb = m['COLOR_BALANCE'], m['BRIGHT_CONTRAST'], m['WHITE_BALANCE']
    out = {"saturation": strip.color_saturation, "multiply": list(strip.color_multiply)} \
        if hasattr(strip.color_multiply, "__len__") else {"saturation": strip.color_saturation}
    if cb is not None:
        out.update(lift=list(cb.color_balance.lift), gamma=list(cb.color_balance.gamma),
                   gain=list(cb.color_balance.gain))
    if bc is not None:
        out.update(bright=bc.bright, contrast=bc.contrast)
    if wb is not None:
        out.update(white=list(wb.white_value))
    return out


def apply(strip, vals, reset=False):
    """Set the grade from a dict (missing values: unchanged, or neutral if reset)."""
    m = ensure(strip)
    neutral = {"lift": [1, 1, 1], "gamma": [1, 1, 1], "gain": [1, 1, 1], "bright": 0.0, "contrast": 0.0,
               "saturation": 1.0, "multiply": [1, 1, 1], "white": [1, 1, 1]}
    vals = dict(neutral, **vals) if reset else vals
    cb = m['COLOR_BALANCE'].color_balance
    for key in ("lift", "gamma", "gain"):
        if key in vals:
            setattr(cb, key, vals[key][:3])
    if "bright" in vals:
        m['BRIGHT_CONTRAST'].bright = vals["bright"]
    if "contrast" in vals:
        m['BRIGHT_CONTRAST'].contrast = vals["contrast"]
    if "white" in vals:
        m['WHITE_BALANCE'].white_value = vals["white"][:3]
    if "saturation" in vals:
        strip.color_saturation = vals["saturation"]
    if "multiply" in vals and hasattr(strip.color_multiply, "__len__"):
        strip.color_multiply = vals["multiply"][:len(strip.color_multiply)]
    elif "multiply" in vals:
        strip.color_multiply = sum(vals["multiply"][:3]) / 3


def apply_look(strip, look):
    """A look starts from neutral."""
    apply(strip, {k: v for k, v in look.items() if k not in ("name", "order", "built_in", "file")}, reset=True)


# --- Grade Everything ------------------------------------------------------------------

def grade_track(scene):
    for track in tracks.all_tracks(scene):
        if track.kind == 'VIDEO' and tracks.name(scene, track) == cfg.GRADE_TRACK:
            return track
    return tracks.add(scene, 'VIDEO', track_name=cfg.GRADE_TRACK)


def everything_clip(scene, make=False):
    clip = next((s for s in clips.top_clips(scene) if s.get(EVERYTHING)), None)
    if clip is None and make:
        ch = tracks.channel_of(scene, grade_track(scene))
        end = max([clips.end(s) for s in clips.top_clips(scene)] + [scene.frame_start + 1])
        clip = clips.editor(scene).strips.new_effect("Grade Everything", 'ADJUSTMENT', ch,
                                                     scene.frame_start, length=end - scene.frame_start)
        clip[EVERYTHING] = True
        ensure(clip)
        events.clips_changed(scene)
    return clip


def _follow(scene, **_info):
    """Grade Everything lasts as long as the project."""
    clip = everything_clip(scene)
    if clip is None:
        return
    others = [s for s in clips.top_clips(scene) if s != clip]
    if not others:
        return
    start = min(scene.frame_start, min(clips.start(s) for s in others))
    end = max(clips.end(s) for s in others)
    if (clips.start(clip), clips.end(clip)) != (start, end):
        clips._set(clip, start, end)


# --- Operators ---------------------------------------------------------------------------

def selected_gradable(context):
    return [s for s in clips.top_clips(context.scene) if s.select and gradable(s)]


_clipboard = {}


class PLASTRON_OT_grade_start(bpy.types.Operator):
    """Grade the selected clips (adds their colour wheels)"""
    bl_idname = "plastron.grade_start"
    bl_label = "Grade This Clip"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        chosen = selected_gradable(context)
        for s in chosen:
            ensure(s)
        return {'FINISHED'} if chosen else {'CANCELLED'}


class PLASTRON_OT_grade_reset(bpy.types.Operator):
    """Put the selected clips' grade back to neutral"""
    bl_idname = "plastron.grade_reset"
    bl_label = "Reset Grade"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for s in selected_gradable(context):
            apply(s, {}, reset=True)
        return {'FINISHED'}


class PLASTRON_OT_grade_copy(bpy.types.Operator):
    """Copy the selected clip's grade"""
    bl_idname = "plastron.grade_copy"
    bl_label = "Copy Grade"

    def execute(self, context):
        strip = context.scene.sequence_editor.active_strip
        if not gradable(strip):
            return {'CANCELLED'}
        _clipboard.clear()
        _clipboard.update(values(strip))
        self.report({'INFO'}, "Grade copied")
        return {'FINISHED'}


class PLASTRON_OT_grade_paste(bpy.types.Operator):
    """Paste the copied grade onto the selected clips"""
    bl_idname = "plastron.grade_paste"
    bl_label = "Paste Grade"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(_clipboard)

    def execute(self, context):
        for s in selected_gradable(context):
            apply(s, dict(_clipboard), reset=True)
        return {'FINISHED'}


class PLASTRON_OT_grade_look(bpy.types.Operator):
    """Give the selected clips this look"""
    bl_idname = "plastron.grade_look"
    bl_label = "Look"
    bl_options = {'REGISTER', 'UNDO'}
    look: bpy.props.StringProperty()

    def execute(self, context):
        look = next((p for p in presets.all_presets(KIND) if p["name"] == self.look), None)
        chosen = selected_gradable(context)
        if look is None or not chosen:
            return {'CANCELLED'}
        for s in chosen:
            apply_look(s, look)
        return {'FINISHED'}


class PLASTRON_OT_grade_everything(bpy.types.Operator):
    """Grade the whole picture at once (an adjustment clip over everything, on the Grade track)"""
    bl_idname = "plastron.grade_everything"
    bl_label = "Grade Everything"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        clip = everything_clip(scene, make=True)
        for s in clips.all_clips(scene):
            s.select = s == clip
        scene.sequence_editor.active_strip = clip
        return {'FINISHED'}


class PLASTRON_MT_grade_looks(bpy.types.Menu):
    bl_label = "Looks"

    def draw(self, context):
        for p in presets.all_presets(KIND):
            self.layout.operator("plastron.grade_look", text=p["name"]).look = p["name"]


classes = (PLASTRON_OT_grade_start, PLASTRON_OT_grade_reset, PLASTRON_OT_grade_copy, PLASTRON_OT_grade_paste,
           PLASTRON_OT_grade_look, PLASTRON_OT_grade_everything, PLASTRON_MT_grade_looks)


def register():
    presets.register_kind(KIND, apply=lambda preset, context=None: None, capture=lambda context=None: {})
    for cls in classes:
        bpy.utils.register_class(cls)
    events.listen("clips_changed", _follow)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
