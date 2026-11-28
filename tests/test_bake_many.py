"""Bake on a whole storyboard (Ollie: "baking the animation missed some
animations at the start of my storyboard"): every kind of move baked, by the
button (modal, as Ollie runs it), and they stay baked afterwards."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

bake = h.module("features.motion.bake")
cfg = h.module("config.motion")
shots = h.module("features.scene3d.shots")
scene3d = h.module("features.scene3d")
panels = h.module("features.storyboard.panels")
panel_cache = h.module("features.storyboard.panel_cache")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")
events = h.module("timeline.events")

cfg.BAKE_SIZE = (160, 90)
N = 12


def paint(strip):
    mat = strip.plastron_panel.material
    img = mat.plastron_stack.layers[0].paint_image
    w, hh = img.size
    a = np.zeros((hh, w, 4), np.float32)
    a[hh // 3:hh // 2, w // 3:w // 2] = (0.1, 0.1, 0.1, 1.0)
    img.pixels.foreach_set(a.ravel())
    img.update()
    panel_cache.request(mat)


def state(sc, names):
    sed = sc.sequence_editor
    return {n: (bake.baked(sed.strips_all[n]), len(sed.strips_all[n].elements)) for n in names}


def steps():
    yield 1.0
    sc = bpy.context.scene
    track = next(t for t in tracks.video_tracks(sc) if t.ripple)
    ch = tracks.channel_of(sc, track)
    for s in list(clips.on_channel(sc, ch)):
        ripple.remove(sc, s)
    yield 0.3
    sc = bpy.context.scene
    made = [panels.create(sc, ch, 1 + i * N, N) for i in range(6)]
    yield 0.3
    for s in made:
        paint(s)
    panel_cache.flush_now()
    yield 0.3
    names = [s.name for s in made]
    get = lambda n: bpy.context.scene.sequence_editor.strips_all[n]  # noqa: E731
    loc, rot = scene3d.rest_pose()
    # 0: card keys · 1: camera keys · 2: a moving layer · 3: card + camera ·
    # 4: nothing · 5: camera keyed by moving the 3D camera at the playhead
    a = get(names[0])
    shots.key(sc, a, shots.CARD_PROPS, 1, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0))
    shots.set_card(sc, a, (3.0, 0.0, 0.0), (0, 0, 0), 1.0, N)
    b = get(names[1])
    shots.set_camera(sc, b, tuple(loc), tuple(rot), 35.0, N + 1)
    shots.set_camera(sc, b, tuple(loc + type(loc)((2.0, 0.0, 0.0))), tuple(rot), 35.0, 2 * N)
    c = get(names[2])
    lay = c.plastron_panel.material.plastron_stack.layers[0]
    lay.move_start = (0.0, 0.0)
    lay.move_end = (400.0, 0.0)
    d = get(names[3])
    shots.key(sc, d, shots.CARD_PROPS, 3 * N + 1, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0))
    shots.set_card(sc, d, (0.0, 2.0, 0.0), (0, 0, 0), 1.0, 4 * N)
    shots.set_camera(sc, d, tuple(loc), tuple(rot), 35.0, 3 * N + 1)
    shots.set_camera(sc, d, tuple(loc), tuple(rot), 50.0, 4 * N)
    events.clips_changed(sc)
    yield 3.0                                      # (pending stills / fits settle, as after real edits)
    bake._forget()
    want = [names[i] for i in (0, 1, 2, 3)]
    h.check("(the animated ones need baking)", sorted(s.name for s in bake.needs(sc)) == sorted(want),
            [s.name for s in bake.needs(sc)])
    h.redraw()
    yield 0.3
    with h.override('VIEW_3D'):
        bpy.ops.plastron.bake('INVOKE_DEFAULT')
    for _ in range(600):
        yield 0.1
        if not bake._state["running"]:
            break
    yield 0.5
    sc = bpy.context.scene
    print("AFTER BAKE", state(sc, names))
    h.check("the button bakes every animated panel", all(state(sc, want)[n] == (True, N) for n in want),
            state(sc, names))
    events.clips_changed(sc)
    yield 4.0                                      # (anything waiting: still re-makes, checks, fits)
    sc = bpy.context.scene
    bake._forget()
    print("LATER", state(sc, names), [s.name for s in bake.needs(sc)])
    h.check("...and they stay baked (nothing left to do)",
            all(state(sc, want)[n] == (True, N) for n in want) and bake.needs(sc) == [],
            (state(sc, names), [s.name for s in bake.needs(sc)]))
    # Scrubbing / playing over them doesn't undo the bake either.
    for f in range(1, 6 * N, 5):
        sc.frame_set(f)
        yield 0.05
    events.clips_changed(sc)
    yield 2.0
    sc = bpy.context.scene
    bake._forget()
    h.check("...also after scrubbing over them", all(state(sc, want)[n] == (True, N) for n in want)
            and bake.needs(sc) == [], (state(sc, names), [s.name for s in bake.needs(sc)]))


    # Several tracks (the multiplane): a still panel on top of a lower
    # track's panel whose card moves. Edit mode shows the top picture, so it
    # carries the lower card's move: the bake renders the canvas as it is.
    h.add_background()
    yield 0.5
    sc = bpy.context.scene
    bg = tracks.video_tracks(sc)[0]
    bch = tracks.channel_of(sc, bg)
    top = get(names[4])                          # (still, nothing of its own)
    low = panels.create(sc, bch, clips.start(top), N)
    paint(low)
    panel_cache.flush_now()
    low_name, top_name = low.name, top.name
    shots.key(sc, low, shots.CARD_PROPS, clips.start(top), ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0))
    shots.set_card(sc, low, (3.0, 0.0, 0.0), (0, 0, 0), 1.0, clips.end(top) - 1)
    events.clips_changed(sc)
    yield 1.0
    bake._forget()
    todo = sorted(s.name for s in bake.needs(bpy.context.scene))
    h.check("a still panel over a moving card on a lower track needs baking too",
            top_name in todo and low_name in todo, todo)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.bake()
    yield 0.5
    top = get(top_name)
    path = lambda i: os.path.join(bpy.path.abspath(top.directory), top.elements[i].filename)  # noqa: E731
    imgs = [bpy.data.images.load(path(i)) for i in (0, N - 1)]
    px = []
    for img in imgs:
        a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(a)
        px.append(a)
        bpy.data.images.remove(img)
    h.check("...its frames show the lower card moving", bake.baked(top) and np.abs(px[0] - px[1]).max() > 0.2,
            (bake.baked(top), float(np.abs(px[0] - px[1]).max())))
    paint(get(low_name))                         # repainting the lower panel: the top one's frames are stale
    panel_cache.flush_now()
    events.clips_changed(bpy.context.scene)
    yield 1.5
    h.check("...repainting the lower panel puts the top one's still back",
            not bake.baked(get(top_name)) and not bake.baked(get(low_name)))
    # The camera keyed on the lower panel (drawn on when it was moved).
    low = get(low_name)
    shots.reset(bpy.context.scene, low, card=True, camera=True)
    sc = bpy.context.scene
    shots.set_camera(sc, low, tuple(loc), tuple(rot), 35.0, clips.start(low))
    shots.set_camera(sc, low, tuple(loc), tuple(rot), 70.0, clips.end(low) - 1)
    events.clips_changed(sc)
    yield 1.0
    bake._forget()
    h.check("a camera keyed on the lower panel: the top one needs baking", top_name in
            [s.name for s in bake.needs(bpy.context.scene)])
    h.check("...through that camera", bake.camera_clip(sc, get(top_name), clips.start(get(top_name))).name == low_name)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.bake()
    yield 0.5
    top = get(top_name)
    imgs = [bpy.data.images.load(path(i)) for i in (0, N - 1)]
    px = []
    for img in imgs:
        a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(a)
        px.append(a)
        bpy.data.images.remove(img)
    h.check("...its frames zoom in", bake.baked(top) and np.abs(px[0] - px[1]).max() > 0.2,
            float(np.abs(px[0] - px[1]).max()))


h.run(steps())
