"""Panel thumbnails follow edits (features/storyboard/panel_cache.py):
Blender's timeline thumbnails are cached by file name, so every re-made panel
image gets a new name. Pasting a picture into a panel shows on its clip."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

pc = h.module("features.storyboard.panel_cache")
panels = h.module("features.storyboard.panels")
clips = h.module("timeline.clips")
ip = h.module("features.canvas_edit.image_paste")


def panel():
    return next(s for s in clips.top_clips(bpy.context.scene) if panels.is_panel(s))


def thumb_colour(name):
    """The colour drawn in the middle of the panel's clip on the timeline (on screen)."""
    area = h.area('SEQUENCE_EDITOR')
    reg = h.region(area)
    p = panel()
    x, y = reg.view2d.view_to_region((clips.start(p) + clips.end(p)) / 2, p.channel + 0.35, clip=False)
    path = h.screenshot(name)
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, hh = img.size
        px = np.array(img.pixels[:], np.float32).reshape(hh, w, 4)
        return tuple(np.round(px[int(reg.y + y), int(reg.x + x), :3], 2))
    finally:
        bpy.data.images.remove(img)


def paste(colour):
    pic = np.zeros((90, 160, 4), np.float32)
    pic[...] = colour + (1.0,)
    ip.read_system = lambda window=None: pic
    ip.sequence = lambda: paste.n
    paste.n += 1
    canvas = h.area('VIEW_3D')
    reg = h.region(canvas)
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    h.key('V', ctrl=True)


paste.n = 10


def wait_for_new_image(old_name):
    for _ in range(60):                    # (re-made 2.5 s after the edit; Material Preview is slow here)
        yield 0.2
        if panel().elements[0].filename != old_name:
            break
    for _ in range(3):
        h.redraw()
        yield 0.5                          # (Blender makes thumbnails in the background)


def steps():
    yield 1.0
    real_read, real_seq = ip.read_system, ip.sequence
    try:
        with h.override('SEQUENCE_EDITOR'):
            bpy.ops.ed.undo_push(message="start")
        first = panel().elements[0].filename
        first_path = pc.strip_path(panel())
        paste((0.0, 0.0, 1.0))
        yield from wait_for_new_image(first)
        p = panel()
        h.check("pasting a picture into a panel re-makes its image, under a new name",
                p.elements[0].filename != first and pc.is_own(p.elements[0].filename, p.plastron_panel.uid)
                and os.path.exists(pc.strip_path(p)), (first, p.elements[0].filename))
        h.check("...the old image file goes", not os.path.exists(first_path), first_path)
        c = thumb_colour("thumb_blue")
        h.check("...and the clip's thumbnail on the timeline shows it (blue)", c[2] > 0.6 and c[0] < 0.3, c)
        second = p.elements[0].filename
        paste((1.0, 0.0, 0.0))
        yield from wait_for_new_image(second)
        c = thumb_colour("thumb_red")
        h.check("pasting again: the thumbnail follows again (red)", c[0] > 0.6 and c[2] < 0.3, c)

        # Undo goes back to an older image name whose file is gone: it's put back.
        h.key('Z', ctrl=True)
        yield 0.6
        p = panel()
        h.check("undo: the panel's image file exists (made again if it was gone)",
                os.path.exists(pc.strip_path(p)), pc.strip_path(p))
    finally:
        ip.read_system, ip.sequence = real_read, real_seq

    # Saving tidies away images no panel uses.
    folder = os.path.join(bpy.app.tempdir, "thumbs_save")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "thumbs.blend")
    cache = pc.cache_dir(path)
    os.makedirs(cache, exist_ok=True)
    stray = os.path.join(cache, pc.file_name("nobody", "x1"))
    open(stray, "wb").close()
    bpy.ops.wm.save_as_mainfile(filepath=path)
    yield 0.5
    p = panel()
    h.check("saving: panels' images are in the project's cache folder, strays tidied away",
            os.path.dirname(pc.strip_path(p)) == cache and os.path.exists(pc.strip_path(p))
            and not os.path.exists(stray), (pc.strip_path(p), os.listdir(cache)))


h.run(steps())
