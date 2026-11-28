"""Bake (Ollie: the storyboard animations weren't visible in Edit mode; "I
want a bake button on the storyboard page"): animated panels rendered to
frames the clip plays; edits that change the move put the still back;
moving the whole clip keeps the bake; exports use the baked frames."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

bake = h.module("features.motion.bake")
cfg = h.module("config.motion")
shots = h.module("features.scene3d.shots")
panels = h.module("features.storyboard.panels")
panel_cache = h.module("features.storyboard.panel_cache")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")
animatic = h.module("features.export.animatic")

cfg.BAKE_SIZE = (160, 90)


def paint(strip):
    mat = strip.plastron_panel.material
    img = mat.plastron_stack.layers[0].paint_image
    w, hh = img.size
    a = np.zeros((hh, w, 4), np.float32)
    a[hh // 3:hh // 2, w // 3:w // 2] = (0.1, 0.1, 0.1, 1.0)
    img.pixels.foreach_set(a.ravel())
    img.update()
    panel_cache.request(mat)
    panel_cache.flush_now()


def frame_pixels(strip, i):
    path = os.path.join(bpy.path.abspath(strip.directory), strip.elements[i].filename)
    img = bpy.data.images.load(path)
    try:
        px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(px)
        return img.size[:], px
    finally:
        bpy.data.images.remove(img)


def get(name):
    return bpy.context.scene.sequence_editor.strips_all.get(name)


def steps():
    yield 1.0
    sc = bpy.context.scene
    track = next(t for t in tracks.video_tracks(sc) if t.ripple)
    ch = tracks.channel_of(sc, track)
    for s in list(clips.on_channel(sc, ch)):
        ripple.remove(sc, s)
    yield 0.3
    sc = bpy.context.scene
    a = panels.create(sc, ch, 1, 12)
    b = panels.create(sc, ch, 13, 12)
    yield 0.3
    paint(a)
    paint(b)
    yield 0.3
    a_name, b_name = a.name, b.name
    still = a.elements[0].filename
    scale = a.transform.scale_x
    h.check("(nothing animates: nothing to bake)", bake.needs(sc) == [], [s.name for s in bake.needs(sc)])

    # 3D Camera (the default): a keyed card move on the first panel.
    shots.key(sc, a, shots.CARD_PROPS, 1, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0))
    shots.set_card(sc, a, (4.0, 0.0, 0.0), (0, 0, 0), 1.0, 12)
    bake._forget()
    h.check("a keyed card move: that panel needs baking", [s.name for s in bake.needs(sc)] == [a_name],
            [s.name for s in bake.needs(sc)])
    h.redraw()
    yield 0.5
    with h.override('VIEW_3D'):
        bpy.ops.plastron.bake()
    yield 0.5
    a = get(a_name)
    h.check("Bake: the panel plays one picture per frame", bake.baked(a) and len(a.elements) == 12
            and clips.start(a) == 1 and clips.end(a) == 13, (len(a.elements), clips.start(a), clips.end(a)))
    size0, px0 = frame_pixels(a, 0)
    size1, px1 = frame_pixels(a, 11)
    h.check("...at the bake size, the card moving between them",
            tuple(size0) == cfg.BAKE_SIZE and np.abs(px0 - px1).max() > 0.2, (size0, np.abs(px0 - px1).max()))
    h.check("...sized to fill the frame like its still (scale x still width / bake width)",
            abs(a.transform.scale_x - scale * panel_cache.SIZE[0] / cfg.BAKE_SIZE[0]) < 1e-4, a.transform.scale_x)
    h.check("...nothing left to bake", bake.needs(sc) == [], [s.name for s in bake.needs(sc)])
    h.screenshot("bake_3d")

    # Moving the whole clip keeps the bake.
    clips.apply(sc, {get(b_name): (40, 52)})
    clips.apply(sc, {get(a_name): (20, 32)})
    h.module("timeline.events").clips_changed(sc)
    yield 0.8
    a = get(a_name)
    h.check("moving the whole clip keeps its bake", bake.baked(a) and len(a.elements) == 12, len(a.elements))

    # Editing the move puts the still back (and it needs baking again).
    shots.set_card(sc, a, (6.0, 0.0, 0.0), (0, 0, 0), 1.0, 31)
    bake.check(sc)
    a = get(a_name)
    h.check("changing its keys puts its still back", not bake.baked(a) and len(a.elements) == 1
            and a.elements[0].filename == still and abs(a.transform.scale_x - scale) < 1e-6
            and (clips.start(a), clips.end(a)) == (20, 32), (len(a.elements), a.elements[0].filename))
    bake._forget()
    h.check("...and it needs baking again", [s.name for s in bake.needs(sc)] == [a_name])
    with h.override('VIEW_3D'):
        bpy.ops.plastron.bake()
    yield 0.3
    a = get(a_name)
    ripple.trim(sc, a, 'RIGHT', 28)
    h.module("timeline.events").clips_changed(sc)
    yield 0.8
    a = get(a_name)
    h.check("trimming a baked clip puts its still back (its length changed)",
            not bake.baked(a) and len(a.elements) == 1 and clips.end(a) == 28, (len(a.elements), clips.end(a)))

    # Painting on a baked panel: the still is re-made, the bake goes.
    with h.override('VIEW_3D'):
        bpy.ops.plastron.bake()
    yield 0.3
    a = get(a_name)
    h.check("(baked again)", bake.baked(a))
    paint(a)
    a = get(a_name)
    h.check("painting on it: its still is re-made, the bake goes", not bake.baked(a) and len(a.elements) == 1
            and panel_cache.is_own(a.elements[0].filename, a.plastron_panel.uid))

    # The flat canvas (3D Camera off): the 2D camera's move, flattened per frame.
    h.flat_canvas()
    yield 0.5
    b = get(b_name)
    b.plastron_motion.end.x = 30.0
    b.plastron_motion.end.zoom = 1.5
    bake._forget()
    h.check("flat canvas: a 2D camera move needs baking", b_name in [s.name for s in bake.needs(sc)])
    with h.override('VIEW_3D'):
        bpy.ops.plastron.bake()
    yield 0.3
    b = get(b_name)
    size0, px0 = frame_pixels(b, 0)
    size1, px1 = frame_pixels(b, 11)
    h.check("...baked: a picture per frame, the camera moving over the painting",
            bake.baked(b) and len(b.elements) == 12 and np.abs(px0 - px1).max() > 0.2,
            (len(b.elements), np.abs(px0 - px1).max()))

    import time
    cfg.BAKE_SIZE = (1280, 720)          # (timing at the real size, both ways)
    for three, name in ((True, a_name), (False, b_name)):
        bpy.context.window_manager.plastron_canvas_3d = three
        yield 0.5
        bake.unbake(get(name))
        bake._forget()
        t0 = time.monotonic()
        with h.override('VIEW_3D'):
            bpy.ops.plastron.bake()
        n = len(get(name).elements)
        print("BAKETIME", "3d" if three else "2d", n, round((time.monotonic() - t0) / n, 3), "s per frame")
        h.check(f"({'3D' if three else 'flat'} bake at 1280x720)", bake.baked(get(name)), n)
    cfg.BAKE_SIZE = (160, 90)
    yield 0.5
    h.check("switching the 3D Camera off: a 3D bake no longer matches what the canvas shows, its still is back",
            not bake.baked(get(a_name)))
    h.screenshot("bake_button")

    # Exports play the baked frames (not one still from the panel's start).
    swapped = animatic._panel_frames(sc, bpy.app.tempdir, (320, 180))
    h.check("exports leave baked panels playing their frames", b_name not in swapped and len(get(b_name).elements) == 12,
            list(swapped))
    animatic._put_back(sc, swapped)

    # Saving keeps the frames in use and tidies the rest.
    path = os.path.join(bpy.app.tempdir, "bake_test.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    yield 0.5
    b = get(b_name)
    folder = bpy.path.abspath(b.directory)
    on_disk = sorted(n for n in os.listdir(folder) if n.startswith("bake_"))
    h.check("save: the baked panel's frames move into the project's folder with it",
            bake.baked(b) and len(b.elements) == 12 and folder.startswith(os.path.dirname(path))
            and all(os.path.exists(os.path.join(folder, e.filename)) for e in b.elements), (folder, on_disk[:3]))
    h.check("...old frames no clip uses are tidied away",
            set(on_disk) <= {e.filename for e in b.elements}, (len(on_disk), len(b.elements)))


h.run(steps())
