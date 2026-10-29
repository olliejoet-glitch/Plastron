"""Timeline behaviour and track header look.

Default tracks for new projects are in project_defaults.py.
"""

# New panel length, in seconds.
NEW_PANEL_SECONDS = 2.0

# How close (in screen pixels) the mouse must be to a clip edge to grab it,
# and to a snap target (playhead, clip edge, marker) to snap to it.
EDGE_GRAB_PX = 8
SNAP_PX = 10

# Track row height when a project opens (screen pixels at 100 % UI scale).
# Tall enough for the timeline to show each panel's picture.
ROW_HEIGHT_PX = 64

# Timeline tools (S = Slice, A = back to this one): Blender's tool for
# clicking / dragging clips; Plastron adds edge dragging on top.
MOVE_TOOL = "builtin.select_box"
SLICE_LINE_COLOR = "orange"   # where a slice would cut (palette name or hex)

# Snap targets used while dragging clips and clip edges.
SNAP_TO_PLAYHEAD = True
SNAP_TO_CLIP_EDGES = True
SNAP_TO_MARKERS = True        # beat markers will be timeline markers

# Track header widgets, drawn left of Blender's own mute / lock buttons.
# Each: (id, label, which tracks show it). Reorder or delete lines freely.
HEADER_WIDGETS = [
    ("RIPPLE", "R", {"VIDEO", "AUDIO"}),
    ("SOLO",   "S", {"AUDIO"}),
    ("VOLUME", "",  {"AUDIO"}),
    ("COLLAPSE", "…", {"AUDIO"}),        # transcript bar: one line
]
HEADER_TOGGLE_PX = 18         # toggle button size
HEADER_VOLUME_PX = 54         # volume bar width
HEADER_GAP_PX = 4
HEADER_NATIVE_BUTTONS_PX = 44  # room Blender's mute + lock buttons take at the right

# Track header colours (palette names or hex, see theme.py).
HEADER_COLORS = {
    "toggle_off":    "bg",
    "toggle_on":     "orange",
    "toggle_text":   "text",
    "volume_back":   "bg_dark",
    "volume_fill":   "blue",
    "active_track":  "orange",     # bar at the left edge of the active track
    "video_track":   "#5d7a76",    # small kind marker
    "audio_track":   "#2f6a8a",
}
