"""Bake (the Bake Animation button at the top of the Motion panel; Ollie: the storyboard
animations weren't visible in Edit mode, "I want a bake button on the
storyboard page, not a bake after I edit every panel's animation").

The timeline shows each panel as its still picture (where it starts). Bake
renders every animated panel's frames, on its own, as the canvas shows it,
and the panel's clip plays them instead (its image list becomes those
frames; the still is kept to come back to):
  - 3D Camera on: the canvas view through the panel's 3D Camera (Blender's
    viewport render), other tracks' cards / onion skin / compare hidden;
    cards, camera and moving layers play by the frame hooks as usual.
  - 3D Camera off: the painting flattened per frame (numpy, like the
    thumbnails) at the 2D camera's crop with the layers at their positions.
Only panels that animate and aren't baked (or changed since) are done; the
button shows how many. Esc stops. Any edit to a baked panel puts its still
back (painting / layers: panel_cache.render; moves / keys / its length:
a signature check after edits); moving the whole clip keeps the bake.
Exports use the baked frames (animatic._panel_frames skips baked panels).
Frames: JPEG at BAKE_SIZE (config/motion.py) in the panel cache folder,
"bake_<uid>_<stamp>_<n>.jpg" (new names each bake: Blender's thumbnails are
cached by file name); unused ones are tidied on save (panel_cache.tidy).
"""

import hashlib
import os

import bpy
import numpy as np

from ...config import motion as cfg
from ...core import handlers
from ...timeline import clips, events, tracks
from ...widgets import dot_graph
from ..storyboard import canvas_sync, panel_cache
from . import camera, layer_motion

SIG = "plastron_bake_sig"
STILL = "plastron_bake_still"
SCALE = "plastron_bake_scale"
KEYS = (SIG, STILL, SCALE)

_state = {"running": False, "done": 0, "total": 0, "needs": None, "busy": False}


def baked(strip):
    return SIG in strip


def three_d():
    from ..scene3d import linked
    return linked()


def animated(scene, strip):
    """Does this panel move (as the canvas shows it now)?"""
    from ..scene3d import shots
    mat = strip.plastron_panel.material
    if mat is not None and any(layer_motion.has_motion(l) for l in mat.plastron_stack.layers):
        return True
    if three_d():
        return shots.animated(scene, strip, shots.CARD_PROPS + shots.CAM_PROPS)
    return camera.moves(strip)


def _r(values):
    return tuple(round(float(v), 4) for v in values)


def signature(scene, strip):
    """What a bake depends on besides the painting (a painting edit re-makes
    the still: panel_cache.render unbakes) and where the clip sits (moving
    the whole clip keeps its bake): its length, track, moves, keys, the mode."""
    from ..scene3d import shots
    m = strip.plastron_motion
    parts = [clips.length(strip), strip.channel, three_d(),
             _r(camera.as_tuple(m.start)), _r(camera.as_tuple(m.end)), dot_graph.points(m.curve) if m.curve else None,
             _r((m.shake, m.shake_speed)), round(scene.render.fps / scene.render.fps_base, 4)]
    mat = strip.plastron_panel.material
    if mat is not None:
        parts.append([(l.uid, _r((*l.move_start, *l.move_end)), dot_graph.points(l.move_curve) if l.move_curve else None)
                      for l in mat.plastron_stack.layers if layer_motion.has_motion(l)])
    fcs = shots.curves(strip)
    for (prop, i), fc in sorted(fcs.items()):
        parts.append((prop, i, [(_r(k.co), k.interpolation, k.easing) for k in fc.keyframe_points]))
    if three_d():                       # (resting values count only where nothing is keyed)
        keyed = {p for (p, _i), fc in fcs.items() if len(fc.keyframe_points)}
        parts.append(strip.plastron_cam_set)
        for prop in shots.ANIM_PROPS:
            if prop not in keyed:
                v = getattr(strip, prop)
                parts.append((prop, _r(v) if hasattr(v, "__len__") else round(v, 4)))
    return hashlib.md5(repr(parts).encode()).hexdigest()


