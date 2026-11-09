"""Value group editor (config/values.py): your four value groups.

    groups  the greys (remembered), sampling them from a picture / panel
    view    Values view: the canvas / preview in your value groups only
    ui      swatches (options bar, Values panel), toggles
"""

from . import groups, ui, view

_MODULES = (view, ui)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()


__all__ = ["groups"]
