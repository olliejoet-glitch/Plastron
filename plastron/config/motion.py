"""Camera and layer motion (stage 6): limits, handles, when moves show.

Colours of the frames drawn while setting a move: CANVAS in config/theme.py.
The ease / overshoot / shake presets are JSON files in plastron/presets/motion/.
"""

# Camera: how far a move can zoom (1 = the normal frame, 2 = twice as close)
# and rotate (degrees either way). Pan has no limit; past the painted bleed
# shows the paper colour.
ZOOM_RANGE = (0.5, 8.0)
ROTATION_LIMIT = 45.0

# Camera controls: a small box in the canvas's bottom-left corner (Ollie: no
# camera mode). Sizes in pixels (at 100 % UI scale); speeds per pixel dragged.
CAMERA_PAD = {
    "margin": 14, "size": 120, "strip": 18, "gap": 4, "button": 20,
    "pan_per_px": 0.15,       # % of the frame width the camera moves per pixel
    "pad_reach": 50.0,        # the pad's edge shows a move of this % of the frame width
    "zoom_per_px": 0.006,     # zoom changes by about 0.6 % per pixel
    "turn_per_px": 0.15,      # degrees per pixel
}

# Setting a layer's position (Motion panel: Start / End): a transform
# box on the canvas. (The camera's own box mode below is still there for
# code / tests but has no key.) Drag inside = move the camera · a corner or side handle
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
