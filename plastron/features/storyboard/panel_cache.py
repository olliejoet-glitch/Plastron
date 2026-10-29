"""Cached panel images: what each panel clip shows on the timeline (and what
the animatic export will use), so playback never redraws the paintings.

Files live next to the project in "<project>_cache/", or in Blender's temp
folder until the project is first saved (copied across on save).

An image is re-made (the camera frame of the panel's layers, flattened in
numpy over the paper colour) shortly after its panel is painted on or its
layers change; never during playback.
"""

import os
import shutil
import time

import bpy
import numpy as np

from ...config import project_defaults as defaults
from ...core import handlers
from ...layers import events as layer_events, paint_target

SIZE = defaults.PANEL_IMAGE_SIZE
DELAY = 0.4          # seconds of quiet after an edit before re-making images

_pending = {"materials": set(), "last": 0.0}


def cache_dir(blend_path=None):
    blend_path = blend_path if blend_path is not None else bpy.data.filepath
    if blend_path:
        folder, name = os.path.split(blend_path)
        return os.path.join(folder, os.path.splitext(name)[0] + "_cache")
    return os.path.join(bpy.app.tempdir, "plastron_cache")


def file_name(uid):
    return f"panel_{uid}.png"


def strip_path(strip):
    return bpy.path.abspath(os.path.join(strip.directory, strip.elements[0].filename))


def paper():
    from .canvas_color import current
    return np.array(current(), np.float32)


def _write(path, rgba):
    """rgba: float array (rows bottom-up, w, 4) -> PNG at path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    h, w = rgba.shape[:2]
    img = bpy.data.images.new("plastron_cache_tmp", w, h)
    try:
        img.pixels.foreach_set(np.ascontiguousarray(rgba, np.float32).ravel())
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    finally:
        bpy.data.images.remove(img)


def write_placeholder(path):
    w, h = SIZE
    rgba = np.empty((h, w, 4), np.float32)
    rgba[..., :3] = paper()
    rgba[..., 3] = 1.0
    _write(path, rgba)


def frame_crop(stack):
    """The camera frame's pixels within a panel's painting: (x0, y0, w, h)."""
    fw = stack.width * defaults.PAINT_FRAME[0] / defaults.PAINT_RESOLUTION[0]
    fh = stack.height * defaults.PAINT_FRAME[1] / defaults.PAINT_RESOLUTION[1]
    return ((stack.width - fw) / 2, (stack.height - fh) / 2, fw, fh)


def render(strip):
    """Re-make strip's cached image from its painting."""
    from ...layers.flatten import flatten
    mat = strip.plastron_panel.material
    if mat is None or not mat.plastron_stack.enabled:
        return
    rgba = flatten(mat, crop=frame_crop(mat.plastron_stack), out_size=SIZE)
    alpha = rgba[..., 3:4]
    rgba[..., :3] = rgba[..., :3] * alpha + paper() * (1.0 - alpha)
    rgba[..., 3] = 1.0
    _write(strip_path(strip), rgba)
    strip.invalidate_cache('RAW')


# --- re-making images after edits (debounced) ------------------------------------

def request(mat):
    """mat's panel image needs re-making soon."""
    if mat is None:
        return
    _pending["materials"].add(mat.name)
    _pending["last"] = time.monotonic()
    if not bpy.app.timers.is_registered(_flush):
        bpy.app.timers.register(_flush, first_interval=DELAY)


def _flush():
    wait = DELAY - (time.monotonic() - _pending["last"])
    if wait > 0.01:
        return wait                       # still being edited
    names, _pending["materials"] = _pending["materials"], set()
    from .panels import all_panels
    for scene in bpy.data.scenes:
        if not hasattr(scene, "plastron_timeline") or scene.sequence_editor is None:
            continue
        for strip in all_panels(scene):
            mat = strip.plastron_panel.material
            if mat is not None and mat.name in names:
                try:
                    render(strip)
                except Exception as err:      # never break painting over a thumbnail
                    print(f"Plastron: couldn't update {strip.name}'s image: {err}")
    return None


def flush_now():
    """Re-make every pending image straight away (tests, saving)."""
    _pending["last"] = 0.0
    if bpy.app.timers.is_registered(_flush):
        bpy.app.timers.unregister(_flush)
    _flush()


def point_at(strip, folder, uid):
    """Make strip show folder/panel_<uid>.png (creating it if missing)."""
    path = os.path.join(folder, file_name(uid))
    if not os.path.exists(path):
        old = strip_path(strip) if len(strip.elements) else ""
        if old and os.path.exists(old) and old != path:
            os.makedirs(folder, exist_ok=True)
            shutil.copyfile(old, path)
        else:
            write_placeholder(path)
    if os.path.normpath(bpy.path.abspath(strip.directory)) != os.path.normpath(folder):
        strip.directory = folder + os.sep
    if strip.elements[0].filename != file_name(uid):
        strip.elements[0].filename = file_name(uid)


def copy_for(uid_from, uid_to, folder=None):
    folder = folder or cache_dir()
    src = os.path.join(folder, file_name(uid_from))
    dst = os.path.join(folder, file_name(uid_to))
    if os.path.exists(src):
        shutil.copyfile(src, dst)
    else:
        write_placeholder(dst)


def _on_stroke(scene, depsgraph):
    # O(1): a finished brush stroke updates the painted image (never during
    # playback). Other image updates (e.g. writing these images) are ignored.
    if not depsgraph.id_type_updated('IMAGE'):
        return
    mat = paint_target.active_material()
    target = paint_target.target_image(mat)
    if target is not None and any(u.id.original == target for u in depsgraph.updates
                                  if isinstance(u.id, bpy.types.Image)):
        request(mat)


def _on_undo(*_args):
    request(paint_target.active_material())


def register():
    layer_events.listen(request)
    handlers.add("depsgraph_update_post", _on_stroke)
    handlers.add("undo_post", _on_undo)
    handlers.add("redo_post", _on_undo)


def unregister():
    if bpy.app.timers.is_registered(_flush):
        bpy.app.timers.unregister(_flush)
