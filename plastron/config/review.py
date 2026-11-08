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
