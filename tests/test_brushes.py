"""Brush palette and importing brushes: Photoshop .abr, image tips, Blender
.blend brushes. An imported tip paints its own shape."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

palette = h.module("features.storyboard.brush_palette")
abr = h.module("features.storyboard.abr")
tools_cfg = h.module("config.tools")


def ring(size=64):
    """A square ring: paint on the border band, nothing in the middle."""
    y, x = np.mgrid[0:size, 0:size]
    edge = np.minimum(np.minimum(x, y), np.minimum(size - 1 - x, size - 1 - y))
    return np.where((edge >= 4) & (edge < 14), 255, 0).astype(np.uint8)


def layer_pixels():
    img = bpy.data.objects["Canvas"].active_material.plastron_stack.active.paint_image
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


def steps():
    yield 1.0
    tmp = os.path.join(bpy.app.tempdir, "brush_import")
    os.makedirs(tmp, exist_ok=True)
    libs = bpy.context.preferences.filepaths.asset_libraries
    lib = libs.get(tools_cfg.BRUSH_LIBRARY_NAME)
    h.check("the Plastron Brushes library is set up", lib is not None and os.path.isdir(lib.path))

    # .abr (Photoshop), compressed and not
    tip = ring()
    path = os.path.join(tmp, "ring.abr")
    abr.write_v6(path, [("a", 64, 64, tip.tobytes()), ("b", 64, 64, tip[::-1].tobytes())],
                 compressed=True)
    read = abr.read(path)
    h.check("reads Photoshop brush tips", len(read) == 2 and read[0][3] == tip.tobytes())
    before = set(bpy.data.brushes.keys())
    names, out = palette.import_file(path)
    h.check("an .abr file becomes palette brushes", names == ["ring 1", "ring 2"] and os.path.exists(out),
            (names, out))
    h.check("...saved in the library, not in the project", set(bpy.data.brushes.keys()) == before)

    # an image as a tip
    png = os.path.join(tmp, "Dots.png")
    img = bpy.data.images.new("dots", 32, 32)
    px = np.ones((32, 32, 4), np.float32)
    px[8:24, 8:24, :3] = 0.0                     # a dark square on white paper
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw, img.file_format = png, 'PNG'
    img.save()
    bpy.data.images.remove(img)
    names, _ = palette.import_file(png)
    h.check("an image becomes a brush tip", names == ["Dots"], names)

    # a Blender brush file
    b = bpy.data.brushes.new("My Chalk", mode='TEXTURE_PAINT')
    blend = os.path.join(tmp, "chalk.blend")
    bpy.data.libraries.write(blend, {b}, fake_user=True)
    bpy.data.brushes.remove(b)
    names, _ = palette.import_file(blend)
    h.check("Blender brushes import too", names == ["My Chalk"], names)

    # The imported brushes are in the palette: pick one and paint a single dab.
    palette.refresh_palette(bpy.context)
    yield 1.0
    with h.override('VIEW_3D'):
        bpy.ops.brush.asset_activate(asset_library_type='CUSTOM',
                                     asset_library_identifier=tools_cfg.BRUSH_LIBRARY_NAME,
                                     relative_asset_identifier="ring.blend/Brush/ring 1")
    ip = bpy.context.scene.tool_settings.image_paint
    h.check("an imported brush can be picked", ip.brush is not None and ip.brush.name == "ring 1",
            ip.brush and ip.brush.name)
    ups = ip.unified_paint_settings
    (ups if ups.use_unified_size else ip.brush).size = 60
    region = h.region(h.area('VIEW_3D'))
    cx, cy = h.center(region)
    h.move(cx, cy)
    yield
    h._event('LEFTMOUSE', 'PRESS')
    yield
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.5
    px = layer_pixels()
    hh, ww = px.shape[:2]
    painted = px[..., 3] > 0.3
    middle = painted[hh // 2 - 3:hh // 2 + 4, ww // 2 - 3:ww // 2 + 4]
    h.check("the dab has the tip's shape (a ring: painted around, empty in the middle)",
            painted.sum() > 200 and not middle.any(), (int(painted.sum()), int(middle.sum())))
    h.screenshot("brush_ring")

    # Right-click on the canvas opens the palette (no errors).
    h.move(cx + 100, cy)
    yield
    h._event('RIGHTMOUSE', 'PRESS')
    yield 0.5
    h.screenshot("brush_palette_pressed")
    h._event('RIGHTMOUSE', 'RELEASE')
    yield 0.5
    h.screenshot("brush_palette")
    h.key('ESC')
    yield 0.2


h.run(steps())
