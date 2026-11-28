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

# Breath remover: breaths in voice clips (short, quiet, noise-like) dip by
# BREATH_DB. Found in 20 ms steps.
BREATH_DB = -18.0
BREATH_SECONDS = (0.1, 1.0)       # how long a breath can be
BREATH_BELOW_SPEECH_DB = 12.0     # at least this much quieter than the voice's loud parts
BREATH_ABOVE_FLOOR_DB = 3.0       # ...and this much louder than the silence (was 6: quiet breaths were missed)
BREATH_SIBILANT_HZ = 4000         # sibilants ("s", "sh") put most of their energy above this...
BREATH_MAX_HIGH = 0.6             # ...a breath has less than this share up there (white noise: 0.5)
BREATH_SIBILANT_SMOOTH = 0.1      # seconds that share is averaged over
BREATH_FLATNESS = 0.12            # how noise-like (0 = a pure tone, 1 = white noise; no transcript only)
BREATH_RAMP = 0.03                # seconds to dip in / out
BREATH_COLOR = "#f0c850"          # found breaths tinted on the timeline (palette name or "#rrggbb")
BREATH_ALPHA = 0.45

# Creature voices: the voice baked into a stack of pitched copies (same
# length), put on the "Creature" track under it; the plain voice is muted.
# Each: the voice itself (dry_db) + layers (semitones up / down, level dB).
CREATURE_TRACK = "Creature"
CREATURES = {
    "Ogre":   {"dry_db": -4.0, "layers": [(-12, 0.0), (-7, -6.0)]},
    "Goblin": {"dry_db": -3.0, "layers": [(7, -2.0), (12, -8.0)]},
    "Demon":  {"dry_db": -8.0, "layers": [(-12, 0.0), (-19, -3.0), (-5, -9.0)]},
    "Robot":  {"dry_db": -2.0, "layers": [(0.3, -3.0), (-0.3, -3.0), (12, -14.0)]},
}

# Music fitting: Fit to Video stretches the music a little (at most
# FIT_MAX_STRETCH) so a beat lands on the video's end, cuts it there and
# fades it out over FIT_FADE seconds.
FIT_MAX_STRETCH = 0.08
FIT_FADE = 1.0

# Level Voice (Sound Tools): evens out quiet / loud stretches INSIDE a
# recording (talking softly, leaning back from the mic). A smooth gain curve
# brings each stretch towards the voice's typical level.
LEVEL_STEP = 0.05                 # seconds per loudness step
LEVEL_WINDOW = 1.5                # seconds of speech averaged for "how loud is it here"
LEVEL_MIN_SPEECH = 0.3            # seconds of speech a window needs to count
LEVEL_SPEECH_RANGE_DB = 30.0      # speech: within this of the voice's loud parts...
LEVEL_ABOVE_FLOOR_DB = 8.0        # ...and this much over the silence
LEVEL_AMOUNT = 0.9                # how much of the difference is made up (1 = all of it)
LEVEL_MAX_BOOST = 12.0            # dB a quiet stretch can come up
LEVEL_MAX_CUT = 6.0               # dB a loud stretch can come down
LEVEL_PAUSE = 1.0                 # pauses longer than this get no boost (room noise stays put)
LEVEL_SMOOTH = 0.4                # seconds of smoothing (no pumping)
LEVEL_TOLERANCE_DB = 0.3          # curve points kept where it moves this much
