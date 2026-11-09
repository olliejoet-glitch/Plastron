"""Edit mode: cutting the real video on the same timeline.

The left area is the media bin (Blender's file browser: thumbnails; drag a
file onto the timeline, or select files and press Add to Timeline). Dropped
clips go on the track under the drop; their sound goes on its own track.
"""

# A video's own sound goes on this audio track (made if missing).
VIDEO_SOUND_TRACK = "Video Sound"

# Footage and panels never share a track: footage meant for a track with
# panels on it (e.g. dropped on "Panels") goes on this video track instead
# (made if missing, on top).
VIDEO_TRACK = "Video"
VIDEO_TRACK_RIPPLE = True     # (like Panels: putting a clip in pushes later ones along)

# A still picture dropped on the timeline lasts this long.
STILL_SECONDS = 5.0

# How big the preview plays footage: 'PROXY_50' = from half-size copies
# (made in the background when a video is added: lighter for 4K), 'SCENE' =
# the project's own preview size.
PREVIEW_SIZE = 'PROXY_50'
PROXY_BUILD = ("build_50",)          # which copies are made (build_25 / 50 / 75 / 100)

# Where the media bin starts (the first time): the project's folder once
# saved, else the first of these that exists ("~" = your home folder).
MEDIA_START = ("~/Videos", "~")

# The Clip panel (the preview's sidebar): speed buttons.
SPEED_BUTTONS = (0.5, 1.0, 2.0)

# The box around the selected clip in the preview: drag inside = move, a
# corner = size, just outside = turn (Shift: in steps).
FRAME_BOX = {
    "handle_px": 10,          # how near a corner counts as grabbing it
    "rotate_px": 40,          # how far outside the box still turns it
    "rotate_snap_deg": 15,
}

# Info windows (preview header: Window): a clip with its own timeline inside
# a UI frame. Styles: PNG frames whose middle is see-through, from
# plastron/presets/windows/ and your own folder (in Plastron's settings).
WINDOW_NAME = "Window"
WINDOW_SECONDS = 5.0           # a new window lasts this long (then: as long as what's in it)
WINDOW_SCALE = 0.5             # its size in the picture (1 = the frame's width)
WINDOW_USER_FOLDER = "plastron_windows"
WINDOW_CLEAR_ALPHA = 0.5       # how see-through counts as the opening

# Shorts reframing (preview header: Shorts): a 9:16 box per shot, dragged
# left / right in the preview; the YouTube Shorts export follows it.
SHORTS_ASPECT = (9, 16)
SHORTS_DIM = (0.0, 0.0, 0.0, 0.55)   # outside the box
