"""Audio mode (sound design) on the same timeline (config/audio.py).

    analysis   sound as numbers: loudness (LUFS), envelope, beats
    loudness   Normalise: clip volumes to each kind's loudness target
    duck       auto-ducking (tracks with Duck dip under the voice)
    beats      Find Beats: a marker on every beat of a music clip
    panel      the Sound panel (Audio mode's timeline sidebar)
"""

from . import beats, duck, loudness, panel

_MODULES = (loudness, duck, panel, beats)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