def needs(scene):
    """Animated panels whose bake is missing or out of date (cached until the next edit)."""
    if _state["needs"] is None:
        from ..storyboard.panels import all_panels
        out = []
        for s in all_panels(scene):
            if animated(scene, s) and (not baked(s) or s[SIG] != signature(scene, s)):
                out.append(s.name)
        _state["needs"] = out
    sed = scene.sequence_editor
    return [sed.strips_all[n] for n in _state["needs"] if sed and n in sed.strips_all]


def _forget(*_args, **_info):
    _state["needs"] = None


# --- a clip showing its frames / its still ------------------------------------------------

def apply(strip, frames, width, sig):
    """The clip plays frames (file names in its folder), its still kept."""
    from ..export.animatic import _png_width
    still = strip.elements[0].filename
    still_w = _png_width(panel_cache.strip_path(strip))
    t = strip.transform
    strip[STILL] = still
    strip[SCALE] = (t.scale_x, t.scale_y)
    start, end = clips.start(strip), clips.end(strip)
    els = strip.elements
    els[0].filename = frames[0]
    for name in frames[1:]:
        els.append(name)
    clips.apply(strip.id_data, {strip: (start, end)})
    k = still_w / width
    t.scale_x, t.scale_y = t.scale_x * k, t.scale_y * k
    strip[SIG] = sig
    strip.invalidate_cache('RAW')


def unbake(strip):
    """Back to its still picture (its frames stay on disk until a save tidies them)."""
    if not baked(strip):
        return False
    start, end = clips.start(strip), clips.end(strip)
    els = strip.elements
    while len(els) > 1:
        els.pop(len(els) - 1)
    els[0].filename = strip[STILL]
    sx, sy = strip[SCALE]
    strip.transform.scale_x, strip.transform.scale_y = sx, sy
    for k in KEYS:
        if k in strip:
            del strip[k]
    clips.apply(strip.id_data, {strip: (start, end)})     # (one picture again: as long as before)
    strip.invalidate_cache('RAW')
    _forget()
    return True


def keeps(strip, folder, uid):
    """A baked panel goes on showing its frames in folder (copied there, e.g.
    the first save of a project): only its own uid's frames (a split-off
    copy has a new uid: its still), all of them there."""
    import shutil
    d = bpy.path.abspath(strip.directory)
    names = [e.filename for e in strip.elements] + [strip[STILL]]
    if not all(n.startswith(f"bake_{uid}_") for n in names[:-1]):
        return False
    if not all(os.path.exists(os.path.join(d, n)) for n in names):
        return False
    if os.path.normpath(d) != os.path.normpath(folder):
        os.makedirs(folder, exist_ok=True)
        for n in names:
            if not os.path.exists(os.path.join(folder, n)):
                shutil.copyfile(os.path.join(d, n), os.path.join(folder, n))
        strip.directory = folder + os.sep
    return True


def broken(scene):
    """Baked panels missing a frame file (or their still)."""
    from ..storyboard.panels import all_panels
    out = []
    for s in all_panels(scene):
        if baked(s):
            d = bpy.path.abspath(s.directory)
            names = [e.filename for e in s.elements] + [s[STILL]]
            if not all(os.path.exists(os.path.join(d, n)) for n in names):
                out.append(s)
    return out


def check(scene):
    """After edits: a baked panel whose length / timing / moves changed shows its still again."""
    if _state["running"] or scene is None or scene.sequence_editor is None:
        return
    from ..storyboard.panels import all_panels
    for s in all_panels(scene):
        if not baked(s):
            continue
        whole = clips.start(s) == round(s.content_start) and clips.end(s) - clips.start(s) == len(s.elements)
        if not whole or s[SIG] != signature(scene, s):
            unbake(s)


def _check_later():
    _state["busy"] = False
    scene = bpy.context.scene
    if scene is not None and hasattr(scene, "plastron_timeline"):
        check(scene)
    return None


def _on_edit(scene, _depsgraph):
    # O(1): note it; the baked panels are checked once things settle.
    _state["needs"] = None
    if not _state["busy"] and not _state["running"]:
        _state["busy"] = True
        bpy.app.timers.register(_check_later, first_interval=0.5)


# --- rendering frames -----------------------------------------------------------------------

