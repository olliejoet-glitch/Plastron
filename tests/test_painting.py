"""Panel paintings: the layers panel acts on the panel on the canvas, painting
follows the active layer, brush presets, paint survives saving and reopening,
onion skin."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

panels = h.module("features.storyboard.panels")
panel_cache = h.module("features.storyboard.panel_cache")
canvas_sync = h.module("features.storyboard.canvas_sync")
presets = h.module("core.presets")


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

    # --- Brush presets -----------------------------------------------------------------
    names = [p["name"] for p in presets.all_presets("brushes")]
    h.check("built-in brush presets", names[:4] == ["Pencil", "Ink", "Marker", "Soft shading"], names)
    ip = bpy.context.scene.tool_settings.image_paint
    ups = ip.unified_paint_settings
    for name in names[:4]:
        want = presets.get("brushes", name)
        with h.override('VIEW_3D'):
            bpy.ops.plastron.preset_apply(kind="brushes", name=name)
        b = ip.brush
        size = ups.size if ups.use_unified_size else b.size
        strength = ups.strength if ups.use_unified_strength else b.strength
        h.check(f"preset {name}: brush, size, opacity, pressure, smoothing",
                b.name == want["base"] and size == want["size"] and abs(strength - want["opacity"]) < 1e-3
                and b.use_pressure_size == want["pressure_size"]
                and b.use_pressure_strength == want["pressure_opacity"]
                and b.use_smooth_stroke == want["smooth"],
                (b.name, size, strength, b.use_pressure_size, b.use_pressure_strength, b.use_smooth_stroke))
    with h.override('VIEW_3D'):
        bpy.ops.plastron.preset_apply(kind="brushes", name="Ink")
        (ups if ups.use_unified_size else ip.brush).size = 17
        presets.save("brushes", "Fat ink", bpy.context)
        bpy.ops.plastron.preset_apply(kind="brushes", name="Pencil")
        bpy.ops.plastron.preset_apply(kind="brushes", name="Fat ink")
    size = ups.size if ups.use_unified_size else ip.brush.size
    h.check("saving the current brush as a preset, and using it",
            "Fat ink" in [p["name"] for p in presets.all_presets("brushes")] and size == 17, size)
    h.check("saved presets can be deleted, built-in ones can't",
            presets.delete("brushes", "Fat ink") and not presets.delete("brushes", "Ink")
            and "Fat ink" not in [p["name"] for p in presets.all_presets("brushes")])
    with h.override('VIEW_3D'):
        bpy.ops.plastron.canvas_tool(tool='PENCIL')

    # Paint (directly), save, reopen.
    img = st.layers[0].paint_image
    w, hgt = img.size
    dab = np.zeros((hgt, w, 4), np.float32)
    dab[600:700, 1100:1300] = (0.1, 0.2, 0.3, 1.0)
    img.pixels.foreach_set(dab.ravel())
    img.update()
    count = painted(img)
    panel_cache.request(mat)
    panel_cache.flush_now()
    yield 1.0
    h.screenshot("thumbnails")
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

    # --- Onion skin ----------------------------------------------------------------
    sc = bpy.context.scene
    p1 = panels.all_panels(sc)[0]
    sc.frame_current = 49
    p2 = panels.new_at_playhead(sc)
    sc.frame_current = 30
    p0 = panels.new_at_playhead(sc)            # cuts panel 1 short: p1 | p0 | p2
    sc.frame_current = 40
    yield
    before, after = (bpy.data.objects[n] for n in canvas_sync.ONION)
    h.check("onion skin is off to start with", before.hide_viewport and after.hide_viewport)
    wm = bpy.context.window_manager
    wm.plastron_onion = True
    yield
    h.check("onion skin shows the panels before and after, faintly",
            not before.hide_viewport and not after.hide_viewport
            and before.material_slots[0].material == p1.plastron_panel.material
            and after.material_slots[0].material == p2.plastron_panel.material
            and abs(before.color[3] - 0.25) < 1e-3 and abs(after.color[3] - 0.25) < 1e-3)
    h.check("...behind the panel being drawn on",
            before.location.y > bpy.data.objects["Canvas"].location.y)
    wm.plastron_onion_opacity = 0.5
    h.check("onion skin strength", abs(before.color[3] - 0.5) < 1e-3, before.color[3])
    sc.frame_current = 10
    yield
    h.check("on the first panel there's nothing before it",
            before.hide_viewport and after.material_slots[0].material == p0.plastron_panel.material)
    h.screenshot("painting")
    wm.plastron_onion = False
    yield
    h.check("turning it off hides it", before.hide_viewport and after.hide_viewport)


h.run(steps())
