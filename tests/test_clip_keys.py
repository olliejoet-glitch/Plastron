"""Keyed card / camera moves survive ripple edits (Ollie: "the animations I
have keyframed keep jumping around and disappearing when I ripple edit
stuff"). Each clip keeps its keys in its own time (features/scene3d/shots)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

shots = h.module("features.scene3d.shots")
panels = h.module("features.storyboard.panels")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")
canvas_sync = h.module("features.storyboard.canvas_sync")


def x_at(clip, frame):
    """The card's x offset the clip shows at a timeline frame."""
    return shots.card_place(clip, frame)[0][0]


def animate(sc, clip, a, b):
    """Card x: 0 at the clip's start, 10 at its end - 1 (keyed)."""
    s, e = clips.start(clip), clips.end(clip)
    shots.key(sc, clip, shots.CARD_PROPS, s, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0))
    shots.set_card(sc, clip, (10.0, 0.0, 0.0), (0, 0, 0), 1.0, e - 1)


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
    a = panels.create(sc, ch, 1, 48)
    b = panels.create(sc, ch, 49, 48)
    c = panels.create(sc, ch, 97, 48)
    yield 0.3
    animate(sc, b, 0, 10)
    animate(sc, c, 0, 10)
    a_name, b_name, c_name = a.name, b.name, c.name
    h.check("(a keyed card: 0 at the clip's start, 10 at its end)",
            abs(x_at(b, 49)) < 1e-4 and abs(x_at(b, 96) - 10) < 1e-4 and 4 < x_at(b, 72) < 6,
            (x_at(b, 49), x_at(b, 72), x_at(b, 96)))
    h.check("...kept on the clip itself, nothing on the timeline's own keys but what the keyframe view shows",
            shots.animated(sc, b, shots.CARD_PROPS)
            and {n for (n, _p, _i) in shots._shown(sc)} <= {canvas_sync._state.get("canvas_clip")},
            sorted({n for (n, _p, _i) in shots._shown(sc)}))
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.ed.undo_push(message="keyed")

    # Ripple delete the first clip: the others move up, their moves with them.
    ripple.delete(sc, [a])
    yield 0.4
    b, c = get(b_name), get(c_name)
    h.check("ripple delete before them: the clips move up and their moves go along",
            clips.start(b) == 1 and abs(x_at(b, 1)) < 1e-4 and abs(x_at(b, 48) - 10) < 1e-4
            and abs(x_at(c, clips.start(c))) < 1e-4 and abs(x_at(c, clips.end(c) - 1) - 10) < 1e-4,
            (clips.start(b), x_at(b, 1), x_at(b, 48)))

    # Trim the start (no ripple): the picture stays where it is, so does its move.
    track.ripple = False
    at13 = x_at(b, 13)
    ripple.trim(sc, b, 'LEFT', 13)
    yield 0.4
    b = get(b_name)
    h.check("trimming a clip's start: the move stays where it was on the timeline",
            clips.start(b) == 13 and abs(x_at(b, 48) - 10) < 1e-4 and abs(x_at(b, 13) - at13) < 1e-4,
            (x_at(b, 13), at13, x_at(b, 48)))
    track.ripple = True
    # Ripple trim of the start: the cut-off start is gone, the rest starts at the clip's start.
    before = x_at(b, 25)
    ripple.trim(sc, b, 'LEFT', 25)
    yield 0.4
    b = get(b_name)
    h.check("ripple trim of the start: the clip stays, its move continues from where it was cut",
            clips.start(b) == 13 and abs(x_at(b, 13) - before) < 1e-3, (x_at(b, 13), before))
    # The end: nothing moves.
    end_before = x_at(b, clips.end(b) - 5)
    ripple.trim(sc, b, 'RIGHT', clips.end(b) - 3)
    yield 0.4
    b = get(b_name)
    h.check("trimming the end leaves the move alone", abs(x_at(b, clips.end(b) - 2) - end_before) < 1e-3
            or abs(x_at(b, clips.end(b) - 5) - end_before) < 1e-3, (end_before,))

    # Split: both halves keep their part, continuing.
    mid = (clips.start(b) + clips.end(b)) // 2
    v_mid = x_at(b, mid + 2)
    right = ripple.split(sc, [b], mid)
    yield 0.4
    b = get(b_name)
    r = right[0] if right else None
    h.check("split: the right half carries on where the move was (its own copy of the keys)",
            r is not None and abs(x_at(r, mid + 2) - v_mid) < 1e-3 and r.plastron_anim != b.plastron_anim,
            (r and x_at(r, mid + 2), v_mid))

    # Rename: the keys stay. A new clip with an old clip's name gets none.
    old_b = b.name
    b.name = "Renamed Shot"
    yield 0.3
    h.check("renaming a clip keeps its keys", shots.animated(sc, get("Renamed Shot"), shots.CARD_PROPS))
    fresh = panels.create(sc, ch, clips.end(get(c_name)), 24)
    fresh.name = old_b
    yield 0.3
    h.check("a new clip given an old clip's name gets no keys", not shots.animated(sc, get(old_b), shots.CARD_PROPS))

    # Undo puts everything back as it was (keys included).
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.ed.undo_push(message="edits")    # (the edits above were made from Python: no step of their own)
    h.move(*h.center(h.region(h.area('SEQUENCE_EDITOR'))))
    h.key('Z', ctrl=True)                   # (edits made from Python: one step back to "keyed")
    yield 0.2
    yield 0.4
    sc = bpy.context.scene
    b = get(b_name)
    h.check("undo back to before the edits: the keys are where they were",
            b is not None and clips.start(b) == 49 and abs(x_at(b, 49)) < 1e-4 and abs(x_at(b, 96) - 10) < 1e-4,
            b and (clips.start(b), x_at(b, 49), x_at(b, 96)) or [(x.name, clips.start(x)) for x in clips.top_clips(sc)])

    # The keyframe view: the current clip's keys show; moving a key there moves the clip's own.
    sc.frame_current = 60
    canvas_sync.invalidate(sc)
    yield 0.6
    cur = shots._current(sc)
    shots.mirror(sc, force=True, now=True)
    shown = {k: fc for k, fc in shots._shown(sc).items() if k[0] == cur.name}
    h.check("the keyframe view shows the current clip's keys at timeline frames",
            cur.name == b_name and shown and all(round(fc.keyframe_points[-1].co[0]) == 96 for fc in shown.values()),
            [(k, [kp.co[0] for kp in fc.keyframe_points]) for k, fc in shown.items()][:2])
    fc = shown[(cur.name, "plastron_card_offset", 0)]
    fc.keyframe_points[-1].co[0] = 72
    fc.keyframe_points[-1].handle_left[0] = 70
    fc.keyframe_points[-1].handle_right[0] = 74
    fc.update()
    shots.check_mirror(sc, edited=True)      # (as a key drag in the keyframe view does)
    h.check("...moving a key there moves the clip's own key", abs(x_at(get(b_name), 72) - 10) < 1e-3,
            x_at(get(b_name), 72))

    # A real edit in the keyframe view: select the clip's keys at frame 72 and press Delete.
    sc = bpy.context.scene
    shots.mirror(sc, force=True, now=True)
    for (n, _p, _i), f in shots._shown(sc).items():
        for kp in f.keyframe_points:
            kp.select_control_point = n == b_name and round(kp.co[0]) == 72
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.ed.undo_push(message="key moved")    # (moved from Python above: no step of its own)
    keys = h.area('DOPESHEET_EDITOR')
    h.move(*h.center(h.region(keys)))
    yield 0.2
    h.key('DEL')
    yield 0.5
    left = {k: [round(kp.co[0] + shots.origin(get(b_name))) for kp in f.keyframe_points]
            for k, f in shots.curves(get(b_name)).items()}
    h.check("deleting a key in the keyframe view deletes the clip's own key",
            72 not in left.get(("plastron_card_offset", 0), [72]), left.get(("plastron_card_offset", 0)))
    h.key('Z', ctrl=True)
    yield 0.5
    h.check("...and Ctrl+Z brings it back", abs(x_at(get(b_name), 72) - 10) < 1e-3, x_at(get(b_name), 72))

    # Blender's own drag-move of a clip (what a pen drag does): the move goes along.
    sc = bpy.context.scene
    c = get(c_name)
    for x in clips.top_clips(sc):
        x.select = x == c
    c0 = clips.start(c)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.transform.seq_slide(value=(30, 0))
    yield 0.5
    c = get(c_name)
    h.check("dragging a clip along (Blender's move): its move goes with it",
            clips.start(c) != c0 and abs(x_at(c, clips.start(c))) < 1e-4
            and abs(x_at(c, clips.end(c) - 1) - 10) < 1e-4, (c0, clips.start(c), x_at(c, clips.end(c) - 1)))

    # An older project: keys kept on the timeline under the clip's name.
    old = panels.create(sc, ch, clips.end(c) + 50, 48)
    old.plastron_card_offset = (0.0, 0.0, 0.0)
    old.keyframe_insert("plastron_card_offset", frame=clips.start(old))
    old.plastron_card_offset = (6.0, 0.0, 0.0)
    old.keyframe_insert("plastron_card_offset", frame=clips.start(old) + 24)
    del sc[shots.LOCAL]
    shots.migrate_local(sc)
    h.check("an older project's keys move into the clip's own time (and off the timeline)",
            abs(x_at(old, clips.start(old) + 24) - 6) < 1e-4 and abs(x_at(old, clips.start(old))) < 1e-4
            and not any(n == old.name for (n, _p, _i) in shots._shown(sc)))

    # Save / reload keeps them.
    path = os.path.join(bpy.app.tempdir, "clip_keys.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    yield 1.0
    b = get(b_name)
    h.check("saved and opened again: the clip's keys are there", b is not None and abs(x_at(b, 72) - 10) < 1e-3
            and abs(x_at(b, 49)) < 1e-4, b and (x_at(b, 49), x_at(b, 72), b.plastron_anim,
                                                b.plastron_anim and b.plastron_anim.users,
                                                {k: [tuple(p.co) for p in fc.keyframe_points] for k, fc in shots.curves(b).items()},
                                                b.plastron_anim_anchored, b.plastron_anim_at, clips.start(b)))


h.run(steps())