def _canvas():
    from ..scene3d import canvas_areas
    for area in canvas_areas():
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if region is not None:
            for window in bpy.context.window_manager.windows:
                if area in window.screen.areas[:]:
                    return window, area, region
    return None


def _hide_others(scene, hidden):
    from ..review.versions import COMPARE
    for obj in scene.objects:
        n = obj.name
        if n.startswith(canvas_sync.DISPLAY_PREFIX) or n in canvas_sync.ONION or n == COMPARE:
            if obj.name not in hidden:
                hidden[obj.name] = obj.hide_viewport
            if not obj.hide_viewport:
                obj.hide_viewport = True


def _write_jpeg(path, rgba):
    h, w = rgba.shape[:2]
    img = bpy.data.images.new("plastron_bake_tmp", w, h)
    try:
        img.pixels.foreach_set(np.ascontiguousarray(rgba, np.float32).ravel())
        img.filepath_raw = path
        img.file_format = 'JPEG'
        img.save(quality=cfg.BAKE_QUALITY)
    finally:
        bpy.data.images.remove(img)


def _frame_2d(scene, strip, frame, path, size):
    from ...layers.flatten import flatten
    mat = strip.plastron_panel.material
    st = mat.plastron_stack
    fps = scene.render.fps / scene.render.fps_base
    crop = camera.crop(camera.state_at(strip, frame, fps), panel_cache.frame_crop(st))
    t = camera.clip_time(strip, frame)
    offsets = {l.uid: layer_motion.position(l, t) for l in st.layers}
    rgba = flatten(mat, crop=crop, out_size=size, offsets=offsets)
    alpha = rgba[..., 3:4]
    rgba[..., :3] = rgba[..., :3] * alpha + panel_cache.paper() * (1.0 - alpha)
    rgba[..., 3] = 1.0
    _write_jpeg(path, rgba)


def _frame_3d(scene, frame, path, where, hidden):
    window, area, region = where
    scene.frame_set(frame)                      # (the canvas places cards / camera / layers)
    _hide_others(scene, hidden)
    with bpy.context.temp_override(window=window, area=area, region=region, scene=scene):
        bpy.ops.render.opengl(view_context=True)
    bpy.data.images["Render Result"].save_render(path, scene=scene)


def run(context, names):
    """Bake these panels, one frame per step (a generator: the button's
    modal operator steps it so Plastron stays responsive; Esc closes it)."""
    scene = context.scene
    sed = scene.sequence_editor
    strips = [sed.strips_all[n] for n in names if n in sed.strips_all]
    size = tuple(cfg.BAKE_SIZE)
    r = scene.render
    saved = {k: getattr(r, k) for k in ("resolution_x", "resolution_y", "resolution_percentage")}
    saved_fmt = r.image_settings.file_format
    saved_media = getattr(r.image_settings, "media_type", None)
    saved_quality = r.image_settings.quality
    frame0 = scene.frame_current
    active = tracks.active(scene)
    hidden = {}
    where = _canvas() if three_d() else None
    shading = where[1].spaces.active.shading if where else None
    comp = shading.use_compositor if shading is not None else None
    _state.update(running=True, done=0, total=sum(clips.length(s) for s in strips))
    try:
        if where is not None:
            r.resolution_x, r.resolution_y = size
            r.resolution_percentage = 100
            if saved_media is not None:
                r.image_settings.media_type = 'IMAGE'
            r.image_settings.file_format = 'JPEG'
            r.image_settings.quality = cfg.BAKE_QUALITY
            if comp is not None and comp != 'DISABLED':
                shading.use_compositor = 'DISABLED'
        for strip in strips:
            unbake(strip)
            name = strip.name
            uid = strip.plastron_panel.uid
            folder = os.path.dirname(panel_cache.strip_path(strip))
            stamp = panel_cache._stamp()
            if where is not None:
                tracks.set_active(scene, tracks.track_of_channel(scene, strip.channel))
                canvas_sync.invalidate(scene)
            frames = []
            for i, frame in enumerate(range(clips.start(strip), clips.end(strip))):
                fname = f"bake_{uid}_{stamp}_{i:04d}.jpg"
                path = os.path.join(folder, fname)
                if where is not None:
                    _frame_3d(scene, frame, path, where, hidden)
                else:
                    _frame_2d(scene, sed.strips_all[name], frame, path, size)
                frames.append(fname)
                _state["done"] += 1
                yield
            strip = sed.strips_all[name]
            apply(strip, frames, size[0], signature(scene, strip))
    finally:
        _state["running"] = False
        for k, v in saved.items():
            setattr(r, k, v)
        if saved_media is not None:
            r.image_settings.media_type = saved_media
        r.image_settings.file_format = saved_fmt
        r.image_settings.quality = saved_quality
        if comp is not None and shading.use_compositor != comp:
            shading.use_compositor = comp
        for n, h in hidden.items():
            obj = bpy.data.objects.get(n)
            if obj is not None and obj.hide_viewport != h:
                obj.hide_viewport = h
        if active is not None:
            tracks.set_active(scene, active)
        scene.frame_set(frame0)
        canvas_sync.invalidate(scene)
        _forget()


