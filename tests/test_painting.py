"""Panel paintings: the layers panel acts on the panel on the canvas, painting
follows the active layer, and paint survives saving and reopening."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

panels = h.module("features.storyboard.panels")


def canvas_mat():
    return bpy.data.objects["Canvas"].material_slots[0].material


def painted(img):
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    return int((px[3::4] > 0.05).sum())


def steps():
    yield 1.0
    mat = canvas_mat()
    st = mat.plastron_stack
    ip = bpy.context.scene.tool_settings.image_paint

    with h.override('VIEW_3D'):
        bpy.ops.plastron.layer_add(layer_type='PAINT')
    yield
    h.check("Add Layer adds a paint layer to the panel on the canvas",
            [l.name for l in st.layers] == ["Sketch", "Layer 2"], [l.name for l in st.layers])
    h.check("...and painting goes to the new layer", ip.canvas == st.active.paint_image)
    st.active_index = 0
    h.check("picking a layer aims painting at it", ip.canvas == st.layers[0].paint_image)
    st.layers[0].locked = True
    h.check("a locked layer can't be painted", ip.canvas is None)
    st.layers[0].locked = False
    with h.override('VIEW_3D'):
        bpy.ops.plastron.layer_add(layer_type='FILL', fill_source='COLOR')
    yield
    h.check("a fill layer isn't painted on", ip.canvas is None)
    with h.override('VIEW_3D'):
        bpy.ops.plastron.layer_remove()
    yield
    st.active_index = 0

    # Paint (directly), save, reopen.
    img = st.layers[0].paint_image
    w, hgt = img.size
    dab = np.zeros((hgt, w, 4), np.float32)
    dab[600:700, 1100:1300] = (0.1, 0.2, 0.3, 1.0)
    img.pixels.foreach_set(dab.ravel())
    img.update()
    count = painted(img)
    path = os.path.join(bpy.app.tempdir, "paint_test", "Painted.blend")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    yield
    h.check("saving packs the painted layers", img.packed_file is not None and not img.is_dirty)
    bpy.ops.wm.open_mainfile(filepath=path)
    yield 1.0
    mat = canvas_mat()
    st = mat.plastron_stack
    h.check("reopened project shows the panel on the canvas",
            mat is not None and mat == panels.all_panels(bpy.context.scene)[0].plastron_panel.material)
    h.check("...with its layers", [l.name for l in st.layers] == ["Sketch", "Layer 2"],
            [l.name for l in st.layers])
    h.check("...and its paint", painted(st.layers[0].paint_image) == count,
            (painted(st.layers[0].paint_image), count))
    h.check("...ready to paint on", bpy.context.mode == 'PAINT_TEXTURE' and
            bpy.context.scene.tool_settings.image_paint.canvas == st.active.paint_image)
    h.screenshot("painting")


h.run(steps())
