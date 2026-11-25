"""Edit mode: cutting the real video on the same timeline (config/edit.py).

    media   putting footage / sound / pictures on the right tracks (and
            fixing up Blender's own drops)
    bin     the media bin (file browser) + Add to Timeline; preview size
    clip_panel  the Clip panel (preview sidebar)
    proxies     the preview's half-size copies of footage, built in the background
    playback_meter  real fps while playing + "Making preview copies..." (preview header)
    frame_rate  Check Frame Rate (variable? real speed?); footage placed at real speed
    frame_box   move / size / turn the selected clip by hand in the preview
    windows     info windows: a clip with its own timeline inside a UI frame
    shorts      Shorts reframing (a 9:16 box per shot; the Shorts export)
    titles      text over the picture (Text / T): typed in the preview, styles, move / size box
    attributes  copy / paste clip attributes (Ctrl+C / Ctrl+V: position, size, grade...)
"""

from . import attributes, bin, titles, clip_panel, frame_box, frame_rate, media, playback_meter, proxies, shorts, windows

_MODULES = (media, proxies, playback_meter, bin, clip_panel, frame_rate, frame_box, windows, shorts, attributes, titles)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
