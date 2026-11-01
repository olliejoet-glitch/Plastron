"""App-wide interface pieces (top bar). Feature UI lives in each feature."""

from . import drag_scroll, topbar

_MODULES = (topbar, drag_scroll)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
