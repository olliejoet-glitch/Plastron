"""Layer stacks: editing operations, and the numpy flattener (panel images)
matching what the canvas shows (an EEVEE render of the same material) for
every blend mode and layer feature."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

props = h.module("layers.props")
stack = h.module("layers.stack")
flatten = h.module("layers.flatten")
compiler = h.module("layers.compiler")

W, H = 48, 27
TOL = 3.0 / 255


def render_scene():
    """A scene that renders a plane with a given material, pixel for pixel."""
    sc = bpy.data.scenes.get("LayerTest") or bpy.data.scenes.new("LayerTest")
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
    sc.render.film_transparent = True
    sc.render.filter_size = 0.0
    sc.render.dither_intensity = 0.0
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.image_settings.color_depth = '16'
    sc.eevee.taa_render_samples = 1
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    if sc.camera is None:
        cam = bpy.data.objects.new("TestCam", bpy.data.cameras.new("TestCam"))
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = 2.0
        cam.location = (0, -5, 0)
        cam.rotation_euler = (np.pi / 2, 0, 0)
        sc.collection.objects.link(cam)
        sc.camera = cam
        me = bpy.data.meshes.new("TestPlane")
        hw, hh = 1.0, H / W
        me.from_pydata([(-hw, 0, -hh), (hw, 0, -hh), (hw, 0, hh), (-hw, 0, hh)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UV")
        for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
            uv.data[i].uv = c
        plane = bpy.data.objects.new("TestPlane", me)
        plane.data.materials.append(None)
        sc.collection.objects.link(plane)
    return sc


def render(mat):
    sc = render_scene()
    bpy.data.objects["TestPlane"].material_slots[0].material = mat
    path = os.path.join(bpy.app.tempdir, "layer_test.png")
    sc.render.filepath = path
    with bpy.context.temp_override(window=h.window(), scene=sc):
        bpy.ops.render.render(write_still=True, scene=sc.name)
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'Non-Color'      # read the stored (display) values as is
    px = np.empty(W * H * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(H, W, 4)


def compare(name, mat):
    want = render(mat)[1:-1, 1:-1]          # (edge pixels are partly outside the plane)
    got = flatten.flatten(mat)[1:-1, 1:-1]
    # 99th percentile: modes that pick one colour or the other (Darker Colour,
    # tiled seams) flip a few boundary pixels under the render's sub-pixel offset.
    alpha_err = np.percentile(np.abs(want[..., 3] - got[..., 3]), 99)
    seen = want[..., 3] > 0.02
    col_err = np.percentile(np.abs(want[..., :3] - got[..., :3])[seen], 99) if seen.any() else 0.0
    return h.check(f"flatten matches the canvas: {name}", alpha_err <= TOL and col_err <= TOL,
                   f"alpha err {alpha_err * 255:.1f}/255, colour err {col_err * 255:.1f}/255")


def new_mat(name):
    mat = bpy.data.materials.new(name)
    stack.init(mat, W, H, first_layer=None)
    return mat


def paint(img, rgba):
    img.pixels.foreach_set(np.ascontiguousarray(rgba, np.float32).ravel())
    img.update()


def gradient(seed):
    """Smooth test colours (the render samples a hair off-centre, so noise
    would measure sampling, not blending)."""
    y, x = np.mgrid[0:H, 0:W]
    u, v = x / (W - 1), y / (H - 1)
    p = seed * 1.7
    rgba = np.empty((H, W, 4), np.float32)
    rgba[..., 0] = 0.5 + 0.45 * np.sin(2.0 * u + p)
    rgba[..., 1] = 0.5 + 0.45 * np.sin(2.5 * v + 2 * p)
    rgba[..., 2] = 0.5 + 0.45 * np.sin(1.5 * (u + v) + 3 * p)
    rgba[..., 3] = 0.55 + 0.4 * np.sin(1.2 * u - 0.8 * v + p)
    return np.round(rgba * 255) / 255     # 8-bit, like a real painting


def layer(mat, uid):
    return mat.plastron_stack.by_uid(uid)


def steps():
    yield 1.0

    # --- editing operations -------------------------------------------------------
    mat = new_mat("Ops")
    a = stack.add_layer(mat, "PAINT", name="A")
    b = stack.add_layer(mat, "PAINT", name="B")
    st = mat.plastron_stack
    names = lambda: [l.name for l in st.layers]
    h.check("new layers go above the active one", names() == ["A", "B"] and st.active.uid == b)
    h.check("paint layers get their own image at the stack size",
            layer(mat, a).paint_image is not None and layer(mat, a).paint_image.size[:] == (W, H)
            and layer(mat, a).paint_image != layer(mat, b).paint_image)
    stack.move_layer(mat, b, -1)
    h.check("move down", names() == ["B", "A"])
    g = stack.group_layer(mat, a)
    h.check("group wraps the layer", layer(mat, a).parent_uid == g and names()[-1] == "Group")
    d = stack.duplicate_layer(mat, a)
    h.check("duplicate copies pixels into a new image",
            layer(mat, d).paint_image != layer(mat, a).paint_image and layer(mat, d).parent_uid == g)
    stack.ungroup(mat, g)
    h.check("ungroup keeps the children", st.by_uid(g) is None and layer(mat, a).parent_uid == "")
    stack.remove_layer(mat, d)
    h.check("remove", st.by_uid(d) is None and len(st.layers) == 2)
    copy = stack.copy_material(mat, "OpsCopy")
    h.check("copied stacks have their own images",
            copy.plastron_stack.layers[0].paint_image != st.layers[0].paint_image)
    yield

    # --- every blend mode -----------------------------------------------------------
    for mode, _label, _d, _k in props.BLEND_MODES:
        mat = new_mat("Blend " + mode)
        lo = stack.add_layer(mat, "PAINT", name="under")
        hi = stack.add_layer(mat, "PAINT", name="over")
        paint(layer(mat, lo).paint_image, gradient(1))
        top = gradient(2)[:, ::-1]
        paint(layer(mat, hi).paint_image, top)
        layer(mat, hi).blend_mode = mode
        layer(mat, hi).opacity = 0.8
        compare(mode, mat)
        yield

    # --- layer features ------------------------------------------------------------------
    def base(name):
        mat = new_mat(name)
        u = stack.add_layer(mat, "PAINT", name="under")
        paint(layer(mat, u).paint_image, gradient(3))
        return mat, u

    mat, u = base("Fill colour")
    f = stack.add_layer(mat, "FILL", fill_source="COLOR", name="fill")
    layer(mat, f).fill_color = (0.9, 0.3, 0.1)
    layer(mat, f).blend_mode = "MULTIPLY"
    layer(mat, f).opacity = 0.6
    compare("fill colour (multiply, 60 %)", mat)
    yield

    mat, u = base("Fill image")
    tex = bpy.data.images.new("tex", 16, 16, alpha=True)
    ty, tx = np.mgrid[0:16, 0:16] / 16.0 * 2 * np.pi       # seamless, smooth tile
    tile = np.stack((0.5 + 0.4 * np.sin(tx), 0.5 + 0.4 * np.cos(ty), 0.5 + 0.3 * np.sin(tx + ty),
                     0.7 + 0.25 * np.cos(tx - ty)), -1)
    paint(tex, np.round(tile * 255) / 255)
    f = stack.add_layer(mat, "FILL", fill_source="IMAGE", name="fill")
    L = layer(mat, f)
    L.fill_image, L.tex_scale, L.tex_rotation, L.tex_offset = tex, 1.5, 0.4, (0.1, -0.2)
    compare("fill image (scaled, rotated, tiled)", mat)
    yield

    mat, u = base("Hidden")
    o = stack.add_layer(mat, "FILL", fill_source="COLOR", name="hidden")
    layer(mat, o).visible = False
    compare("hidden layer", mat)
    yield

    mat, u = base("Layer HSV")
    layer(mat, u).la_hue, layer(mat, u).la_saturation, layer(mat, u).la_value = 40, 1.4, 0.8
    compare("layer hue / saturation / value", mat)
    yield

    for kind, setup in (("HUE_SAT", dict(hs_hue=30, hs_saturation=-40, hs_lightness=20)),
                        ("LEVELS", dict(lv_in_black=30, lv_in_white=220, lv_gamma=1.4,
                                        lv_out_black=10, lv_out_white=240)),
                        ("BRIGHT_CONTRAST", dict(bc_brightness=20, bc_contrast=30))):
        mat, u = base("Adjust " + kind)
        a = stack.add_layer(mat, "ADJUST", adjust_kind=kind, name=kind)
        for k, v in setup.items():
            setattr(layer(mat, a), k, v)
        compare("adjustment layer: " + kind, mat)
        yield

    mat, u = base("Curves")
    a = stack.add_layer(mat, "ADJUST", adjust_kind="CURVES", name="curves")
    curve = layer(mat, a).node_tree.nodes["ADJ.curves"].mapping.curves[3]
    curve.points.new(0.4, 0.7)
    layer(mat, a).node_tree.nodes["ADJ.curves"].mapping.update()
    compare("adjustment layer: CURVES", mat)
    yield

    for gmode in ("PASS_THROUGH", "ISOLATED"):
        mat, u = base("Group " + gmode)
        c = stack.add_layer(mat, "PAINT", name="child")
        paint(layer(mat, c).paint_image, gradient(5))
        layer(mat, c).blend_mode = "SCREEN"
        g = stack.group_layer(mat, c)
        layer(mat, g).group_mode = gmode
        layer(mat, g).opacity = 0.7
        compare("group " + gmode.lower(), mat)
        yield

    mat, u = base("Mask paint")
    f = stack.add_layer(mat, "FILL", fill_source="COLOR", name="fill")
    stack.add_mask(mat, f, "PAINT")
    m = layer(mat, f).masks[0]
    y, x = np.mgrid[0:H, 0:W]
    grey = np.round(np.clip(x / W, 0, 1) * 255) / 255
    paint(m.image, np.stack((grey, grey, grey, np.ones_like(grey)), -1))
    compare("painted mask", mat)
    yield

    mat, u = base("Blend if")
    o = stack.add_layer(mat, "PAINT", name="over")
    paint(layer(mat, o).paint_image, gradient(6))
    layer(mat, o).blend_if = True
    ramp = layer(mat, o).node_tree.nodes["BI.under.GREY"].color_ramp
    ramp.elements[1].position = 0.3
    ramp.elements[2].position = 0.7
    compiler.push_layer(mat, layer(mat, o))
    compare("blend if", mat)


h.run(steps())
