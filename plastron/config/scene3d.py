"""The 3D scene view (under the script): your panels as cards in 3D, one
per video track, and a 3D camera that keyframes itself as you move it.
Ctrl+Space maximises it (or any area).

Move a track's card further back / nearer (or sideways, turn, scale) with
Blender's own tools; move the 3D Camera for a parallax move.
"""

ORIGIN = (0.0, 0.0, 0.0)           # the picture plane's middle (where the cards stand)
CAMERA_NAME = "3D Camera"
COLLECTION = "3D Scene"
CAMERA_LENS = 35.0                 # mm. The camera starts square-on, exactly framing the picture
VIEW_DISTANCE = 34.0               # the scene view starts this far from ORIGIN...
VIEW_ANGLES = (75.0, 0.0, -35.0)   # ...looking at the cards from the front-left (degrees, X/Y/Z)
CLIP_END = 1000.0
SHADING = 'MATERIAL'               # the cards show their drawings
CARD_COLOR = "#83a4a0cc"            # outline of each track's card (the one drawn on: orange)
