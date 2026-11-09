"""Value groups (Ollie's four value groups: the greys a picture is planned in).

The groups are remembered in Plastron's settings (not per project). Values
view shows the canvas / preview reduced to them.
"""

DEFAULT_GROUPS = (0.12, 0.38, 0.64, 0.9)     # greys (0 black - 1 white, as shown on screen)
COUNT = 4
VALUES_TRACK = "Values"                       # the preview's Values view clip goes on this track
SAMPLE_SIZE = 256                             # pictures are sampled this small (fast)
