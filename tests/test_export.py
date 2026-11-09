"""Stage 7 exports: shot list (CSV), panel sheet (PDF), animatic video (MP4)."""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

panels = h.module("features.storyboard.panels")
panel_cache = h.module("features.storyboard.panel_cache")
clips = h.module("timeline.clips")
shotlist = h.module("features.export.shotlist")
sheet = h.module("features.export.sheet")
animatic = h.module("features.export.animatic")


def steps():
    yield 1.0
    sc = bpy.context.scene
    first = panels.all_panels(sc)[0]
    second = panels.create(sc, first.channel, clips.end(first), 24)
    first.plastron_panel.note = "Wide: the forest, dusk"
    second.plastron_panel.note = "Close-up — the creature's eye (it blinks)"
    second.plastron_panel.status = "BLOCKING"
    mat = first.plastron_panel.material
    img = mat.plastron_stack.layers[0].paint_image
    w, hh = img.size
    a = np.zeros((hh, w, 4), np.float32)
    a[hh // 3:hh // 2, w // 3:w // 2] = (0.1, 0.1, 0.1, 1.0)
    img.pixels.foreach_set(a.ravel())
    img.update()
    panel_cache.request(mat)
    panel_cache.flush_now()
    out = os.path.join(bpy.app.tempdir, "exports")
    os.makedirs(out, exist_ok=True)

    path = shotlist.export(sc, os.path.join(out, "shots.csv"))
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    h.check("shot list: a header and one row per panel, in order, with notes and status",
            len(rows) == 3 and rows[1][1] == first.name and rows[2][5].startswith("Close-up")
            and rows[2][4] == "Blocking" and rows[1][2] == "00:00+00", rows)

    pdf = os.path.join(out, "sheet.pdf")
    pages = sheet.export(sc, pdf)
    data = open(pdf, "rb").read()
    h.check("panel sheet: a PDF with the panels' pictures and notes",
            data.startswith(b"%PDF-1.4") and pages == 1 and b"/Count 1" in data
            and data.count(b"/Subtype /Image") == 2 and b"Wide: the forest, dusk" in data
            and data.rstrip().endswith(b"%%EOF"), (pages, len(data)))
    many = [(None, ["x"])] * 13
    h.check("...more panels than fit go on more pages", sheet.write_pdf(os.path.join(out, "m.pdf"), many) == 3)

    mp4 = os.path.join(out, "animatic.mp4")
    before = (sc.render.resolution_x, sc.render.filepath, sc.render.image_settings.file_format)
    with h.override('SEQUENCE_EDITOR'):
        animatic.export(bpy.context, mp4, size=(320, 180), frames=(1, 12))
    yield 0.5
    ok = os.path.exists(mp4) and os.path.getsize(mp4) > 1000
    h.check("animatic: an MP4 is rendered", ok, os.path.getsize(mp4) if os.path.exists(mp4) else None)
    h.check("...and the project's render settings and pictures are put back",
            (sc.render.resolution_x, sc.render.filepath, sc.render.image_settings.file_format) == before
            and first.elements[0].filename.startswith("panel_"))

    # --- Captions (.srt) from a voice clip's transcript (on the timeline, trims, "um"s left out).
    takes = h.module("features.voice.takes")
    tracks = h.module("timeline.tracks")
    captions = h.module("features.export.captions")
    import wave
    wav = os.path.join(out, "talk.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(b"\0\0" * 48000 * 8)
    voice_track = next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == "Voice")
    vc = takes.new_clip(sc, voice_track, 25, wav, 8.0)
    fps = sc.render.fps / sc.render.fps_base
    takes.set_words(takes.active_take(vc), [
        ("Once", 0.2, 0.5), ("upon", 0.5, 0.8), ("a", 0.8, 0.9), ("time.", 0.9, 1.3),
        ("Um,", 1.4, 1.6), ("there", 2.5, 2.8), ("was", 2.8, 3.0), ("a", 3.0, 3.1),
        ("creature", 3.1, 3.6), ("living", 3.6, 3.9), ("in", 3.9, 4.0), ("the", 4.0, 4.1), ("forest", 4.1, 4.6),
        ("cut", 7.5, 7.8)])
    vc.right_handle = 25 + int(7.0 * fps)                     # ("cut" trimmed off)
    srt = os.path.join(out, "captions.srt")
    n = captions.export(sc, srt)
    text = open(srt, encoding="utf-8").read()
    start0 = (25 - sc.frame_start) / fps
    h.check("captions: lines from the transcript at their timeline times, 'um' and trimmed words left out",
            n == 2 and "Once upon a time." in text and "there was a creature living in the forest" in text
            and "Um" not in text and "cut" not in text
            and captions.stamp(start0 + 0.2) in text.splitlines()[1], text)

    # --- 4K: Export Video (YouTube 4K preset), Export Frame, a 4K video brought in.
    import json
    import subprocess
    video = h.module("features.export.video")
    names = [p["name"] for p in video.preset_list()]
    h.check("export presets: YouTube 4K first, then 1080p and a quick animatic",
            names[:3] == ["YouTube 4K", "YouTube 1080p", "Animatic (quick)"], names)

    def probe(path):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "json", path], capture_output=True, text=True).stdout
        st = json.loads(out or "{}").get("streams", [{}])[0]
        return st.get("width"), st.get("height")

    uhd = os.path.join(out, "uhd.mp4")
    with h.override('SEQUENCE_EDITOR'):
        video.export(bpy.context, uhd, video.preset_named("YouTube 4K"), frames=(1, 3))
    h.check("Export Video (YouTube 4K): a 3840×2160 video", probe(uhd) == (3840, 2160), probe(uhd))
    png = os.path.join(out, "frame.png")
    sc.frame_current = clips.start(first) + 1
    with h.override('SEQUENCE_EDITOR'):
        video.export_frame(bpy.context, png)
    img = bpy.data.images.load(png, check_existing=False)
    h.check("Export Frame: the picture at the playhead as a 3840×2160 PNG", tuple(img.size) == (3840, 2160),
            tuple(img.size))
    px = np.empty(3840 * 2160 * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(2160, 3840, 4)
    bpy.data.images.remove(img)
    at = lambda fx, fy: px[int(fy * 2160), int(fx * 3840), :3].mean()    # noqa: E731
    # The block painted at a third to a half of the painting = 29-50 % of the frame.
    h.check("...the panel at its right size and place in the 4K frame (painted block where it was drawn)",
            at(0.4, 0.4) < 0.25 and at(0.75, 0.75) > 0.5 and at(0.15, 0.15) > 0.5,
            (at(0.4, 0.4), at(0.75, 0.75), at(0.15, 0.15)))
    h.check("...render settings put back again",
            (sc.render.resolution_x, sc.render.filepath, sc.render.image_settings.file_format) == before)
    src = os.path.join(out, "in4k.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=3840x2160:rate=24:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", src],
                   check=True)
    made = h.module("features.edit.media").place(sc, src, frame=100)
    clip = made[0]
    h.check("a 4K video brought in fills the frame at its full size",
            (clip.elements[0].orig_width, clip.elements[0].orig_height) == (3840, 2160)
            and abs(clip.transform.scale_x - 1.0) < 1e-6, (clip.elements[0].orig_width, clip.transform.scale_x))


h.run(steps())
