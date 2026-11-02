"""The 3D scene view (under the script): a small 3D scene with its own
camera, for blocking out shots. Ctrl+Space maximises it (or any area).

Its objects live far from the canvas (the canvas never looks there, and the
scene view's clipping hides the canvas), in the "3D Scene" collection.
"""

ORIGIN = (5000.0, 0.0, 0.0)        # middle of the 3D scene, in world units
CAMERA_NAME = "3D Camera"
COLLECTION = "3D Scene"
CAMERA_OFFSET = (0.0, -10.0, 1.6)  # from ORIGIN: in front, at eye height, looking at it
CAMERA_LENS = 35.0                 # mm
VIEW_DISTANCE = 22.0               # the view starts this far from ORIGIN...
VIEW_ANGLES = (62.0, 0.0, 35.0)    # ...looking down at it from here (degrees, X/Y/Z)
CLIP_END = 1000.0                  # beyond this the view shows nothing (the canvas is 5000 away)
