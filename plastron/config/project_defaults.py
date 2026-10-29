"""Settings every new Plastron project starts with.

After changing anything here, rebuild the startup file:
    python tools/build_startup.py
"""

# Final output is 4K. Storyboard work previews at PREVIEW_PERCENT of that.
RESOLUTION = (3840, 2160)
PREVIEW_PERCENT = 50          # 50 % of 4K = 1920 x 1080
FPS = 24                      # YouTube keeps the upload's rate; 24 = animation standard

FRAME_START = 1
FRAME_END = 240               # 10 s; grows as panels are added

AUDIO_SCRUB = True            # hear audio while dragging the playhead
PLAYBACK_SYNC = 'AUDIO_SYNC'  # keep picture locked to sound, dropping frames if needed

# "Standard" shows greys exactly as drawn (Blender's default, AgX, shifts them).
VIEW_TRANSFORM = 'Standard'

# Canvas: the camera frame is CANVAS_WIDTH units wide; drawing happens on a
# flat sheet facing the camera.
CANVAS_WIDTH = 16.0

# Panels are painted at PAINT_RESOLUTION pixels. PAINT_FRAME of them fill the
# camera frame; the rest is bleed around it (room to reframe later).
PAINT_RESOLUTION = (2400, 1350)
PAINT_FRAME = (1920, 1080)
FIRST_LAYER_NAME = "Sketch"   # every new panel starts with this paint layer

# Cached panel images (what the timeline shows): the camera frame, this size.
# They're re-made once you've stopped painting for PANEL_IMAGE_DELAY seconds
# (making one briefly holds Blender up, so never mid-sketch).
PANEL_IMAGE_SIZE = (480, 270)
PANEL_IMAGE_DELAY = 2.5

SCRIPT_TEXT_NAME = "Script"
BRUSH_COLOR = (0.0, 0.0, 0.0)  # starting paint colour

# Tracks a new project starts with, top to bottom (as they appear).
# kind: "VIDEO" or "AUDIO". Video tracks stack above audio tracks.
DEFAULT_TRACKS = [
    # name          kind      ripple
    ("Panels",      "VIDEO",  True),
    ("Background",  "VIDEO",  False),
    ("Voice",       "AUDIO",  True),
    ("Music",       "AUDIO",  False),
]

# A new project starts with one empty panel so you can draw straight away.
STARTER_PANEL = True

# Timeline snapping off by default (Ollie): hold Ctrl while dragging / slicing
# to snap. The header magnet switches it on (then Ctrl stops it snapping).
SNAPPING = False
