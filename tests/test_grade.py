"""Grade mode: layout (picture + scopes + timeline), a clip's grade (wheels,
brightness / contrast, saturation, white balance), looks, copy / paste,
Grade Everything."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.grade")
grade = h.module("features.grade.grade")
media = h.module("features.edit.media")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
events = h.module("timeline.events")


def render(scene, path):
    r = scene.render
    saved = (r.resolution_percentage, r.filepath, r.use_sequencer, r.image_settings.file_format)
    r.resolution_percentage, r.filepath, r.use_sequencer = 10, path, True
    r.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)
    r.resolution_percentage, r.filepath, r.use_sequencer, r.image_settings.file_format = saved
    img = bpy.data.images.load(path, check_existing=False)
    w, hh = img.size
    px = np.empty(w * hh * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(hh, w, 4)[hh // 2, w // 2]


def steps():
    yield 1.0
    sc = bpy.context.scene
    bpy.context.window_manager.plastron_mode = 'Grade'
    yield 1.0
    modes = sorted((a.type, getattr(a.spaces.active, "view_type", ""), getattr(a.spaces.active, "display_mode", ""))
                   for a in h.window().screen.areas)
    h.check("Grade mode: the picture, its scopes (waveform, vectorscope), the timeline",
            ('SEQUENCE_EDITOR', 'PREVIEW', 'IMAGE') in modes and ('SEQUENCE_EDITOR', 'PREVIEW', 'WAVEFORM') in modes
            and ('SEQUENCE_EDITOR', 'PREVIEW', 'VECTOR_SCOPE') in modes
            and any(m[1] == 'SEQUENCER' for m in modes), modes)

    folder = os.path.join(bpy.app.tempdir, "grade")
    os.makedirs(folder, exist_ok=True)
    grey = os.path.join(folder, "grey.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x606060:size=640x360",
                    "-frames:v", "1", grey], check=True)
    red = os.path.join(folder, "red.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xc03020:size=640x360",
                    "-frames:v", "1", red], check=True)
    a = media.place(sc, grey, frame=1)[0]
    b = media.place(sc, red, frame=clips.end(a))[0]
    sc.frame_current = 10
    before = render(sc, os.path.join(folder, "before.png"))
    for s in clips.all_clips(sc):
        s.select = s == a
    sc.sequence_editor.active_strip = a
    with h.override('PREVIEW'):
        bpy.ops.plastron.grade_start()
    h.check("Grade This Clip: the clip gets its colour wheels", grade.is_graded(a))
    ui = h.region(h.area('PREVIEW'), 'UI')
    h.check("Grade mode's sidebar shows the Grade panel (on the Clip tab, alone)",
            ui.active_panel_category == "Clip", ui.active_panel_category)
    grade.mods(a)['COLOR_BALANCE'].color_balance.gain = (1.5, 1.5, 1.5)
    after = render(sc, os.path.join(folder, "after.png"))
    h.check("lifting the highlights wheel brightens the clip", after[0] > before[0] + 0.05, (before[:3], after[:3]))
    h.redraw()
    yield 0.6
    h.screenshot("grade_mode")

    with h.override('PREVIEW'):
        bpy.ops.plastron.grade_look(look="Night")
    v = grade.values(a)
    h.check("a look (Night): bluer, darker, less saturated", v["gain"][2] > v["gain"][0] and v["saturation"] < 1,
            v)
    with h.override('PREVIEW'):
        bpy.ops.plastron.grade_copy()
    for s in clips.all_clips(sc):
        s.select = s == b
    sc.sequence_editor.active_strip = b
    with h.override('PREVIEW'):
        bpy.ops.plastron.grade_paste()
    h.check("copy / paste a grade onto another clip", grade.values(b)["gain"] == v["gain"]
            and abs(grade.values(b)["saturation"] - v["saturation"]) < 1e-6)
    with h.override('PREVIEW'):
        bpy.ops.plastron.grade_reset()
    h.check("Reset Grade: back to neutral", grade.values(b)["gain"] == [1, 1, 1] and grade.values(b)["saturation"] == 1)

    with h.override('PREVIEW'):
        bpy.ops.plastron.grade_everything()
    everything = grade.everything_clip(sc)
    gt = next((t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == cfg.GRADE_TRACK), None)
    ends = max(clips.end(s) for s in clips.top_clips(sc) if s != everything)
    h.check("Grade Everything: one adjustment clip on the Grade track over the whole project",
            everything is not None and everything.type == 'ADJUSTMENT' and gt is not None
            and everything.channel == tracks.channel_of(sc, gt) and clips.end(everything) == ends
            and sc.sequence_editor.active_strip == everything, everything and (clips.start(everything), ends))
    everything.color_saturation = 0.0
    sc.frame_current = clips.start(b) + 2
    px = render(sc, os.path.join(folder, "all.png"))
    h.check("...grading it grades everything under it (saturation 0: grey)",
            abs(px[0] - px[1]) < 0.02 and abs(px[1] - px[2]) < 0.02, px[:3])
    clips.apply(sc, {b: (clips.start(b), clips.end(b) + 24)})
    events.clips_changed(sc)
    yield 0.2
    h.check("...and stays as long as the project", clips.end(everything) == clips.end(b),
            (clips.end(everything), clips.end(b)))


h.run(steps())
