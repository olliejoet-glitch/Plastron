"""Packing CaraPainter's float images small (§60).

Blender packs a generated float image as an uncompressed 32-bit EXR: 67 MB for a 2048² map, and
the normal-map analysis alone makes five of them per normal map. Here the image is written once as
a ZIP-compressed HALF-float EXR (~5-15 MB), the SAME datablock is switched to that file and packed,
so every node and material keeps pointing at it, and later re-packs (after painting, re-analysing
or baking into it) keep the compact format. Half floats keep ~3 significant digits (errors around
0.0002 for 0..1 data): far below anything visible.
"""
import os
import tempfile

import bpy


def _settings(scn):
    s = scn.render.image_settings
    if hasattr(s, "media_type"):
        s.media_type = 'IMAGE'
    s.file_format = 'OPEN_EXR'
    s.color_depth = '16'           # half float
    s.exr_codec = 'ZIP'            # lossless
    s.color_mode = 'RGBA'
    try:   # an EXR stores the data as it is: never a view transform / look
        s.color_management = 'OVERRIDE'
        s.view_settings.view_transform = 'Standard'
        s.view_settings.look = 'None'
    except (AttributeError, TypeError):
        pass


def _safe(img):
    """EXR stores colour premultiplied: an image whose alpha is real transparency (not a data
    channel) and isn't opaque everywhere would come back with its colours changed. CaraPainter's
    float maps are channel-packed data or opaque bakes; anything else keeps Blender's packing."""
    if img.alpha_mode == 'CHANNEL_PACKED' or img.alpha_mode == 'NONE':
        return True
    import numpy as np
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    return bool(px.size) and float(px[3::4].min()) >= 0.9999


def pack_float(img):
    """Pack `img`: a float image as a compressed half EXR (in place), anything else as usual."""
    if img is None:
        return
    if not img.is_float or not _safe(img):
        img.pack()
        return
    cs, am = img.colorspace_settings.name, img.alpha_mode
    fd, path = tempfile.mkstemp(prefix="pl_", suffix=".exr")
    os.close(fd)
    scn = bpy.data.scenes.new("_pl_pack_tmp")
    try:
        _settings(scn)
        img.save_render(path, scene=scn)
        if img.packed_file is not None:
            img.unpack(method='REMOVE')   # (the old uncompressed copy)
        img.filepath = path
        img.source = 'FILE'
        img.reload()
        img.colorspace_settings.name = cs
        img.alpha_mode = am
        img.pack()
        img.filepath = ""                 # it lives packed in the .blend, no outside path
    finally:
        bpy.data.scenes.remove(scn)
        try:
            os.remove(path)
        except OSError:
            pass


def is_bloated(img):
    """A float image packed bigger than an uncompressed HALF-float copy would be: Blender's
    32-bit default (files made before 0.24)."""
    if img is None or not img.is_float or img.packed_file is None:
        return False
    w, h = img.size
    return img.packed_file.size > w * h * 8 * 1.05


def ours(img):
    return bool(img.get("pl_owned")) or img.name.startswith(("PL ", "PL·"))
