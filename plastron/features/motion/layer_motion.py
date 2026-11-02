"""Layer and group motion: a layer (or a group, with everything in it) has a
position at the start of its panel and one at the end, eased by a dot graph
(layer.move_start / move_end / move_curve, canvas pixels).

Showing it (Ollie: layers must move with playback, to direct the shot):
every frame, during playback and scrubbing, the moving layers of the panels
under the playhead get their position (move_now: two shader values each; no
recompiling, nothing else is touched). Which layers move is worked out once
per stretch between clip edges / per edit, so a frame with no moving layers
costs nothing.

Painting a moved layer: the canvas sheet's UVs are shifted by how far the
layer being painted is shown moved (stack.view_shift; every layer is
shown shifted back by the same amount), so strokes land where you see them.
That is re-aimed shortly after scrubbing stops, at clip edges and after edits.
"""

import time

import bpy

from ...config import motion as cfg
from ...layers import compiler, layer_trees, paint_target, props
from ...timeline import clips, tracks
from ...widgets import dot_graph
from . import camera

_state = {"last": 0.0, "shifted": None, "busy": False}


def has_motion(layer):
    return any(abs(v) > 1e-6 for v in (*layer.move_start, *layer.move_end))


def position(layer, t):
    """Where a layer is (canvas pixels from where it was painted) at clip time t."""
    if not has_motion(layer):
        return (0.0, 0.0)
    e = dot_graph.evaluate(layer.move_curve, t)
    a, b = layer.move_start, layer.move_end
    return (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e)


def panels_at(scene, frame):
    """Panel clips under the playhead, one per video track."""
    from ..storyboard.panels import is_panel
    out = []
    for track in tracks.video_tracks(scene):
        clip = clips.at(scene, tracks.channel_of(scene, track), frame)
        if clip is not None and is_panel(clip) and clip.plastron_panel.material:
            out.append(clip)
    return out


def _push_all(mat):
    for layer in mat.plastron_stack.layers:
        compiler.push_layer(mat, layer)


def _close(a, b, tol=1e-4):
    return all(abs(p - q) <= tol for p, q in zip(a, b))


def _show(mat, t):
    """Write every layer's shown position; True if any changed."""
    changed = False
    st = mat.plastron_stack
    with props.suspended():
        for layer in st.layers:
            pos = position(layer, t)
            if not _close(layer.move_now, pos):
                layer.move_now = pos
                changed = True
    return changed


def _set_shift(mat, affine):
    """The canvas's paint UVs follow the painted layer: (scale, shift x, y)."""
    st = mat.plastron_stack
    a, mx, my = affine
    if abs(st.view_scale - a) < 1e-6 and _close(st.view_shift, (mx, my)):
        return False
    with props.suspended():
        st.view_scale = a
        st.view_shift = (mx, my)
    return True


def painted_affine(mat):
    """Where the layer being painted on is shown: (a, mx, my) as in
    layer_trees.shown_affine (1, 0, 0 = where it was painted)."""
    if mat is None or paint_target.target_image(mat) is None:
        return (1.0, 0.0, 0.0)
    st = mat.plastron_stack
    return layer_trees.shown_affine(st.active, st)


def painted_shift(mat):
    a, mx, my = painted_affine(mat)
    return (mx, my)


def refresh(scene=None):
    """Show every layer of the panels under the playhead where it is now."""
    if _state["busy"]:
        return
    scene = scene or bpy.context.scene
    if scene is None or not hasattr(scene, "plastron_timeline") or scene.sequence_editor is None:
        return
    _state["busy"] = True
    try:
        frame = scene.frame_current
        for strip in panels_at(scene, frame):
            mat = strip.plastron_panel.material
            if mat.plastron_stack.enabled and _show(mat, camera.clip_time(strip, frame)):
                _push_all(mat)
        _aim(scene)
    finally:
        _state["busy"] = False


