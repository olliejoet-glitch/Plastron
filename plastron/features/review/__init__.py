"""Planning and review (stage 7).

    notes     shot status (colour tag) + notes per panel (Panel panel)
    guides    framing guides on the canvas (thirds, safe areas, 9:16)
"""

from . import guides, notes

_MODULES = (notes, guides)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
