"""App-wide interface pieces (top bar). Feature UI lives in each feature."""

from . import topbar

_MODULES = (topbar,)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
