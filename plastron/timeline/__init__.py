"""The one shared timeline and track system.

Stage 1: the timeline header. Stage 2 adds tracks, clips, ripple, lock,
snapping and split.
"""

from . import header

_MODULES = (header,)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
