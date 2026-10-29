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

# Canvas: the camera frame is CANVAS_WIDTH units wide; drawing happens on the
# flat plane facing the camera.
CANVAS_WIDTH = 16.0

SCRIPT_TEXT_NAME = "Script"
STROKE_COLOR = (0.0, 0.0, 0.0, 1.0)
