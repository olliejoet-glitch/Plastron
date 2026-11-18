"""Voiceover recording and transcripts.

Recording and transcription use Python packages Blender doesn't ship with.
Plastron installs them once, in the background, into Blender's config folder
(an internet connection is needed the first time).
"""

# Recording
SAMPLE_RATE = 48000
CHANNELS = 1
AUDIO_FOLDER_SUFFIX = "_audio"     # recordings live in "<project>_audio/"

# Transcription (runs on your computer, once per take, after recording)
TRANSCRIBE_MODEL = "small.en"      # faster-whisper model: tiny.en, base.en, small.en, medium.en
# Whisper tidies away "um"s and false starts unless its prompt shows them.
TRANSCRIBE_PROMPT = "Umm, so, uh, I mean, like... let me, let me start again. Hmm, okay."

# Packages installed into Blender's Python the first time Plastron starts.
PACKAGES = {
    "sounddevice": "sounddevice",          # module name: pip name
    "faster_whisper": "faster-whisper",
}

# Transcript bar: the bottom band of each audio track's row.
BAR_FRACTION = 0.5          # how much of the row the bar takes (the rest shows the waveform)
WORD_GAP_PX = 5             # space between words
WORD_COLORS = {
    "text":      "text",
    "trimmed":   "#7d8f8c",     # words in a trimmed-off part of a clip
    "unspoken":  "orange",      # script words not recorded yet (script panel)
    "selected":  "orange",
    "hover":     "blue",
    "bar":       "bg_dark",
}

# The microphone list (the ▾ next to Record). Windows lists every input once
# per audio system (MME, DirectSound, WASAPI, WDM-KS); only the system the
# default microphone uses is shown (on Windows: MME, which lists only
# plugged-in, enabled inputs), with full names (MME cuts them at 31 letters).
# Inputs whose name contains one of these are left out: stand-ins and the
# virtual inputs that apps add (Voicemeeter, Steam, Oculus...), lower case.
# Anything else can be hidden from the list itself (its x button).
MIC_HIDE = ("sound mapper", "primary sound capture", "stereo mix", "what u hear", "wave out mix",
            "voicemeeter", "vb-audio", "cable output", "steam streaming", "oculus virt",
            "nvidia broadcast", "krisp", "virtual audio", "obs-", "discord")

# The script follows the playhead: the line being played is highlighted (a
# band behind it) and scrolled into view.
# Lines told apart in the script (Ollie): every other line faintly tinted (the
# space between lines is a blank line, config/timeline.py SCRIPT_PANELS
# "blank_line_between"); an optional strip where two lines touch.
SCRIPT_LINES = {
    "stripe": "#ffffff",  # (palette name or "#rrggbb")
    "stripe_alpha": 0.04,
    "gap_color": "bg_dark",
    "gap_alpha": 1.0,
    "gap_px": 0,          # a strip where two lines touch (pixels, 100 % UI scale; 0 = none)
}

SCRIPT_FOLLOW = {
    "color": "blue",      # (palette name or "#rrggbb")
    "alpha": 0.28,
    "scroll": True,       # keep the line in view while playing / scrubbing
    "row": 1.4,           # (band size: one text row = font size x this)
    "above": 1.0,         # band top above the line's first row (rows)
    "below": 0.15,        # band bottom under its last row (rows)
}
