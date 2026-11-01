"""Camera and layer motion (stage 6): limits, handles, when moves show.

Colours of the frames drawn while setting a move: CANVAS in config/theme.py.
The ease / overshoot / shake presets are JSON files in plastron/presets/motion/.
"""

# Camera: how far a move can zoom (1 = the normal frame, 2 = twice as close)
# and rotate (degrees either way). Pan has no limit; past the painted bleed
# shows the paper colour.
ZOOM_RANGE = (0.5, 8.0)
ROTATION_LIMIT = 45.0

# Setting a camera position (C, or Motion panel: Start / End): a transform
# box on the frame. Drag inside = move the camera · a corner or side handle
# = zoom · outside = rotate (Shift: steps). Tab swaps Start / End.
HANDLE_PX = 7                # half-size of the box's handles
CORNER_GRAB_PX = 18          # how near a handle counts as grabbing it
ROTATE_STEP = 5.0            # degrees per step with Shift held
# In Camera View the frame stays still: True = the camera follows your hand
# (drag right and the camera pans right, so the drawing slides left);
# False = the drawing follows your hand.
CAMERA_FOLLOWS_HAND = True

# Camera shake (from the "Camera shake" preset or the Motion panel):
# amount = % of the frame width; speed = wobbles per second.
SHAKE_AMOUNT_MAX = 10.0
SHAKE_SPEED_RANGE = (0.2, 30.0)
SHAKE_ROTATION = 0.15        # degrees of tilt per % of shake

# Camera and layers move with playback and scrubbing (Ollie). Painting on a
# moved layer is re-aimed this long (seconds) after scrubbing stops.
LAYER_REFRESH_DELAY = 0.12
