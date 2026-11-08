"""Edit mode: cutting the real video on the same timeline (config/edit.py).

    media   putting footage / sound / pictures on the right tracks (and
            fixing up Blender's own drops)
    bin     the media bin (file browser) + Add to Timeline; preview size
"""

from . import bin, media

_MODULES = (media, bin)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
