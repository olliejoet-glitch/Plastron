"""Editing the canvas's pixels (stage 5): selections, move / transform
(scale, rotate, distort, warp), copy / paste between panels, flips.

    shapes      pure numpy geometry (masks, homographies, warp, resampling)
    pixels      reading / writing layer pixels undoably; screen <-> canvas
    selection   L lasso, M rectangle, deselect / all / invert / erase
    transform   Ctrl+T transform, V move
    clipboard   Ctrl+C / X / V, Ctrl+Alt+F flips
"""

from . import clipboard, selection, transform

_MODULES = (selection, transform, clipboard)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
