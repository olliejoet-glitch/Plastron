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
