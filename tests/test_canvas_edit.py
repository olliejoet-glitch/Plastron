"""Stage 5 with simulated keys and mouse: rectangle / lasso selection (add,
take away, deselect, undo), V move, Ctrl+T scale / distort / warp, Esc
cancel, Delete, copy / paste between panels, flips."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

pixels = h.module("features.canvas_edit.pixels")
selection = h.module("features.canvas_edit.selection")
panels = h.module("features.storyboard.panels")
canvas_view = h.module("features.storyboard.canvas_view")


def layer_px():
    mat = pixels.material()
    return pixels.array(mat.plastron_stack.active.paint_image)


def painted(a=None):
    a = layer_px() if a is None else a
    return a[..., 3] > 0.5


def win(px, py):
    """Canvas pixel -> window pixel."""
    with h.override('VIEW_3D'):
        x, y = pixels.region_point(bpy.context, px, py)
    r = h.region(h.area('VIEW_3D'))
    return r.x + x, r.y + y


def sel():
    m = selection.mask(bpy.context)
    return None if m is None else m > 0.5


def steps():
    yield 1.0
    with h.override('VIEW_3D'):
        bpy.ops.plastron.canvas_fit()
    yield 0.5
    h.redraw()
    mat = pixels.material()
    layer = mat.plastron_stack.active
    w, hh = pixels.size()
    a = np.zeros((hh, w, 4), np.float32)
    a[600:700, 1000:1200] = (1.0, 0.0, 0.0, 1.0)          # a red block
    pixels.write(layer.paint_image, a)
    base_count = int(painted().sum())

    # --- M: rectangle selection --------------------------------------------------------------
    h.move(*win(1100, 650))
    yield
    h.key('M')
    yield 0.2
    yield from h.drag(win(980, 580), win(1220, 720))
    yield 0.3
    s = sel()
    h.check("M + drag selects a rectangle", s is not None and s[650, 1100] and not s[650, 900]
            and abs(int(s.sum()) - 240 * 140) < 240 * 140 * 0.08, None if s is None else int(s.sum()))
    stencil = bpy.context.scene.tool_settings.image_paint
    h.check("...and painting is kept inside it (stencil mask)",
            stencil.use_stencil_layer and stencil.stencil_image is not None)
    yield from h.drag(win(1300, 580), win(1400, 720), shift=True)
    yield 0.3
    added = sel()
    h.check("Shift+drag adds to it", added[650, 1350] and added[650, 1100])
    yield from h.drag(win(1300, 580), win(1400, 720), alt=True)
    yield 0.3
    h.check("Alt+drag takes away", not sel()[650, 1350] and sel()[650, 1100])
    h.screenshot("selection")
    h.key('ESC')
    yield 0.2
    h.key('D', ctrl=True)
    yield 0.2
    h.check("Ctrl+D deselects", sel() is None)
    h.key('Z', ctrl=True)
    yield 0.5
    h.check("Ctrl+Z brings the selection back", sel() is not None and sel()[650, 1100])

    # --- L: lasso ------------------------------------------------------------------------------
    h.key('D', ctrl=True)
    yield 0.2
    h.key('L')
    yield 0.2
    path = [(900, 500), (1300, 500), (1100, 800), (900, 500)]
    h.move(*win(*path[0]))
    yield
    h._event('LEFTMOUSE', 'PRESS')
    yield
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        for t in np.linspace(0, 1, 8)[1:]:
            h.move(*win(ax + (bx - ax) * t, ay + (by - ay) * t))
            yield
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.3
    s = sel()
    h.check("L + drag selects a lasso shape", s is not None and s[550, 1100] and not s[780, 920],
            None if s is None else int(s.sum()))
    h.key('ESC')
    yield 0.2

    # --- V: move -------------------------------------------------------------------------------
    h.key('A', ctrl=True)      # select all: moves everything on the layer
    yield 0.2
    h.key('V')
    yield 0.2
    yield from h.drag(win(1100, 650), win(1100 + 150, 650 + 100))
    yield 0.5
    p = painted()
    h.check("V + drag moves the pixels", p[750, 1250] and not p[620, 1020] and
            abs(int(p.sum()) - base_count) < base_count * 0.05, int(p.sum()))
    h.check("...and the selection with them", sel()[750, 1250] if sel() is not None else True)
    h.key('ESC')
    yield 0.2
    h.key('Z', ctrl=True)
    yield 0.6
    p = painted()
    h.check("Ctrl+Z puts them back", p[620, 1020] and not p[790, 1340], int(p.sum()))

    # --- Ctrl+T: scale (corner drag), apply with Enter ---------------------------------------
    h.key('D', ctrl=True)
    yield 0.2
    h.move(*win(1100, 650))
    h.key('T', ctrl=True)
    yield 0.3
    yield from h.drag(win(1200, 700), win(1400, 800))     # top-right corner, away
    yield 0.2
    h.screenshot("transform")
    h.key('RET')
    yield 0.6
    p = painted()
    h.check("Ctrl+T, drag a corner, Enter: scaled (corner opposite stays put)",
            p[610, 1010] and p[790, 1390] and int(p.sum()) > base_count * 3.5, int(p.sum()))
    h.key('Z', ctrl=True)
    yield 0.6
    h.check("...undoable", abs(int(painted().sum()) - base_count) < 50, int(painted().sum()))

    # Esc cancels.
    h.key('T', ctrl=True)
    yield 0.3
    yield from h.drag(win(1100, 650), win(1300, 650))
    yield 0.2
    h.key('ESC')
    yield 0.4
    p = painted()
    h.check("Esc cancels a transform", p[650, 1100] and not p[650, 1350]
            and abs(int(p.sum()) - base_count) < 50, int(p.sum()))

    # Ctrl+drag a corner: distort (corner pin).
    h.key('T', ctrl=True)
    yield 0.3
    yield from h.drag(win(1200, 700), win(1300, 900), ctrl=True)
    yield 0.2
    h.key('RET')
    yield 0.6
    p = painted()
    h.check("Ctrl+drag a corner distorts (only that corner moves)",
            p[610, 1010] and p[880, 1290] and not p[880, 1010], int(p.sum()))
    h.key('Z', ctrl=True)
    yield 0.6

    # W: warp, drag a grid point.
    h.key('T', ctrl=True)
    yield 0.3
    h.key('W')
    yield 0.2
    before = layer_px().copy()
    yield from h.drag(win(1133.3, 666.7), win(1133.3, 850))   # an inner warp point, upwards
    yield 0.2
    h.screenshot("warp")
    h.key('RET')
    yield 0.6
    p = painted()
    h.check("W warps: the drawing follows the dragged grid point",
            p[835, 1133] and not painted(before)[835, 1133] and not p[835, 1010], int(p.sum()))
    h.key('Z', ctrl=True)
    yield 0.6

    # --- Delete with a selection erases inside it ----------------------------------------------
    h.key('M')
    yield 0.2
    yield from h.drag(win(980, 580), win(1100, 720))
    yield 0.3
    h.key('ESC')
    yield 0.2
    h.key('DEL')
    yield 0.4
    p = painted()
    h.check("Delete erases the selected pixels", not p[650, 1050] and p[650, 1150])

    # --- Flip ----------------------------------------------------------------------------------
    h.key('D', ctrl=True)
    yield 0.2
    h.key('F', ctrl=True, alt=True)
    yield 0.4
    p = painted()
    h.check("Ctrl+Alt+F with nothing selected flips the layer left-right",
            p[650, w - 1 - 1150] and not p[650, w - 1 - 1050])
    h.key('F', ctrl=True, alt=True, shift=True)
    yield 0.4
    p = painted()
    h.check("Ctrl+Alt+Shift+F flips it upside down", p[hh - 1 - 650, w - 1 - 1150])

    # --- Copy / paste between panels ------------------------------------------------------------
    copied_from = layer_px().copy()
    h.key('C', ctrl=True)
    yield 0.2
    sc = bpy.context.scene
    first = pixels.material()
    sc.frame_current = 49
    yield
    h.key('N')
    yield 0.4
    second = pixels.material()
    h.check("(a new panel is on the canvas)", second is not None and second != first)
    h.key('V', ctrl=True)
    yield 0.4
    names = [l.name for l in second.plastron_stack.layers]
    pasted = layer_px()
    h.check("Ctrl+V pastes in place, as a new layer, on another panel",
            "Pasted" in names and np.array_equal(painted(pasted), painted(copied_from)), names)
    h.screenshot("pasted")


h.run(steps())
