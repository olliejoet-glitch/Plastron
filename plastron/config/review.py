"""Planning and review (stage 7): shot status, notes, framing guides, speed
playback, temp sounds, board view.
"""

# Shot status: a colour tag per panel (also the clip's colour on the timeline).
#   id, label, timeline colour tag (Blender's COLOR_01..09), swatch colour
STATUS = [
    ("SKETCH",   "Sketch",   'COLOR_09', "#9a9893"),
    ("BLOCKING", "Blocking", 'COLOR_03', "#e2c044"),
    ("ANIMATED", "Animated", 'COLOR_05', "#4d73b1"),
    ("FINAL",    "Final",    'COLOR_04', "#5aa55a"),
]
STATUS_DEFAULT = "SKETCH"

# Framing guides on the canvas (toggled in the options bar's Guides menu,
# remembered). Safe areas are fractions of the frame (centred).
GUIDES = [
    # id,        label
    ("THIRDS",   "Rule of thirds"),
    ("SAFE",     "YouTube safe areas"),
    ("SHORT",    "9:16 (Shorts)"),
]
SAFE_AREAS = [("Action safe", 0.93), ("Title safe", 0.90)]
GUIDE_COLOR = "#ffffff88"
SHORT_COLOR = "#de7520cc"

# Speed playback (timeline header): play the animatic faster with the voice
# at its normal pitch (the sound is time-stretched, the picture plays at
# fps x speed; everything is put back when playback stops).
SPEEDS = (1.0, 1.5, 2.0)

# Temp sounds (timeline header: Sounds): placeholder effects from a folder
# in Plastron's settings ("plastron_sounds/", subfolders = tags). Added at the
# playhead on this track, coloured and named so they're easy to find and
# replace later.
TEMP_SOUND_TRACK = "Temp Sounds"
TEMP_SOUND_PREFIX = "TEMP "
TEMP_SOUND_COLOR = 'COLOR_07'
SOUND_TYPES = (".wav", ".mp3", ".ogg", ".flac", ".aif", ".aiff", ".m4a")
