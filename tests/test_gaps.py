"""Ripple delete a gap (timeline/gaps.py): click an empty stretch of a
track, Delete closes it up (every unlocked track by the same amount, as far
as all have room; else just that track and its clips' linked clips)."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
gaps = h.module("timeline.gaps")


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "gaps")
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "v.mp4")
    wav = os.path.join(folder, "m.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", movie], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=500:duration=2", wav],
                   check=True)
    a = next(s for s in media.place(sc, movie, frame=1000) if s.type == 'MOVIE')
    b = next(s for s in media.place(sc, movie, frame=1200) if s.type == 'MOVIE')
    b_sound = clips.linked(b)[0]
    a_name, b_name, snd_name = a.name, b.name, b_sound.name
    yield 0.3
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.ed.undo_push(message="clips placed")     # (placed from Python: no undo step of their own)
    gap_start, gap_end = clips.end(a), clips.start(b)
    h.check("(two videos with a gap between them)", gap_end > gap_start, (gap_start, gap_end))

    # Click in the gap (a real click on the timeline).
    area = h.area('SEQUENCE_EDITOR')
    reg = h.region(area)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.3
    v2d = reg.view2d
    x, y = v2d.view_to_region((gap_start + gap_end) / 2, a.channel + 0.5, clip=False)
    h.move(reg.x + x, reg.y + y)
    yield 0.2
    h.key('LEFTMOUSE')
    yield 0.3
    sc = bpy.context.scene
    h.check("clicking an empty stretch of a track selects the gap",
            gaps.selected(sc) == (a.channel, gap_start, gap_end), gaps.selected(sc))
    h.redraw()
    h.screenshot("gap_selected")
    width = gap_end - gap_start
    b_was, snd_was = clips.start(b), clips.start(b_sound)
    h.key('DEL')
    yield 0.4
    sc = bpy.context.scene
    b = sc.sequence_editor.strips_all[b_name]
    b_sound = sc.sequence_editor.strips_all[snd_name]
    a = sc.sequence_editor.strips_all[a_name]
    h.check("Delete closes it: the next clip moves up to the one before",
            clips.start(b) == clips.end(a) and clips.start(b) == b_was - width, (clips.start(b), clips.end(a)))
    h.check("...its sound with it (other tracks move the same)", clips.start(b_sound) == snd_was - width,
            (clips.start(b_sound), snd_was - width))
    h.check("...and the gap is let go", gaps.selected(sc) is None)
    h.key('Z', ctrl=True)
    yield 0.4
    sc = bpy.context.scene
    b = sc.sequence_editor.strips_all[b_name]
    h.check("one Ctrl+Z puts it back", clips.start(b) == b_was, clips.start(b))

    # A track with no room: only the clicked track (and linked clips) close up.
    a = sc.sequence_editor.strips_all[a_name]
    music = tracks.add(sc, 'AUDIO', track_name="Music Gap Test")
    mch = tracks.channel_of(sc, music)
    m1 = clips.editor(sc).strips.new_sound("m1", wav, mch, clips.start(a) + 160)
    m2 = clips.editor(sc).strips.new_sound("m2", wav, mch, clips.end(m1))
    yield 0.3
    sc = bpy.context.scene
    m2 = sc.sequence_editor.strips_all["m2"]
    a = sc.sequence_editor.strips_all[a_name]
    b = sc.sequence_editor.strips_all[b_name]
    h.check("(the music's second clip starts after the gap, with no room before it)",
            clips.start(m2) >= clips.start(b), (clips.start(m2), clips.start(b)))
    m2_was = clips.start(m2)
    changes, d = gaps.plan(sc, a.channel, clips.end(a), clips.start(b))
    h.check("a track without room: only the gap's track (and linked clips) close up",
            d == clips.start(b) - clips.end(a) and m2 not in changes and b in changes,
            (d, [s.name for s in changes]))
    h.check("...the blocked track's clips stay", clips.start(m2) == m2_was)

    # Clicking a clip lets the gap go.
    gaps._gap.update(scene=sc.name, channel=a.channel, start=clips.end(a), end=clips.start(b))
    x, y = v2d.view_to_region((clips.start(a) + clips.end(a)) / 2, a.channel + 0.5, clip=False)
    h.move(reg.x + x, reg.y + y)
    yield 0.2
    h.key('LEFTMOUSE')
    yield 0.3
    h.check("clicking a clip lets the gap go", gaps.selected(bpy.context.scene) is None)


h.run(steps())
