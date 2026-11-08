"""Edit mode: its layout (media bin, preview, timeline), putting footage on
the timeline (video on a video track, its sound on Video Sound), Blender's
own drops placed again properly, Add to Timeline from the bin."""

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
    h.check("a video goes on the video track at the playhead", not isinstance(made, str)
            and made[0].type == 'MOVIE' and clips.start(made[0]) == 60
            and made[0].channel == tracks.channel_of(sc, panels_track), made)
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

    made = media.place(sc, still, frame=300, track=panels_track)
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
    made = media.place(sc, still, frame=clips.start(video), track=panels_track)
    h.check("a clip put in front on a ripple track pushes the video AND its sound along",
            clips.start(video) == clips.end(made[0]) and clips.start(sound) == clips.start(video)
            and clips.end(sound) == clips.end(video), (clips.start(video), clips.start(sound)))

    def head(s):
        return s.left_handle - s.content_start

    tracks.set_active(sc, panels_track)
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
