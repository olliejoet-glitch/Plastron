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


h.run(steps())
