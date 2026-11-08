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

    # Blender's own drop (as from the media bin / Windows): placed again properly.
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.movie_strip_add(filepath=movie, directory=folder + os.sep,
                                          files=[{"name": "shot.mp4"}],
                                          frame_start=200, channel=tracks.channel_of(sc, panels_track),
                                          move_strips=False)
    yield 0.3
    h.redraw()
    yield 0.5
    dropped = [s for s in clips.all_clips(sc) if media.is_media(s) and clips.start(s) == 200]
    by_type = {s.type: s for s in dropped}
    h.check("a dropped video is put on the track it was dropped on, its sound on Video Sound",
            set(by_type) == {'MOVIE', 'SOUND'}
            and by_type['MOVIE'].channel == tracks.channel_of(sc, panels_track)
            and by_type['SOUND'].channel == tracks.channel_of(sc, vs),
            [(s.type, s.channel, clips.start(s)) for s in dropped])
    h.check("...no stray clips left from the drop",
            not [s for s in clips.all_clips(sc) if not media.owned(s)])

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

    right = ripple.split(sc, [video], clips.start(video) + 24)
    h.check("splitting footage keeps both halves as media", right and media.is_media(right[0]))
    yield 0.3
    h.check("...and isn't mistaken for a new drop", right[0].name in clips.editor(sc).strips_all)

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
