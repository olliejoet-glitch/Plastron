"""Planning and review (stage 7).

    notes     shot status (colour tag) + notes per panel (Panel panel)
    guides    framing guides on the canvas (thirds, safe areas, 9:16)
    speed     speed playback (1.5x / 2x, the voice keeps its pitch)
    sounds    temp sounds bin (timeline header: Sounds)
    board     board view: the panels as cards, drag to reorder (header: Board)
    versions  panel versions: keep, flip, compare (Panel panel)
"""

from . import board, guides, notes, sounds, speed, versions

_MODULES = (notes, versions, guides, speed, sounds, board)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
