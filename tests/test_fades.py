"""Fades: per-clip fade in / out (opacity; a sound's volume up to its mix
volume), corner handles on the timeline, Ctrl+D dip at a cut, split /
delete / moves keep the keyframes right."""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")
fades = h.module("timeline.fades")
events = h.module("timeline.events")
panels = h.module("features.storyboard.panels")


def sound_file():
    path = os.path.join(bpy.app.tempdir, "fade.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\0\0" * 24000 * 10)
    return path


def value_at(scene, strip, frame):
    scene.frame_set(frame)
    return getattr(strip, fades.prop_of(strip))


def steps():
    yield 1.0
    sc = bpy.context.scene
    p1 = panels.all_panels(sc)[0]
    ch = p1.channel
    p2 = panels.create(sc, ch, clips.end(p1), 48)
    events.clips_changed(sc)
    yield 0.2

    fades.set_fade(sc, p1, 'IN', 12)
    s = clips.start(p1)
    h.check("fade in: the picture goes from nothing to its opacity over the fade",
            abs(value_at(sc, p1, s)) < 1e-4 and abs(value_at(sc, p1, s + 6) - 0.5) < 0.05
            and abs(value_at(sc, p1, s + 12) - 1.0) < 1e-4 and abs(value_at(sc, p1, s + 30) - 1.0) < 1e-4,
            [round(value_at(sc, p1, f), 3) for f in (s, s + 6, s + 12, s + 30)])
    p1.plastron.opacity = 0.6
    yield 0.2
    h.check("...up to the clip's own opacity", abs(value_at(sc, p1, s + 30) - 0.6) < 1e-4,
            value_at(sc, p1, s + 30))
    p1.plastron.opacity = 1.0
    fades.set_fade(sc, p2, 'OUT', 10)
    e = clips.end(p2)
    h.check("fade out: down to nothing at the clip's end",
            abs(value_at(sc, p2, e - 10) - 1.0) < 1e-4 and value_at(sc, p2, e - 1) < 0.15,
            [round(value_at(sc, p2, f), 3) for f in (e - 10, e - 5, e - 1)])

    # Moving the clip: its fade goes with it.
    clips.apply(sc, {p2: (clips.start(p2) + 20, clips.end(p2) + 20)})
    events.clips_changed(sc)
    yield 0.3
    e = clips.end(p2)
    h.check("moving a clip moves its fade", abs(value_at(sc, p2, e - 10) - 1.0) < 1e-4 and value_at(sc, p2, e - 1) < 0.15,
            [round(value_at(sc, p2, f), 3) for f in (e - 10, e - 1)])

    # Sounds fade their volume, up to the mix volume (clip × track).
    voice = next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == "Voice")
    snd = clips.editor(sc).strips.new_sound("fadesnd", sound_file(), tracks.channel_of(sc, voice), 200)
    snd.right_handle = 248
    voice.volume = 0.5
    events.emit("mix_changed", sc)
    fades.set_fade(sc, snd, 'IN', 8)
    yield 0.2
    h.check("a sound fades in its volume, up to the mix volume (track at 50 %)",
            abs(value_at(sc, snd, 200)) < 1e-4 and abs(value_at(sc, snd, 220) - 0.5) < 1e-4,
            (value_at(sc, snd, 200), value_at(sc, snd, 220)))
    voice.volume = 1.0
    yield 0.2
    h.check("...and follows the mix when it changes", abs(value_at(sc, snd, 220) - 1.0) < 1e-4,
            value_at(sc, snd, 220))

    # Dragging a corner handle on the timeline.
    tl = h.area('SEQUENCE_EDITOR')
    reg = h.region(tl)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.3
    fades.set_fade(sc, p2, 'IN', 0)
    (hx, hy), _out = fades.handle_points(reg, p2)
    target = reg.view2d.view_to_region(clips.start(p2) + 16, 0, clip=False)[0]
    yield from h.drag((reg.x + hx, reg.y + hy), (reg.x + target, reg.y + hy), steps=10)
    yield 0.3
    h.check("dragging a clip's top-left handle inward sets its fade in", abs(p2.plastron.fade_in - 16) <= 1,
            p2.plastron.fade_in)
    h.check("...without moving or trimming the clip", clips.length(p2) == 48, clips.length(p2))
    h.redraw()
    yield 0.3
    h.screenshot("fades")

    # Ctrl+D: a dip on the cut at the playhead.
    p3 = panels.create(sc, ch, clips.end(p2), 48)
    events.clips_changed(sc)
    yield 0.2
    sc.frame_current = clips.start(p3)
    tracks.set_active(sc, tracks.track_of_clip(sc, p3))
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    h.key('D', ctrl=True)
    yield 0.3
    fps = sc.render.fps / sc.render.fps_base
    n = round(h.module("config.timeline").DIP_SECONDS * fps)
    h.check("Ctrl+D: the clip before the cut fades out, the one after fades in",
            p2.plastron.fade_out == n // 2 and p3.plastron.fade_in == n - n // 2,
            (p2.plastron.fade_out, p3.plastron.fade_in))

    # Split: the left half keeps the fade in, the right half the fade out.
    fades.set_fade(sc, p3, 'OUT', 6)
    right = ripple.split(sc, [p3], clips.start(p3) + 20)[0]
    yield 0.3
    h.check("split: the left half keeps the fade in, the right half gets the fade out",
            (p3.plastron.fade_in, p3.plastron.fade_out, right.plastron.fade_in, right.plastron.fade_out)
            == (n - n // 2, 0, 0, 6),
            (p3.plastron.fade_in, p3.plastron.fade_out, right.plastron.fade_in, right.plastron.fade_out))
    e = clips.end(right)
    h.check("...and plays that way", value_at(sc, right, e - 1) < 0.2 and abs(value_at(sc, p3, clips.end(p3) - 1) - 1) < 1e-4)

    gone = right.path_from_id("blend_alpha")
    ripple.delete(sc, [right])
    events.clips_changed(sc)
    yield 0.3
    left = [fc.data_path for fc in fades._bags(sc.animation_data.action)[0].fcurves] \
        if sc.animation_data and sc.animation_data.action and fades._bags(sc.animation_data.action) else []
    h.check("deleting a clip removes its fade keyframes", gone not in left, left)


h.run(steps())
