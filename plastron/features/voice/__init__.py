"""Voiceover: record at the playhead with retakes, local transcription,
transcript bars under audio tracks, cut by words, script linking.

    recorder           the microphone (sounddevice) -> WAV
    takes              voice clips and their takes (packed sounds + words)
    record             Record (Ctrl+R) and switching takes
    mic                choosing the microphone (the ▾ next to Record), remembered
    transcribe         one transcription job per take, in its own process
                       (transcribe_worker.py runs faster-whisper)
    transcript_bar     transcript bars (layout: transcript_layout), hover,
                       click, select, cut by words
    script_link        script lines <-> where they're spoken; unrecorded words
"""

import bpy

from ...config import voice as cfg
from ...core import deps
from ...timeline import header
from . import mic, record, script_link, takes, transcribe, transcript_bar

_MODULES = (takes, mic, record, transcribe, transcript_bar, script_link)


def draw_header(layout, context):
    row = layout.row(align=True)
    if record.recording():
        secs = record.elapsed()
        row.alert = True
        row.operator("plastron.voice_record", text=f"Stop  {int(secs // 60)}:{secs % 60:04.1f}",
                     icon='SNAP_FACE')
        meter = layout.row()
        meter.ui_units_x = 4
        import math
        db = 20 * math.log10(max(record.level(), 1e-4))          # (as heard: -60 dB empty .. 0 dB full)
        meter.alert = db > -1.0                                   # (too loud: it's clipping)
        meter.progress(factor=max(0.0, min(1.0, (db + 60) / 60)), type='BAR', text="Level")
    else:
        row.operator("plastron.voice_record", text="Record", icon='RECORD_OFF')
        row.popover("PLASTRON_PT_mic", text="", icon='DOWNARROW_HLT')
    sed = context.scene.sequence_editor
    strip = sed.active_strip if sed else None
    if takes.is_voice(strip) and strip.select:
        v = strip.plastron_voice
        sub = layout.row(align=True)
        if len(v.takes) > 1:
            sub.operator("plastron.voice_take", text="", icon='TRIA_LEFT').step = -1
            sub.label(text=f"Take {v.active + 1}/{len(v.takes)}")
            sub.operator("plastron.voice_take", text="", icon='TRIA_RIGHT').step = 1
        take = takes.active_take(strip)
        if take is not None and take.status in {'FAILED', 'NONE'}:
            sub.operator("plastron.voice_transcribe", text="Transcribe Again", icon='FILE_REFRESH')
    note = transcribe.status() or deps.status()
    if note:
        layout.label(text=note, icon='INFO')


def _setup():
    """Install the recording / transcription packages in the background,
    the first time Plastron starts (or after a failed try)."""
    deps.ensure(cfg.PACKAGES, "voice recording and transcripts")
    return None


def register():
    for module in _MODULES:
        module.register()
    header.add_section(draw_header)
    bpy.app.timers.register(_setup, first_interval=3.0)


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
