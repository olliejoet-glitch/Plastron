"""Value group editor: four value groups (set, sampled from a picture),
painting with them, Values view (canvas + preview reduced to the groups)."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.values")
groups = h.module("features.values.groups")
view = h.module("features.values.view")
media = h.module("features.edit.media")
clips = h.module("timeline.clips")


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
    return px.reshape(hh, w, 4)


def steps():
    yield 1.0
    sc = bpy.context.scene
    wm = bpy.context.window_manager
    h.check("four value groups to start with", groups.get() == list(cfg.DEFAULT_GROUPS), groups.get())

    folder = os.path.join(bpy.app.tempdir, "values")
    os.makedirs(folder, exist_ok=True)
    four = os.path.join(folder, "four.png")
    a = np.zeros((90, 160, 3), np.uint8)
    for i, g in enumerate((0.1, 0.3, 0.6, 0.85)):
        a[:, i * 40:(i + 1) * 40] = int(g * 255)
    with open(os.path.join(folder, "four.ppm"), "wb") as f:
        f.write(b"P6 160 90 255\n" + a[::-1].tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(folder, "four.ppm"), four], check=True)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.values_from_image(filepath=four)
    got = groups.get()
    h.check("From a Picture: the four greys it's made of", np.allclose(got, (0.1, 0.3, 0.6, 0.85), atol=0.02), got)

    with h.override('VIEW_3D'):
        bpy.ops.plastron.value_use(index=2)
    ups = bpy.context.tool_settings.image_paint.unified_paint_settings
    h.check("clicking a value's number paints with its grey", abs(ups.color[0] - got[2]) < 0.01, tuple(ups.color))
    wm.plastron_value_0 = (0.05, 0.05, 0.05)
    h.check("changing a swatch changes the group (and it's remembered)",
            abs(groups.get()[0] - 0.05) < 1e-3 and h.module("core.user_settings").get(groups.KEY)[0] < 0.06)

    # Values view: a gradient comes out in the four greys only.
    grad = os.path.join(folder, "grad.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "gradients=size=640x360:c0=black:c1=white:x0=0:y0=0:x1=640:y1=0:nb_colors=2,format=rgb24",
                    "-frames:v", "1", grad], check=True)
    made = media.place(sc, grad, frame=1)
    sc.frame_current = 5
    plain = render(sc, os.path.join(folder, "plain.png"))
    row = plain[plain.shape[0] // 2, :, 0]
    h.check("(the gradient has many greys)", len(np.unique(np.round(row, 2))) > 10, len(np.unique(np.round(row, 2))))
    wm.plastron_values_view = True
    yield 0.4
    clip = view.values_clip(sc)
    h.check("Values view on: a Values clip over the project, the canvas through the compositor",
            clip is not None and clip.modifiers[0].type == 'COMPOSITOR'
            and h.area('VIEW_3D').spaces.active.shading.use_compositor == 'ALWAYS'
            and sc.compositing_node_group is not None)
    stepped = render(sc, os.path.join(folder, "stepped.png"))
    row = stepped[stepped.shape[0] // 2, :, 0]
    shown = [round(float(g), 2) for g in groups.get()]
    nearest = [min(shown, key=lambda s, v=v: abs(s - v)) for v in row]
    h.check("...the picture shows only the four value greys (8-bit rounding aside)",
            all(abs(v - n) < 0.02 for v, n in zip(row, nearest)) and len(set(nearest)) == 4,
            (sorted(set(np.round(row, 2))), shown))
    h.redraw()
    yield 1.0
    h.screenshot("values_view")
    wm.plastron_values_view = False
    yield 0.3
    h.check("Values view off: all taken away again (renders unaffected)",
            view.values_clip(sc) is None and sc.compositing_node_group is None
            and h.area('VIEW_3D').spaces.active.shading.use_compositor == 'DISABLED')
    del made


h.run(steps())
