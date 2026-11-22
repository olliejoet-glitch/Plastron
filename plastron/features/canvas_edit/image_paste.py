"""Pictures from the computer's clipboard (Ollie: "I need to be able to paste
images into the panels", for a pacing study of a nature documentary).

Ctrl+V on the canvas pastes a picture copied anywhere else (a screenshot, a
frame copied from a browser or a player) as a new layer "Image", fitted to
the camera frame (PASTE_IMAGE_FIT in config/tools.py). Pixels copied in
Plastron (Ctrl+C / Ctrl+X) still paste in place: whichever was copied last
wins (Windows numbers every clipboard change; elsewhere a picture on the
clipboard wins).

Blender reads clipboard pictures (Windows / macOS) only with an Image
Editor in context: another area is turned into one for that moment.
"""

import sys

import bpy
import numpy as np

from ...config import tools as cfg
from . import shapes

_state = {"copied_at": None}
SPARE_AREAS = ('DOPESHEET_EDITOR', 'TEXT_EDITOR', 'PROPERTIES', 'FILE_BROWSER', 'OUTLINER')


def sequence():
    """The clipboard's change number (Windows), else None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())
    except Exception:
        return None


def mark_copied():
    """Plastron copied pixels: until the clipboard changes, Ctrl+V is ours."""
    _state["copied_at"] = sequence()


def clipboard_is_newer(have_own):
    """Should Ctrl+V look at the computer's clipboard first?"""
    if not have_own:
        return True
    now = sequence()
    return now is None or now != _state["copied_at"]


def read_system(window=None):
    """The picture on the computer's clipboard as RGBA floats (rows bottom-up),
    or None."""
    window = window or bpy.context.window
    if window is None:
        return None
    area = next((a for kind in SPARE_AREAS for a in window.screen.areas if a.type == kind), None)
    if area is None:
        return None
    old = area.ui_type
    before = set(bpy.data.images)
    try:
        area.ui_type = 'IMAGE_EDITOR'
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(window=window, area=area, region=region):
            if not bpy.ops.image.clipboard_paste.poll():
                return None
            bpy.ops.image.clipboard_paste()
    except Exception as err:
        print("Plastron paste: couldn't read the clipboard picture:", err)
        return None
    finally:
        space = area.spaces.active
        if getattr(space, "image", None) is not None and space.image not in before:
            space.image = None
        area.ui_type = old
    new = [img for img in bpy.data.images if img not in before]
    if not new:
        return None
    img = new[0]
    w, h = img.size
    arr = None
    if w and h:
        arr = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(arr)
        arr = arr.reshape(h, w, 4)
    for img in new:
        bpy.data.images.remove(img)
    return arr


def fitted(picture, w, h, frame, fit=None):
    """Pure: picture (rows bottom-up) placed in the camera frame (frame_w,
    frame_h, in the middle of a w x h painting), "contain" or "cover"
    -> a w x h straight-alpha RGBA array."""
    fit = fit or cfg.PASTE_IMAGE_FIT
    ph, pw = picture.shape[:2]
    fw, fh = frame
    k = (max if fit == "cover" else min)(fw / pw, fh / ph)
    sw, sh = pw * k, ph * k
    x0, y0 = w / 2 - sw / 2, h / 2 - sh / 2
    src = picture.copy()
    if fit == "cover":                     # (only what's inside the frame)
        cx0, cy0 = max(x0, w / 2 - fw / 2), max(y0, h / 2 - fh / 2)
        cx1, cy1 = min(x0 + sw, w / 2 + fw / 2), min(y0 + sh, h / 2 + fh / 2)
        i0, i1 = int(round((cx0 - x0) / k)), int(round((cx1 - x0) / k))
        j0, j1 = int(round((cy0 - y0) / k)), int(round((cy1 - y0) / k))
        src = src[j0:j1, i0:i1]
        x0, y0, sw, sh = cx0, cy0, cx1 - cx0, cy1 - cy0
    grid = shapes.grid_from_corners(shapes.rect_corners(x0, y0, x0 + sw, y0 + sh), 8)
    pre = shapes.render(src, grid, w, h)
    return shapes.over(np.zeros((h, w, 4), np.float32), pre)
