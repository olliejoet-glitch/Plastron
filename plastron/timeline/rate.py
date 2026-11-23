"""The project's frame rate, changeable (Ollie: match the phone footage, so
it plays smoothly: 30 fps video in a 24 fps project drops every 5th frame).

Blender's own fps change only half-adapts a timeline (sounds keep their
length in seconds, but every clip's start stays at the same FRAME number,
so everything slides out of place). change() keeps everything at the same
TIME instead: each clip's start / end / where its media starts, every
keyframe (per-clip cards and cameras, fades), fade lengths, gain curves,
markers (beats), the project / loop range and the playhead, in the main
timeline and in every info window's. Footage is re-timed to play at real
speed at the new rate (RETIME hooks, from features/edit).
"""

import bpy

from ..config import project_defaults as cfg
from . import clips, events

RETIME = []          # func(scene, strip): make a video play at real speed (after the fps changed)


def fps(scene):
    return scene.render.fps / scene.render.fps_base


def _fcurves(scene):
    ad = scene.animation_data
    action = ad.action if ad else None
    if action is None:
        return []
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    return [fc for layer in action.layers for st in layer.strips
            for bag in getattr(st, "channelbags", []) for fc in bag.fcurves]


def _scenes(scene):
    """The project's scene and its info windows' scenes."""
    out = [scene]
    for sc in bpy.data.scenes:
        if sc != scene and sc.get("plastron_window_of") == scene.name:
            out.append(sc)
    return out


def _gain_keys(strip):
    return [k for k in strip.keys() if k.startswith("plastron_gain")]


def change(scene, new_fps):
    """Set the project's frame rate, keeping everything at the same time.
    Returns False if it's already that rate."""
    if abs(fps(scene) - new_fps) < 1e-6:
        return False
    for sc in reversed(_scenes(scene)):          # (windows first: their clips' lengths follow)
        _change_one(sc, float(new_fps))
    events.clips_changed(scene)
    return True


def _change_one(scene, r1):
    r0 = fps(scene)
    k = r1 / r0
    sed = scene.sequence_editor
    strips = list(sed.strips_all) if sed else []
    # 1. Everything in seconds, before the rate changes.
    spans = {s: (s.left_handle / r0, s.right_handle / r0, s.content_start / r0) for s in strips}
    fade = {s: (s.plastron.fade_in, s.plastron.fade_out) for s in strips if hasattr(s, "plastron")}
    gains = {(s, g): [(f / r0, v) for f, v in s[g]] for s in strips for g in _gain_keys(s)}
    keys = [(fc, i, kp.co[0] / r0, kp.handle_left[0] / r0, kp.handle_right[0] / r0)
            for fc in _fcurves(scene) for i, kp in enumerate(fc.keyframe_points)]
    marks = [(m, m.frame / r0) for m in scene.timeline_markers]
    rng = (scene.frame_start / r0, scene.frame_end / r0, scene.frame_current / r0,
           scene.frame_preview_start / r0, scene.frame_preview_end / r0)
    auto = scene.plastron_timeline.range_auto if hasattr(scene, "plastron_timeline") else True

    # 2. The rate.
    scene.render.fps = int(round(r1))
    scene.render.fps_base = scene.render.fps / r1

    # 3. Clips back at their times. Footage first goes to spare channels: it's
    # re-timed whole (its retiming reset, opened out to all its media, so no
    # stretch is left at the old speed) and put back last.
    movies = [s for s in strips if s.type == 'MOVIE' and RETIME]
    home = {s: s.channel for s in movies}
    spare = max([s.channel for s in strips] + [1]) + 1
    for i, s in enumerate(movies):
        s.channel = spare + i
    changes = {s: (round(a * r1), max(round(a * r1) + 1, round(b * r1)), c * r1)
               for s, (a, b, c) in spans.items() if s not in home}
    clips.apply(scene, changes)
    for s in movies:
        a, b, c = spans[s]
        s.right_handle = round(s.content_end)
        s.left_handle = round(s.content_start)
        for func in RETIME:
            func(scene, s)                       # (plays at real speed at the new rate)
        s.content_start += c * r1 - s.content_start
        new_a, new_b = round(a * r1), max(round(a * r1) + 1, round(b * r1))
        s.right_handle = min(new_b, round(s.content_end))
        s.left_handle = max(new_a, round(s.content_start))
        s.channel = home[s]

    # 5. Keys (before fades: a fade length change rewrites its own keys), fades,
    # gain curves, markers, range, playhead.
    for fc, i, t, hl, hr in keys:
        try:
            kp = fc.keyframe_points[i]
        except (IndexError, ReferenceError):
            continue                              # (rewritten meanwhile: fades write their own)
        kp.co[0], kp.handle_left[0], kp.handle_right[0] = t * r1, hl * r1, hr * r1
    for fc in {fc for fc, *_rest in keys}:
        try:
            fc.update()
        except ReferenceError:
            pass
    for s, (fi, fo) in fade.items():
        if fi or fo:
            s.plastron.fade_in, s.plastron.fade_out = round(fi * k), round(fo * k)
    for (s, g), points in gains.items():
        s[g] = [(round(t * r1), v) for t, v in points]
    for m, t in marks:
        m.frame = round(t * r1)
    start, end, now, p0, p1 = rng
    scene.frame_start = round(start * r1)
    if not auto:
        scene.frame_end = round(end * r1)
    scene.frame_preview_start, scene.frame_preview_end = round(p0 * r1), round(p1 * r1)
    scene.frame_current = round(now * r1)


class PLASTRON_OT_project_fps(bpy.types.Operator):
    """Change the project's frame rate: every clip, key, fade and marker stays at the same time"""
    bl_idname = "plastron.project_fps"
    bl_label = "Project Frame Rate"
    bl_options = {'REGISTER', 'UNDO'}

    fps: bpy.props.IntProperty(default=24, min=1, max=240)

    @classmethod
    def description(cls, _context, props):
        return f"Make the project {props.fps} fps (match your footage: it plays smoothly). " \
               "Everything keeps its time in seconds"

    def execute(self, context):
        scene = context.scene
        if scene.get("plastron_window_of"):          # (inside an info window: the project's scene)
            scene = bpy.data.scenes.get(scene["plastron_window_of"], scene)
        if not change(scene, self.fps):
            return {'CANCELLED'}
        self.report({'INFO'}, f"The project is now {self.fps} fps")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


class PLASTRON_MT_project_fps(bpy.types.Menu):
    bl_idname = "PLASTRON_MT_project_fps"
    bl_label = "Frame Rate"

    def draw(self, context):
        now = fps(context.scene)
        for rate in cfg.FPS_CHOICES:
            self.layout.operator("plastron.project_fps", text=f"{rate} fps",
                                 icon='CHECKMARK' if abs(now - rate) < 1e-3 else 'BLANK1').fps = rate


def draw_header(layout, context):
    layout.menu("PLASTRON_MT_project_fps", text=f"{fps(context.scene):g} fps")


classes = (PLASTRON_OT_project_fps, PLASTRON_MT_project_fps)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