def _aim(scene):
    """Shift the canvas's UVs (and the panel's look back) by the painted layer's move."""
    from ..storyboard import canvas_sync
    mat = paint_target.active_material()
    previous = bpy.data.materials.get(_state["shifted"] or "")
    if previous is not None and previous != mat and previous.plastron_stack.enabled:
        if _set_shift(previous, (1.0, 0.0, 0.0)):
            _push_all(previous)
    affine = painted_affine(mat)
    if mat is not None:
        if _set_shift(mat, affine):
            _push_all(mat)
        st = mat.plastron_stack
        a, mx, my = affine
        canvas_sync.shift_paint_uv(scene, mx / max(st.width, 1), my / max(st.height, 1), a)
        _state["shifted"] = mat.name
    else:
        canvas_sync.shift_paint_uv(scene, 0.0, 0.0)
        _state["shifted"] = None


# --- when to refresh ------------------------------------------------------------------

def _playing():
    wm = bpy.context.window_manager
    return wm is not None and any(w.screen and w.screen.is_animation_playing for w in wm.windows)


def _timer():
    wait = cfg.LAYER_REFRESH_DELAY - (time.monotonic() - _state["last"])
    if wait > 0.01:
        return wait
    from ..storyboard import stroke_guard
    if stroke_guard.busy():
        return 0.25                        # don't change the canvas sheet under a stroke
    if not _playing():
        refresh()
    return None


_live = {"key": None, "items": []}     # [(strip name, material, [moving layer uids])]


def _moving(scene):
    """What moves under the playhead (cached per stretch of clips / edit)."""
    from ..storyboard import canvas_sync
    key = (canvas_sync._state["work"], scene.name, camera._edits[0])
    if key != _live["key"]:
        items = []
        for strip in panels_at(scene, scene.frame_current):
            mat = strip.plastron_panel.material
            st = mat.plastron_stack
            uids = [l.uid for l in st.layers if has_motion(l)]
            if uids and mat.plastron_stack.enabled:
                items.append((strip.name, mat, uids))
        _live.update(key=key, items=items)
    return _live["items"]


def live(scene):
    """Moving layers to where they are at this frame (only those)."""
    sed = scene.sequence_editor
    for name, mat, uids in _moving(scene):
        strip = sed.strips_all.get(name) if sed else None
        if strip is None:
            continue
        t = camera.clip_time(strip, scene.frame_current)
        st = mat.plastron_stack
        for uid in uids:
            layer = st.by_uid(uid)
            if layer is None:
                continue
            pos = position(layer, t)
            if not _close(layer.move_now, pos, 1e-3):
                layer.move_now = pos          # pushes this layer (+ a group's layers)


def _motion_frame(scene, *_args):
    # Per-frame hook (allowed deliberately, Ollie's call: motion must play).
    # Camera view: a few numbers on the canvas views. Layers: only the ones
    # that move (cached list; empty = nothing to do). Painting is re-aimed
    # by a short timer once scrubbing stops, never during playback.
    from . import view_follow
    view_follow.follow(scene)
    live(scene)
    if _playing():
        return
    _state["last"] = time.monotonic()
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=cfg.LAYER_REFRESH_DELAY)


def _after_playback(scene, *_args):
    refresh(scene)


def _re_aimed(_mat):
    # Painting was re-aimed (another layer, another panel at a clip edge,
    # undo...): the canvas's UV shift must follow, also during playback
    # (clip edges only, like the canvas itself).
    refresh()


def _after_undo(*_args):
    camera.bump()
    refresh()
    from . import view_follow
    view_follow.follow()


def _on_load(scene):
    _state["shifted"] = None
    refresh(scene)


def register():
    from ...core import handlers
    handlers.add("frame_change_post", _motion_frame)
    handlers.add("animation_playback_post", _after_playback)
    handlers.add("undo_post", _after_undo)
    handlers.add("redo_post", _after_undo)
    handlers.on_load(_on_load)
    paint_target.listen(_re_aimed)


def unregister():
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
