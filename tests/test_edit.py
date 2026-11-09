"""Edit mode: its layout (media bin, preview, timeline), putting footage on
the timeline (video on a video track, its sound on Video Sound), Blender's
own drops placed again properly, Add to Timeline from the bin."""

import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.edit")
media = h.module("features.edit.media")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
ripple = h.module("timeline.ripple")


def make_media(folder):
    """A 2 s test video (with a tone) and a picture."""
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "shot.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", movie],
                   check=True)
    still = os.path.join(folder, "still.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=red:size=320x180", "-frames:v", "1", still], check=True)
    return movie, still


def steps():
    yield 1.0
    sc = bpy.context.scene
    wm = bpy.context.window_manager
    wm.plastron_mode = 'Edit'
    yield 1.0
    kinds = sorted((a.type, getattr(a.spaces.active, "view_type", "")) for a in h.window().screen.areas)
    h.check("Edit mode: media bin, preview and timeline",
            ('FILE_BROWSER', '') in kinds and ('SEQUENCE_EDITOR', 'PREVIEW') in kinds
            and ('SEQUENCE_EDITOR', 'SEQUENCER') in kinds, kinds)
    preview = h.area('PREVIEW')
    h.check("the preview plays footage from half-size copies",
            preview.spaces.active.proxy_render_size == cfg.PREVIEW_SIZE, preview.spaces.active.proxy_render_size)
    browser = h.area('FILE_BROWSER').spaces.active
    h.check("the media bin shows thumbnails of video, sound and pictures",
            browser.params is not None and browser.params.display_type == 'THUMBNAIL'
            and browser.params.use_filter_movie and browser.params.use_filter_sound
            and not browser.params.use_filter_blender)

    folder = os.path.join(bpy.app.tempdir, "media")
    movie, still = make_media(folder)
    panels_track = tracks.track_of_clip(sc, h.module("features.storyboard.panels").all_panels(sc)[0])
    sc.frame_current = 60
    made = media.place(sc, movie, track=panels_track)
    vt = media.footage_track(sc)
    h.check("a video meant for the Panels track goes on the Video track instead (they never share)",
            not isinstance(made, str) and made[0].type == 'MOVIE' and clips.start(made[0]) == 60
            and made[0].channel == tracks.channel_of(sc, vt) and tracks.name(sc, vt) == cfg.VIDEO_TRACK, made)
    video, sound = made[0], made[1] if len(made) > 1 else None
    vs = media.sound_track(sc)
    h.check("...its sound on the Video Sound track, the same length",
            sound is not None and sound.channel == tracks.channel_of(sc, vs)
            and clips.start(sound) == 60 and clips.length(sound) == clips.length(video) == 48,
            sound and (sound.channel, clips.start(sound), clips.length(sound), clips.length(video)))
    h.check("...marked as media, half-size copies on", media.is_media(video) and media.is_media(sound)
            and video.use_proxy and video.proxy.build_50)

    # Clips other code makes (not a drop) are left alone.
    raw = clips.editor(sc).strips.new_sound("raw", movie, 9, 900)
    h.module("timeline.events").clips_changed(sc)
    yield 0.3
    h.check("clips made by other code aren't taken for drops", "raw" in clips.editor(sc).strips_all)
    clips.editor(sc).strips.remove(raw)

    made = media.place(sc, still, frame=300, track=vt)
    fps = sc.render.fps / sc.render.fps_base
    h.check("a picture lasts STILL_SECONDS", not isinstance(made, str)
            and clips.length(made[0]) == round(cfg.STILL_SECONDS * fps), made)

    # Add to Timeline from the bin: the selected file at the playhead.
    browser.params.directory = folder.encode() if isinstance(browser.params.directory, bytes) else folder
    browser.params.filename = "shot.mp4"
    sc.frame_current = 500
    before = len(clips.all_clips(sc))
    with h.override('FILE_BROWSER'):
        bpy.ops.plastron.media_add()
    yield 0.3
    h.check("Add to Timeline puts the selected file at the playhead",
            len(clips.all_clips(sc)) == before + 2
            and any(s.type == 'MOVIE' and clips.start(s) == 500 for s in clips.all_clips(sc)))

    # A real drag from the media bin onto the timeline (Blender's own drop,
    # then placed properly): a folder with just the video, its first thumbnail.
    only = os.path.join(bpy.app.tempdir, "drag")
    os.makedirs(only, exist_ok=True)
    import shutil
    shutil.copy(movie, os.path.join(only, "drag.mp4"))
    barea = h.area('FILE_BROWSER')
    browser.params.directory = only.encode() if isinstance(browser.params.directory, bytes) else only
    with h.override('FILE_BROWSER'):
        bpy.ops.file.refresh()
    h.redraw()
    yield 1.0
    breg = h.region(barea)
    item = (breg.x + 61, breg.y + breg.height - 70)
    tl = h.area('SEQUENCE_EDITOR')
    treg = h.region(tl)
    # drop on the Background track (a video track) at frame ~800
    bg = next(t for t in tracks.video_tracks(sc) if tracks.name(sc, t) == "Background")
    x, y = treg.view2d.view_to_region(clips.end(max(clips.all_clips(sc), key=clips.end)) + 20,
                                      tracks.channel_of(sc, bg) + 0.5, clip=False)
    yield from h.drag(item, (treg.x + min(x, treg.width - 40), treg.y + y), steps=12)
    yield 0.5
    h.redraw()
    yield 0.5
    dragged = [s for s in clips.all_clips(sc) if s.type == 'MOVIE' and "drag" in s.name]
    h.check("dragging a file from the bin onto a track puts it there (its sound on Video Sound)",
            dragged and dragged[0].channel == tracks.channel_of(sc, bg) and media.is_media(dragged[0])
            and any(s.type == 'SOUND' and "drag" in s.name and s.channel == tracks.channel_of(sc, vs)
                    for s in clips.all_clips(sc)),
            [(s.name, s.type, s.channel) for s in clips.all_clips(sc)])

    # --- A video and its sound are linked: they move, trim, cut and go together.
    h.check("a video is linked to its sound (Blender's connected strips too)",
            clips.linked(video) == [sound] and [c.name for c in video.connections] == [sound.name],
            (clips.linked(video), [c.name for c in video.connections]))
    made = media.place(sc, still, frame=clips.start(video), track=vt)
    h.check("a clip put in front on a ripple track pushes the video AND its sound along",
            clips.start(video) == clips.end(made[0]) and clips.start(sound) == clips.start(video)
            and clips.end(sound) == clips.end(video), (clips.start(video), clips.start(sound)))

    # Clips can't be moved where they don't belong: they go back.
    events = h.module("timeline.events")
    for target, why in ((tracks.channel_of(sc, h.module("timeline.tracks").video_tracks(sc)[0]), "a sound onto a video track"),
                        (len(tracks.all_tracks(sc)) + 3, "a sound into a channel that isn't a track")):
        before = (sound.channel, clips.start(sound))
        sound.channel = target
        events.clips_changed(sc)
        yield 0.2
        h.check(f"moving {why}: it goes back", (sound.channel, clips.start(sound)) == before,
                ((sound.channel, clips.start(sound)), before))
    before = video.channel
    video.channel = tracks.channel_of(sc, panels_track)
    events.clips_changed(sc)
    yield 0.2
    h.check("moving a video onto the Panels track: it goes back", video.channel == before, video.channel)

    def head(s):
        return s.left_handle - s.content_start

    tracks.set_active(sc, vt)
    for s in clips.all_clips(sc):
        s.select = False
    start, length, h0 = clips.start(video), clips.length(video), head(video)
    sc.frame_current = start + 12
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.trim_to_playhead(side='LEFT')
    h.check("Q: the start is cut to the playhead; on a ripple track the clip stays put and "
            "the footage slides (what was at the playhead now starts the clip)",
            clips.start(video) == start and clips.length(video) == length - 12 and head(video) == h0 + 12
            and sc.frame_current == start, (clips.start(video), clips.length(video), head(video), h0))
    h.check("...its sound trimmed the same way", (clips.start(sound), clips.end(sound), head(sound))
            == (clips.start(video), clips.end(video), head(video)), (clips.start(sound), head(sound)))
    sc.frame_current = start + 20
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.trim_to_playhead(side='RIGHT')
    h.check("W: the end is cut to the playhead (sound too)",
            clips.end(video) == start + 20 and clips.end(sound) == start + 20)

    edges = sorted({e for s in clips.top_clips(sc) for e in (clips.start(s), clips.end(s))})
    sc.frame_current = start + 5
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.jump_cut(direction=1)
    h.check("Down: the playhead jumps to the next cut", sc.frame_current == min(e for e in edges if e > start + 5))
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.jump_cut(direction=-1)
        bpy.ops.plastron.jump_cut(direction=-1)
    h.check("Up: ...and back past it", sc.frame_current == max(e for e in edges if e < start), sc.frame_current)

    # Clicking the video in the timeline selects its sound too.
    tl = h.area('SEQUENCE_EDITOR')
    treg = h.region(tl)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.3
    x, y = treg.view2d.view_to_region((clips.start(video) + clips.end(video)) / 2, video.channel + 0.5, clip=False)
    h.move(treg.x + x, treg.y + y)
    yield 0.2
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.3
    h.check("clicking the video selects its sound too", video.select and sound.select,
            (video.select, sound.select))
    # A real drag of the video up into empty channels (Blender's own move): back it goes.
    before = (video.channel, sound.channel, clips.start(video))
    _x, y2 = treg.view2d.view_to_region(0, video.channel + 2.5, clip=False)
    yield from h.drag((treg.x + x, treg.y + y), (treg.x + x + 30, treg.y + y2), steps=10)
    yield 0.6
    h.check("dragging a video into a channel that isn't a track: it (and its sound) go back, at the new time",
            (video.channel, sound.channel) == before[:2] and clips.start(sound) == clips.start(video),
            ((video.channel, sound.channel, clips.start(video), clips.start(sound)), before))

    right = ripple.split(sc, [video], clips.start(video) + 10)
    h.check("splitting the video cuts its sound too; both halves stay media",
            len(right) == 2 and all(media.is_media(r) for r in right), [r.name for r in right])
    rv = next(r for r in right if r.type == 'MOVIE')
    rs = next(r for r in right if r.type == 'SOUND')
    h.check("...the right halves are linked to each other (not to the left ones)",
            clips.linked(rv) == [rs] and clips.linked(video) == [sound], (clips.linked(rv), clips.linked(video)))
    yield 0.3
    h.check("...and aren't mistaken for a new drop", rv.name in clips.editor(sc).strips_all)
    n = len(clips.all_clips(sc))
    ripple.delete(sc, [rv])
    h.check("deleting a video deletes its sound", len(clips.all_clips(sc)) == n - 2
            and rs.name not in [s.name for s in clips.all_clips(sc)] if False else len(clips.all_clips(sc)) == n - 2)

    # --- Speed: the clip (and its sound) play faster / slower; ripple closes up.
    clip = next(s for s in clips.top_clips(sc) if s.type == 'MOVIE' and clips.linked(s))
    csound = clips.linked(clip)[0]
    s0, l0 = clips.start(clip), clips.length(clip)
    after = [s for s in clips.on_channel(sc, clip.channel) if clips.start(s) >= clips.end(clip)]
    nxt0 = clips.start(after[0]) if after else None
    for s in clips.all_clips(sc):
        s.select = s in (clip, csound)
    sc.sequence_editor.active_strip = clip
    with h.override('PREVIEW'):
        bpy.ops.plastron.clip_speed(speed=2.0)
    h.check("2x speed: the clip (and its sound) half as long, same start",
            clips.start(clip) == s0 and clips.length(clip) == round(l0 / 2)
            and (clips.start(csound), clips.end(csound)) == (clips.start(clip), clips.end(clip))
            and abs(clip['plastron_speed'] - 2.0) < 1e-6,
            (clips.start(clip), clips.length(clip), l0, clips.length(csound)))
    if after:
        h.check("...on a ripple track the next clip closes up", clips.start(after[0]) == nxt0 - (l0 - clips.length(clip)),
                (clips.start(after[0]), nxt0))
    with h.override('PREVIEW'):
        bpy.ops.plastron.clip_speed(speed=1.0)
    h.check("...and back to normal speed", clips.length(clip) == l0 and clips.length(csound) == l0,
            (clips.length(clip), l0))
    h.check("a sped-up voice keeps its pitch", csound.pitch_correction)

    # --- The preview: a box around the selected clip; drag to move / size / turn it.
    fb = h.module("features.edit.frame_box")
    pv = h.area('PREVIEW')
    sc.frame_current = clips.start(clip) + 2
    for s_ in clips.all_clips(sc):
        s_.select = s_ in (clip, csound)
    sc.sequence_editor.active_strip = clip
    with h.override('PREVIEW', 'PREVIEW'):
        bpy.ops.sequencer.view_all_preview()
        bpy.ops.view2d.zoom_out()           # (room around the picture for the corners)
        bpy.ops.view2d.zoom_out()
    h.redraw()
    yield 0.5
    preg = h.region(pv, 'PREVIEW')
    t = clip.transform

    def at(p):
        q = fb.to_region(preg, p)
        return preg.x + q.x, preg.y + q.y

    corners = fb.corners_view(clip)
    centre = (corners[0] + corners[2]) / 2
    start = at(centre + (corners[1] - centre) * 0.3)
    yield from h.drag(start, (start[0] + 60, start[1] + 20), steps=10)
    yield 0.3
    h.check("dragging inside the clip's box moves it", t.offset_x > 100 and t.offset_y > 20, (t.offset_x, t.offset_y))
    sx0 = t.scale_x
    corners = fb.corners_view(clip)
    c2 = at(corners[0])                     # (bottom-left: still on screen after the move)
    centre_r = at((corners[0] + corners[2]) / 2)
    yield from h.drag(c2, (centre_r[0] + (c2[0] - centre_r[0]) * 0.5, centre_r[1] + (c2[1] - centre_r[1]) * 0.5),
                      steps=10)
    yield 0.3
    h.check("dragging a corner sizes it (keeping its shape)",
            abs(t.scale_x / sx0 - 0.5) < 0.08 and abs(t.scale_x / t.scale_y - 1.0) < 1e-3, (sx0, t.scale_x, t.scale_y))
    corners = fb.corners_view(clip)
    centre_v = (corners[0] + corners[2]) / 2
    right_mid = (corners[1] + corners[2]) / 2
    out = at(centre_v + (right_mid - centre_v) * 1.15)
    centre_r = at(centre_v)
    up = (centre_r[0], centre_r[1] + (out[0] - centre_r[0]))
    yield from h.drag(out, up, steps=12, shift=True)
    yield 0.3
    h.check("dragging just outside turns it (Shift: 15° steps)", abs(math.degrees(t.rotation) - 90) < 0.5,
            math.degrees(t.rotation))
    h.redraw()
    yield 0.5
    h.screenshot("edit_clip_panel")
    with h.override('PREVIEW'):
        bpy.ops.plastron.clip_reset_frame()
    h.check("Reset Position puts it back: in the middle, filling the frame, not turned",
            (t.offset_x, t.offset_y, t.rotation) == (0, 0, 0) and abs(t.scale_x - sx0) < 1e-4
            and abs(t.scale_y - sx0) < 1e-4, (t.offset_x, t.scale_x, sx0))

    # Colour coding: the selected clip and its linked sound take the colour.
    tagged = next(s_ for s_ in clips.top_clips(sc) if s_.type == 'MOVIE' and clips.linked(s_))
    for s_ in clips.all_clips(sc):
        s_.select = s_ == tagged
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.clip_color(tag='COLOR_03')
    h.check("colour-coding a clip colours it and its linked sound",
            tagged.color_tag == 'COLOR_03' and all(o.color_tag == 'COLOR_03' for o in clips.linked(tagged)))
    tl_space = h.area('SEQUENCE_EDITOR').spaces.active
    h.check("clips show pictures all along them, and their colours",
            tl_space.timeline_overlay.thumbnail_display_style == 'CONTINUOUS'
            and tl_space.timeline_overlay.show_strip_tag_color)

    # Zooming the timeline keeps what's under the pen where it is (Ollie).
    tl = h.area('SEQUENCE_EDITOR')
    treg = h.region(tl)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 0.3
    px, py = treg.x + int(treg.width * 0.85), treg.y + int(treg.height * 0.3)
    under = treg.view2d.region_to_view(px - treg.x, py - treg.y)
    h.move(px, py)
    yield 0.2
    for key in ('WHEELUPMOUSE', 'WHEELUPMOUSE', 'EQUAL'):
        if key == 'EQUAL':
            h.key('EQUAL', ctrl=True)
        else:
            h._event(key, 'PRESS')
        yield 0.2
    after = treg.view2d.region_to_view(px - treg.x, py - treg.y)
    span = treg.view2d.region_to_view(treg.width, 0)[0] - treg.view2d.region_to_view(0, 0)[0]
    h.check("zooming in on the timeline keeps the frame and track under the pen",
            abs(after[0] - under[0]) < span * 0.05 and abs(after[1] - under[1]) < 1.0, (under, after, span))

    with h.override('PREVIEW'):
        bpy.ops.sequencer.view_all_preview()
    sc.frame_current = 70
    h.redraw()
    yield 1.0
    h.screenshot("edit_mode")
    wm.plastron_mode = 'Storyboard'
    yield 0.5
    h.check("back to Storyboard: the canvas again", h.area('VIEW_3D') is not None)


h.run(steps())
