"""Clips cut differently, linked (timeline/link.link_matching): Ollie
separated a recording's ums, then linked it to its video. Ctrl+Alt+L cuts
the video to match and links piece by piece; Separate again does the same."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
ripple = h.module("timeline.ripple")
ums = h.module("features.voice.ums")
takes = h.module("features.voice.takes")


def spans(group):
    return [(clips.start(x), clips.end(x)) for x in group]


def on(scene, channel):
    return sorted((s for s in clips.top_clips(scene) if s.channel == channel), key=clips.start)


def setup(sc, folder, name, frame):
    """A long video over its own sound in three pieces (the middle one an um),
    linked the wrong way: all as one. (Ctrl+Alt+L unlinks first, then links
piece by piece.)"""
    movie = os.path.join(folder, name + ".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", movie], check=True)
    made = media.place(sc, movie, frame=frame)
    v = next(s for s in made if s.type == 'MOVIE')
    snd = next(s for s in made if s.type == 'SOUND')
    clips.unlink_all([v, snd])
    s0 = clips.start(v)
    ripple.split(sc, [snd], s0 + 30)
    um = ripple.split(sc, [snd], s0 + 20)[0]
    um[ums.MARK] = 1
    group = [v] + on(sc, snd.channel)
    clips.link(group)
    return v.name, v.channel, snd.channel, s0, clips.end(v)


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "match")
    os.makedirs(folder, exist_ok=True)
    v_name, vch, sch, s0, s1 = setup(sc, folder, "a", 100)
    h.check("(a long video linked to its sound's three pieces as one)",
            len(on(sc, vch)) == 1 and len(on(sc, sch)) == 3 and len(clips.linked(on(sc, vch)[0])) == 3)

    for s in clips.top_clips(sc):
        s.select = s.channel in (vch, sch)
    area = h.area('SEQUENCE_EDITOR')
    reg = h.region(area)
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    h.key('L', ctrl=True, alt=True)
    yield 0.4
    sc = bpy.context.scene
    h.check("Ctrl+Alt+L on linked clips unlinks them first (nothing cut)",
            len(on(sc, vch)) == 1 and not any(s.get(clips.LINK) or len(s.connections) for s in clips.top_clips(sc)
                                              if s.channel in (vch, sch)))
    for s in clips.top_clips(sc):
        s.select = s.channel in (vch, sch)
    h.key('L', ctrl=True, alt=True)
    yield 0.4
    sc = bpy.context.scene
    vids, sounds = on(sc, vch), on(sc, sch)
    h.check("...again (now not linked), on clips cut differently: cuts the video to match", spans(vids) == spans(sounds),
            (spans(vids), spans(sounds)))
    h.check("...and links them piece by piece",
            all(clips.linked(a) == [b] for a, b in zip(vids, sounds)),
            [[x.name for x in clips.linked(a)] for a in vids])
    h.check("...the um's picture is marked as an um too", bool(vids[1].get(ums.MARK)))
    ums.delete(sc)
    yield 0.3
    sc = bpy.context.scene
    vids, sounds = on(sc, vch), on(sc, sch)
    h.check("Delete takes the um with its picture; the rest still line up (ripple)",
            len(vids) == 2 and spans(vids) == spans(sounds) and spans(vids)[-1][1] == s1 - 10,
            (spans(vids), spans(sounds)))

    # Separate run again after linking: the video is cut to match (Ollie:
    # "run the search and cut thing more than once").
    for s in clips.top_clips(sc):
        ripple.remove(sc, s) if s.channel in (vch, sch) else None
    yield 0.2
    sc = bpy.context.scene
    v_name, vch, sch, s0, s1 = setup(sc, folder, "b", 100)
    sound_pieces = on(sc, sch)
    take = takes._add_take(sound_pieces[0], sound_pieces[0].sound, 3.0)
    fps = sc.render.fps / sc.render.fps_base
    rel = lambda f: (f - sound_pieces[0].content_start) / fps     # noqa: E731
    takes.set_words(take, [["hello", rel(s0 + 2), rel(s0 + 16)], ["um", rel(s0 + 21), rel(s0 + 29)],
                           ["there", rel(s0 + 34), rel(s0 + 60)]])
    for p in sound_pieces[1:]:            # (split pieces share the recording's take)
        p.plastron_voice.takes.clear()
        t = takes._add_take(p, p.sound, 3.0)
        t.uid, t.words_json = take.uid, take.words_json
    ums._dirty()
    ums.separate(sc)
    yield 0.3
    sc = bpy.context.scene
    vids, sounds = on(sc, vch), on(sc, sch)
    h.check("Separate again on clips linked since: the video is cut to match too",
            spans(vids) == spans(sounds), (spans(vids), spans(sounds)))
    um_a, um_b = ums.word_span(sc, sounds[0], take, 1) if hasattr(ums, "word_span") else (s0 + 19, s0 + 32)
    chosen = {s.name for s in clips.top_clips(sc) if s.select}
    inside = {s.name for s in vids + sounds if s.get(ums.MARK)}
    h.check("...the um's pieces (picture and sound) are the selected ones, nothing else",
            chosen == inside and len(inside) >= 2 and all(s.get(ums.MARK) == linked_mark
                                                              for s in vids for linked_mark in
                                                              [clips.linked(s)[0].get(ums.MARK)]),
            (sorted(chosen), sorted(inside)))
    h.check("...the picture before the um isn't marked (the test tone after the last word counts as an unworded sound)",
            not vids[0].get(ums.MARK), (spans(vids),))
    before = spans(vids)
    ums.separate(sc)
    yield 0.2
    sc = bpy.context.scene
    h.check("...and a third time changes nothing", spans(on(sc, vch)) == before, spans(on(sc, vch)))


h.run(steps())
