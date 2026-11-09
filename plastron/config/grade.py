"""Grade mode (colour grading).

Each clip's grade is Blender's colour tools on the clip: lift / gamma /
gain wheels (Color Balance), brightness / contrast, white balance, and the
clip's own saturation and tint. Grade Everything puts one adjustment clip on
the "Grade" track over the whole project: grading it grades everything.
Looks: plastron/presets/grades/*.json.
"""

GRADE_TRACK = "Grade"

# Blender modifier names Plastron gives a graded clip (in this order).
MODIFIERS = (("Plastron Balance", 'COLOR_BALANCE'),
             ("Plastron Bright", 'BRIGHT_CONTRAST'),
             ("Plastron White", 'WHITE_BALANCE'))

# The scopes beside the picture (Grade mode).
SCOPES = ('WAVEFORM', 'VECTOR_SCOPE')
