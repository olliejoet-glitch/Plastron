"""Cached panel images: what each panel clip shows on the timeline (and what
the animatic export will use), so playback never redraws the drawings.

Files live next to the project in "<project>_cache/", or in Blender's temp
folder until the project is first saved (copied across on save).
Stage 2 writes a plain placeholder; stage 3 renders the drawing into it.
"""

import os
import shutil

import bpy
import numpy as np

from ...core.theme import _color

SIZE = (480, 270)


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


def write_placeholder(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    w, h = SIZE
    img = bpy.data.images.new("plastron_cache_tmp", w, h)
    pixels = np.tile(np.array(_color("paper")[:3] + [1.0], dtype=np.float32), w * h)
    img.pixels.foreach_set(pixels)
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


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
