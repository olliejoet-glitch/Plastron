"""Edit mode: cutting the real video on the same timeline (config/edit.py).

    media   putting footage / sound / pictures on the right tracks (and
            fixing up Blender's own drops)
    bin     the media bin (file browser) + Add to Timeline; preview size
    clip_panel  the Clip panel (preview sidebar)
    frame_box   move / size / turn the selected clip by hand in the preview
    windows     info windows: a clip with its own timeline inside a UI frame
    shorts      Shorts reframing (a 9:16 box per shot; the Shorts export)
"""

from . import bin, clip_panel, frame_box, media, shorts, windows

_MODULES = (media, bin, clip_panel, frame_box, windows, shorts)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