class PLASTRON_OT_bake(bpy.types.Operator):
    """Bake the animated panels so the timeline (Edit mode, exports) plays their moves.
    Only panels that changed since their last bake are done; Esc stops"""
    bl_idname = "plastron.bake"
    bl_label = "Bake Animation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):            # (all at once: from Python / tests)
        panel_cache.flush_now()         # (stills still waiting to be re-made first: they'd drop the bake after)
        _forget()
        todo = [s.name for s in needs(context.scene)]
        if not todo:
            self.report({'INFO'}, "Nothing to bake: every animated panel is baked")
            return {'CANCELLED'}
        for _step in run(context, todo):
            pass
        self.report({'INFO'}, f"Baked {len(todo)} panel{'s' if len(todo) != 1 else ''}")
        return {'FINISHED'}

    def invoke(self, context, event):
        panel_cache.flush_now()         # (stills still waiting to be re-made first: they'd drop the bake after)
        _forget()
        todo = [s.name for s in needs(context.scene)]
        if not todo:
            self.report({'INFO'}, "Nothing to bake: every animated panel is baked")
            return {'CANCELLED'}
        self._n = len(todo)
        self._steps = run(context, todo)
        self._timer = context.window_manager.event_timer_add(0.001, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context):
        context.window_manager.event_timer_remove(self._timer)
        for area in context.screen.areas:
            area.tag_redraw()

    def modal(self, context, event):
        if event.type == 'ESC':
            self._steps.close()
            self._end(context)
            self.report({'INFO'}, "Bake stopped (panels done so far keep their bake)")
            return {'FINISHED'}
        if event.type == 'TIMER':
            try:
                next(self._steps)
            except StopIteration:
                self._end(context)
                self.report({'INFO'}, f"Baked {self._n} panel{'s' if self._n != 1 else ''}")
                return {'FINISHED'}
            for area in context.screen.areas:
                if area.type in {'VIEW_3D', 'PROPERTIES'}:      # (the canvas, the button's progress)
                    area.tag_redraw()
        return {'RUNNING_MODAL'}


def draw_button(layout, context):
    """Motion panel (tools area): Bake Animation (n) / Baking 12/240 (Esc stops)."""
    scene = context.scene
    if scene is None or scene.sequence_editor is None:
        return
    if _state["running"]:
        layout.label(text=f"Baking {_state['done']}/{_state['total']} (Esc stops)", icon='RENDER_ANIMATION')
        return
    n = len(needs(scene))
    row = layout.row()
    row.scale_y = 1.3
    row.alert = n > 0
    row.operator("plastron.bake", text=f"Bake Animation ({n} to do)" if n else "Animation Baked",
                 icon='RENDER_ANIMATION')


def _clips_changed(scene, **_info):
    _forget()
    check(scene)


def register():
    bpy.utils.register_class(PLASTRON_OT_bake)
    handlers.add("depsgraph_update_post", _on_edit)
    events.listen("clips_changed", _clips_changed)


def unregister():
    if bpy.app.timers.is_registered(_check_later):
        bpy.app.timers.unregister(_check_later)
    bpy.utils.unregister_class(PLASTRON_OT_bake)
