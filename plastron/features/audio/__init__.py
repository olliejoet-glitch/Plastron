"""Audio mode (sound design) on the same timeline (config/audio.py).

    analysis   sound as numbers: loudness (LUFS), envelope, beats
    loudness   Normalise: clip volumes to each kind's loudness target
    duck       auto-ducking (tracks with Duck dip under the voice)
    beats      Find Beats: a marker on every beat of a music clip
    breaths    breath remover (dips breaths in voice clips)
    creature   creature voices (a voice baked into a stack of pitched copies)
    fit        music fitting (a beat lands on the video's end, fade out)
    panel      the Sound panel (Audio mode's timeline sidebar)
"""

from . import beats, breaths, creature, duck, fit, loudness, panel

_MODULES = (loudness, duck, panel, beats, breaths, creature, fit)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
