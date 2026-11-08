"""Info windows (Edit mode): a clip with its own timeline inside a UI frame;
clips put inside fill the frame's opening; Tab goes in and back out."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.edit")
windows = h.module("features.edit.windows")
media = h.module("features.edit.media")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")


def make_movie(folder):
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "inside.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=0xff0000:size=320x240:rate=24:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", movie], check=True)
    return movie


def render(scene, path, percentage=25):
    r = scene.render
    saved = (r.resolution_percentage, r.filepath, r.use_sequencer, r.image_settings.file_format)
    r.resolution_percentage, r.filepath, r.use_sequencer = percentage, path, True
    r.image_settings.file_format = 'PNG'
    with bpy.context.temp_override(scene=scene):
        bpy.ops.render.render(write_still=True, scene=scene.name)
    r.resolution_percentage, r.filepath, r.use_sequencer, r.image_settings.file_format = saved
    img = bpy.data.images.load(path, check_existing=False)
    w, hh = img.size
    px = np.empty(w * hh * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(hh, w, 4)


def steps():
    yield 1.0
    sc = bpy.context.scene
    wm = bpy.context.window_manager
    wm.plastron_mode = 'Edit'
    yield 1.0

    names = [n for n, _p in windows.styles()]
    h.check("the Green Book window style ships with Plastron", "Green Book" in names, names)
    path = dict(windows.styles())["Green Book"]
    (x0, y0, x1, y1), size = windows.opening(path)
    h.check("its see-through opening is found (most of it, inside the border)",
            0.0 < x0 < 0.03 and 0.97 < x1 < 1.0 and 0.02 < y0 < 0.1 and 0.85 < y1 < 0.93 and size == (2000, 941),
            ((x0, y0, x1, y1), size))

    sc.frame_current = 30
    with h.override('PREVIEW'):
        bpy.ops.plastron.window_add(style=path)
    strip = sc.sequence_editor.active_strip
    ws = strip.scene if strip is not None and strip.type == 'SCENE' else None
    h.check("Add Window: a window clip at the playhead on the Video track, half the frame's size",
            windows.is_window_clip(strip) and clips.start(strip) == 30
            and tracks.name(sc, tracks.track_of_clip(sc, strip)) == cfg.VIDEO_TRACK
            and abs(strip.transform.scale_x - cfg.WINDOW_SCALE) < 1e-6,
            strip and (strip.type, clips.start(strip)))
    h.check("...with its own timeline: Content, a locked Frame on top, a sound track",
            ws is not None and [tracks.name(ws, t) for t in tracks.all_tracks(ws)]
            == [cfg.VIDEO_SOUND_TRACK, windows.CONTENT_TRACK, windows.FRAME_TRACK]
            and windows.frame_clip(ws) is not None
            and ws.sequence_editor.channels[windows.frame_clip(ws).channel].lock,
            ws and [tracks.name(ws, t) for t in tracks.all_tracks(ws)])

    # Inside (Tab over the timeline).
    tl = h.area('SEQUENCE_EDITOR')
    h.move(*h.center(h.region(tl)))
    yield 0.2
    h.key('TAB')
    yield 0.5
    h.check("Tab: the timeline and preview show the window's own timeline",
            bpy.context.window.scene == ws and bpy.context.window.workspace.sequencer_scene == ws,
            bpy.context.window.scene.name)
    movie = make_movie(os.path.join(bpy.app.tempdir, "win"))
    made = media.place(ws, movie, frame=1)
    clip = made[0]
    content = windows._track_named(ws, windows.CONTENT_TRACK)
    h.check("a video put inside goes on Content", clip.channel == tracks.channel_of(ws, content),
            (clip.channel, tracks.channel_of(ws, content)))
    ox0, oy0, ox1, oy1 = windows.opening_rect(ws)
    t = clip.transform
    vis_w = (320 - 2 * clip.crop.min_x) * t.scale_x
    vis_h = (240 - 2 * clip.crop.min_y) * t.scale_y
    h.check("...filling the window's opening, cropped to fit",
            abs(vis_w - (ox1 - ox0)) < t.scale_x * 2 + 1 and abs(vis_h - (oy1 - oy0)) < t.scale_y * 2 + 1
            and abs(t.offset_x - (ox0 + ox1) / 2) < 1 and abs(t.offset_y - (oy0 + oy1) / 2) < 1,
            (vis_w, ox1 - ox0, vis_h, oy1 - oy0))
    yield 0.4
    pic = windows.frame_clip(ws)
    h.check("...and the frame lasts as long as what's in it",
            (clips.start(pic), clips.end(pic)) == (1, clips.end(clip)), (clips.start(pic), clips.end(pic)))
    h.redraw()
    yield 0.6
    h.screenshot("window_inside")

    # The inside, rendered: the frame's border is drawn over the red content.
    px = render(ws, os.path.join(bpy.app.tempdir, "win_inside.png"))
    hh, w = px.shape[:2]
    mid = px[hh // 2, w // 2]
    h.check("rendered: the content shows through the opening", mid[0] > 0.7 and mid[1] < 0.35 and mid[2] < 0.35, mid)

    h.key('TAB')
    yield 0.5
    h.check("Tab again: back on the main timeline", bpy.context.window.scene == sc, bpy.context.window.scene.name)
    h.check("...the window clip as long as what's inside", clips.length(strip) == ws.frame_end - ws.frame_start + 1,
            (clips.length(strip), ws.frame_start, ws.frame_end))
    sc.frame_current = clips.start(strip) + 5
    px = render(sc, os.path.join(bpy.app.tempdir, "win_main.png"))
    hh, w = px.shape[:2]
    centre, corner = px[hh // 2, w // 2], px[5, 5]
    h.check("rendered on the main picture: the window (with its content) in the middle, half size; "
            "what's under it shows around it",
            centre[0] > 0.7 and centre[1] < 0.35 and not (corner[0] > 0.7 and corner[1] < 0.35), (centre, corner))
    h.redraw()
    yield 0.6
    h.screenshot("window_outside")

    # Saved while inside a window: it opens on the main timeline again.
    for s_ in clips.all_clips(sc):
        s_.select = s_ == strip
    sc.sequence_editor.active_strip = strip
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.window_toggle()
    yield 0.3
    wm.plastron_mode = 'Storyboard'
    yield 0.4
    h.check("switching to Storyboard while inside a window steps back out first",
            not windows.is_window_scene(bpy.context.window.scene), bpy.context.window.scene.name)
    wm.plastron_mode = 'Edit'
    yield 0.4
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.window_toggle()
    yield 0.3
    path = os.path.join(bpy.app.tempdir, "win_test", "Windows.blend")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    yield
    bpy.ops.wm.open_mainfile(filepath=path)
    yield 1.0
    win = bpy.context.window
    h.check("a project saved inside a window opens on the main timeline",
            not windows.is_window_scene(win.scene) and win.workspace.sequencer_scene == win.scene,
            (win.scene.name, win.workspace.sequencer_scene.name))
    h.check("...its window still there, with what's inside",
            any(windows.is_window_clip(s) and s.scene is not None and len(s.scene.sequence_editor.strips_all) >= 3
                for s in clips.all_clips(win.scene)))


h.run(steps())
