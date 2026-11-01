"""Camera and layer motion (stage 6): limits, handles, when moves show.

Colours of the frames drawn while setting a move: CANVAS in config/theme.py.
The ease / overshoot / shake presets are JSON files in plastron/presets/motion/.
"""

# Camera: how far a move can zoom (1 = the normal frame, 2 = twice as close)
# and rotate (degrees either way). Pan has no limit; past the painted bleed
# shows the paper colour.
ZOOM_RANGE = (0.5, 8.0)
ROTATION_LIMIT = 45.0

# Setting a camera position (Motion panel: Start / End), dragging:
#   inside the frame = move it · near a corner = zoom · outside = rotate.
CORNER_GRAB_PX = 18          # how near a corner counts as grabbing it
ROTATE_STEP = 5.0            # degrees per step with Shift held

# Camera shake (from the "Camera shake" preset or the Motion panel):
# amount = % of the frame width; speed = wobbles per second.
SHAKE_AMOUNT_MAX = 10.0
SHAKE_SPEED_RANGE = (0.2, 30.0)
SHAKE_ROTATION = 0.15        # degrees of tilt per % of shake

# Moving layers show where they are at the playhead after scrubbing stops
# for this long (seconds). During playback they stay put (no per-frame work:
# Ollie's standing rule); the camera frame does follow the playback.
LAYER_REFRESH_DELAY = 0.12
