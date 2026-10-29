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
