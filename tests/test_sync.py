"""Linked sound stays in sync with its picture (timeline/sync.py, ripple):
drift is spotted and Resync puts it back; a ripple trim of a sound piece
linked to a longer video keeps them in step; the chain button unlinks a
selection from several link groups."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")
sync = h.module("timeline.sync")


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "sync")
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "v.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=8",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=8", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", movie], check=True)
    v = next(s for s in media.place(sc, movie, frame=100) if s.type == 'MOVIE')
    snd = clips.linked(v)[0]
    v_name, s_name = v.name, snd.name
    yield 0.4
    sc = bpy.context.scene
    h.check("(a placed video and its sound start their media together: in sync)", not sync.drifted(sc),
            sync.drifted(sc))

    # Drift it: the sound's media slid 10 frames under it.
    snd = sc.sequence_editor.strips_all[s_name]
    clips.apply(sc, {snd: (clips.start(snd), clips.end(snd) - 12, snd.content_start - 10)})
    yield 0.4
    sc = bpy.context.scene
    bad = sync.drifted(sc)
    h.check("a sound slid under its picture is spotted (10 frames off)",
            len(bad) == 1 and abs(abs(bad[0][2]) - 10) < 0.6, [(s.name, p.name, o) for s, p, o in bad])
    h.check("...the header shows it (cached per timeline change)", len(sync.drifted_cached(sc)) == 1)
    span = (clips.start(snd), clips.end(snd))
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.clip_resync()
    yield 0.4
    sc = bpy.context.scene
    snd = sc.sequence_editor.strips_all[s_name]
    v = sc.sequence_editor.strips_all[v_name]
    h.check("Resync puts it back under its picture (the clip stays put)",
            not sync.drifted(sc) and abs(snd.content_start - v.content_start) < 0.6
            and (clips.start(snd), clips.end(snd)) == span, (snd.content_start, v.content_start))

    # A sound piece linked to a longer video: a ripple trim of its start keeps them in step.
    clips.unlink_all([v, snd])
    right = snd.split(frame=clips.start(snd) + 60, split_method='SOFT')
    yield 0.3
    sc = bpy.context.scene
    v = sc.sequence_editor.strips_all[v_name]
    piece = right if right is not None else None
    clips.link([v, piece])
    for t in tracks.all_tracks(sc):
        t.ripple = True
    yield 0.3
    h.check("(a sound piece linked to a longer video)",
            piece is not None and (clips.start(piece), clips.end(piece)) != (clips.start(v), clips.end(v))
            and not sync.drifted(sc))
    ripple.trim(sc, piece, 'LEFT', clips.start(piece) + 12)
    yield 0.4
    sc = bpy.context.scene
    h.check("ripple-trimming the sound piece's start keeps it in sync with the video",
            not sync.drifted(sc), [(s.name, p.name, o) for s, p, o in sync.drifted(sc)])

    # The chain button unlinks a selection from several link groups (it used to link them all).
    v2 = next(s for s in media.place(sc, movie, frame=clips.end(v) + 200) if s.type == 'MOVIE')
    yield 0.3
    sc = bpy.context.scene
    v = sc.sequence_editor.strips_all[v_name]
    group = [v, piece, v2] + clips.linked(v2)
    for s in clips.top_clips(sc):
        s.select = s in group
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.clip_link()
    yield 0.3
    h.check("the chain button on clips from two link groups unlinks them all",
            not any(s.get(clips.LINK) or len(s.connections) for s in group),
            [(s.name, s.get(clips.LINK), len(s.connections)) for s in group])


h.run(steps())
