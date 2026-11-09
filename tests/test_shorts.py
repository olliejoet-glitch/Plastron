"""Shorts reframing: a 9:16 box per shot (dragged in the preview), the
YouTube Shorts export (1080×1920) following each shot's box."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

shorts = h.module("features.edit.shorts")
media = h.module("features.edit.media")
video = h.module("features.export.video")
clips = h.module("timeline.clips")
ripple = h.module("timeline.ripple")


def frame_png(mp4, index, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf", f"select=eq(n\\,{index})",
                    "-frames:v", "1", out], check=True)
    img = bpy.data.images.load(out, check_existing=False)
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
    folder = os.path.join(bpy.app.tempdir, "shorts")
    os.makedirs(folder, exist_ok=True)
    pic = os.path.join(folder, "halves.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:size=320x360",
                    "-f", "lavfi", "-i", "color=c=blue:size=320x360", "-filter_complex", "hstack", "-frames:v", "1",
                    pic], check=True)
    a = media.place(sc, pic, frame=1)[0]
    clips.apply(sc, {a: (1, 13)})
    b = media.place(sc, pic, frame=13)[0]
    clips.apply(sc, {b: (13, 25)})
    sc.frame_end = 24
    h.check("the Shorts box is 9:16 of the frame's height and slides across it",
            abs(shorts.box_width(sc) - 2160 * 9 / 16) < 1e-6 and abs(shorts.travel(sc) - (3840 - 1215) / 2) < 1e-6)

    # Drag the box in the preview (shot at the playhead: b).
    wm.plastron_shorts = True
    sc.frame_current = 18
    pv = h.area('PREVIEW')
    with h.override('PREVIEW', 'PREVIEW'):
        bpy.ops.sequencer.view_all_preview()
    h.redraw()
    yield 0.4
    preg = h.region(pv, 'PREVIEW')
    c = h.center(preg)
    to = preg.view2d.view_to_region(shorts.travel(sc), 0, clip=False)[0] + preg.x
    yield from h.drag(c, (to, c[1]), steps=10)
    yield 0.3
    h.check("dragging the box right sets this shot to the right (the other shot keeps the middle)",
            shorts.short_x(b) > 0.9 and shorts.short_x(a) == 0.0, (shorts.short_x(a), shorts.short_x(b)))
    h.redraw()
    yield 0.4
    h.screenshot("shorts_box")
    a[shorts.KEY] = -1.0
    right = ripple.split(sc, [b], 20)
    h.check("...a split keeps the choice", right and abs(shorts.short_x(right[0]) - shorts.short_x(b)) < 1e-6)

    out = os.path.join(folder, "short.mp4")
    names = [p["name"] for p in video.preset_list()]
    h.check("a YouTube Shorts export preset", "YouTube Shorts" in names, names)
    with h.override('SEQUENCE_EDITOR'):
        video.export(bpy.context, out, video.preset_named("YouTube Shorts"), frames=(1, 24))
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "json", out], capture_output=True, text=True).stdout
    st = json.loads(probe or "{}").get("streams", [{}])[0]
    h.check("the Short is 1080×1920", (st.get("width"), st.get("height")) == (1080, 1920), st)
    first = frame_png(out, 3, os.path.join(folder, "f3.png"))
    later = frame_png(out, 17, os.path.join(folder, "f17.png"))
    mid1 = first[first.shape[0] // 2, first.shape[1] // 2]
    mid2 = later[later.shape[0] // 2, later.shape[1] // 2]
    h.check("each shot shows its own part: left (red), then right (blue)",
            mid1[0] > 0.6 and mid1[2] < 0.3 and mid2[2] > 0.6 and mid2[0] < 0.3, (mid1[:3], mid2[:3]))
    h.check("...and the edit is untouched afterwards (sizes, positions, no keys left)",
            sc.render.resolution_x == 3840 and abs(a.transform.offset_x) < 1e-6
            and not [fc for fc in h.module("timeline.fades")._bags(sc.animation_data.action)[0].fcurves
                     if "transform" in fc.data_path] if sc.animation_data and sc.animation_data.action else True)


h.run(steps())
