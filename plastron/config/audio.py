"""Audio mode (sound design): loudness, ducking, beats.

Loudness is measured like YouTube does (LUFS, ITU BS.1770); Normalise sets
clip volumes so each kind of sound lands on its target.
"""

# Normalise: target loudness per kind of clip (LUFS; YouTube plays at -14).
# A clip's kind comes from its track's name (else "other").
TARGETS = {"voice": -16.0, "music": -24.0, "other": -20.0}
VOICE_TRACKS = ("Voice", "Video Sound")
MUSIC_TRACKS = ("Music",)

# Auto-ducking: audio tracks with Duck on dip under the voice tracks.
DUCK_DB = -12.0               # how far they dip
DUCK_ATTACK = 0.15            # seconds to go down (starts this early)
DUCK_RELEASE = 0.5            # seconds to come back up
DUCK_THRESHOLD_DB = -40.0     # voice louder than this counts as talking
DUCK_GAP = 0.6                # pauses shorter than this stay ducked
DUCK_HOP = 0.05               # envelope step (seconds)

# Beats: tempo range looked for (BPM) and the marker name.
BEAT_BPM = (60, 190)
BEAT_MARKER = "beat"

# Analysis sample rate (lower = faster; loudness always uses 48 kHz).
ANALYSIS_RATE = 16000
