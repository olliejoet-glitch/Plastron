"""Tidying tracks (timeline/track_edit.py): no Background track in new
projects, Remove Track (the tracks above close up), the Script lane hidden
in Edit mode only (the others sit together), shown again elsewhere."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
sections = h.module("timeline.sections")


def names(sc):
    return [tracks.name(sc, t) for t in tracks.all_tracks(sc)]


def steps():
    yield 1.0
    sc = bpy.context.scene
    h.check("new projects have no Background track", "Background" not in names(sc), names(sc))
    wm = bpy.context.window_manager

    # Remove Track: add a video track with a clip on Music's... remove the Music track.
    music = next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == "Music")
    tracks.set_active(sc, music)
    before = names(sc)
    panel_ch = tracks.channel_of(sc, tracks.video_tracks(sc)[0])
    panel_clips = [s.name for s in clips.on_channel(sc, panel_ch)]
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.track_remove()
    yield 0.3
    sc = bpy.context.scene
    h.check("Remove Track takes the active track away", names(sc) == [n for n in before if n != "Music"], names(sc))
    new_ch = tracks.channel_of(sc, tracks.video_tracks(sc)[0])
    h.check("...and the tracks above close up, clips and all",
            new_ch == panel_ch - 1 and [s.name for s in clips.on_channel(sc, new_ch)] == panel_clips,
            (panel_ch, new_ch, [s.name for s in clips.on_channel(sc, new_ch)]))

    # Script lane: hidden in Edit mode.
    wm.plastron_mode = 'Edit'
    yield 1.0
    sc.plastron_timeline.script_hidden_edit = True
    yield 0.5
    lane = tracks.script_track(sc)
    shown = [tracks.name(sc, t) for _i, t in tracks.visible_tracks(sc)]
    h.check("Edit mode: the Script eye hides the Script lane", lane.hidden and "Script" not in shown, shown)
    order = [t.kind for t in tracks.all_tracks(sc)]
    h.check("...parked above the others, so they sit together (video right above audio)",
            order[-1] == 'SCRIPT' and order[:-1] == sorted(order[:-1], key=lambda k: k != 'AUDIO'), order)
    found, top = sections.spans(sc)
    h.check("...and its row is covered over like an unused one", 'SCRIPT' not in found)
    h.redraw()
    yield 0.3
    h.screenshot("script_hidden_edit")

    wm.plastron_mode = 'Storyboard'
    yield 1.0
    lane = tracks.script_track(sc)
    order = [t.kind for t in tracks.all_tracks(sc)]
    h.check("Storyboard mode: the Script lane is back between audio and video",
            not lane.hidden and order.index('SCRIPT') == order.count('AUDIO'), order)
    wm.plastron_mode = 'Edit'
    yield 1.0
    h.check("back in Edit mode it's hidden again", tracks.script_track(sc).hidden)
    sc.plastron_timeline.script_hidden_edit = False
    yield 0.5
    h.check("the eye shows it again", not tracks.script_track(sc).hidden)

    # A new video track while the lane is hidden goes under it.
    sc.plastron_timeline.script_hidden_edit = True
    yield 0.3
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.track_add(kind='VIDEO')
    yield 0.3
    h.check("a video track added meanwhile goes below the hidden lane",
            tracks.all_tracks(sc)[-1].kind == 'SCRIPT', [t.kind for t in tracks.all_tracks(sc)])
    wm.plastron_mode = 'Storyboard'
    yield 1.0


h.run(steps())
