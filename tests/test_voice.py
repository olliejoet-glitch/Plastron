"""Voice recording (a stand-in microphone), takes, transcription (a stand-in
transcriber that runs in its own process like the real one)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
record = h.module("features.voice.record")
takes = h.module("features.voice.takes")
transcribe = h.module("features.voice.transcribe")
bar = h.module("features.voice.transcript_bar")
script_link = h.module("features.voice.script_link")
timeline_view = h.module("timeline.view")


def scene():
    return bpy.context.scene


def track(name):
    return next(t for t in tracks.all_tracks(scene()) if tracks.name(scene(), t) == name)


def voice_clips():
    ch = tracks.channel_of(scene(), track("Voice"))
    return [s for s in clips.on_channel(scene(), ch)]


def span(strip):
    return (clips.start(strip), clips.end(strip))


def record_for(seconds):
    """Generator: Ctrl+R, wait, Ctrl+R (mouse over the timeline)."""
    h.key('R', ctrl=True)
    yield seconds
    if record.recording():
        h.key('R', ctrl=True)
    yield 0.3


def steps():
    yield 1.0
    sc = scene()
    tl = h.region(h.area('SEQUENCE_EDITOR'))
    h.move(tl.x + tl.width // 2, tl.y + 20)
    yield
    tracks.set_active(sc, track("Voice"))
    sc.frame_current = 10
    os.environ["PLASTRON_FAKE_WORDS"] = "hello there this is my first line"

    h.key('R', ctrl=True)
    yield 0.5
    h.check("Ctrl+R starts recording, and the timeline plays", record.recording()
            and bpy.context.screen.is_animation_playing)
    yield 1.0
    h.key('R', ctrl=True)
    yield 0.3
    sc = scene()
    vc = voice_clips()
    h.check("Ctrl+R again stops: a voice clip on the Voice track at the playhead",
            not record.recording() and len(vc) == 1 and clips.start(vc[0]) == 10, [span(s) for s in vc])
    first = vc[0]
    take = takes.active_take(first)
    h.check("...its length is the recording's", abs(clips.length(first) - take.duration * 24) <= 1
            and 1.0 < take.duration < 2.5, (clips.length(first), take.duration))
    h.check("...packed into the project", take.sound is not None and take.sound.packed_file is not None)
    h.check("...and waiting to be transcribed", take.status in {'WAITING', 'RUNNING'}, take.status)
    transcribe.wait_all()
    words = takes.words(takes.active_take(first))
    worker = h.module("features.voice.transcribe_worker")
    wav_path = os.path.join(bpy.app.tempdir, "plastron_test_tone.wav")
    import numpy as np
    import wave as wavmod
    tone = (np.sin(2 * np.pi * 440 * np.arange(48000) / 48000) * 16000).astype(np.int16)
    with wavmod.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(tone.tobytes())
    audio = worker.load_audio(wav_path)
    spectrum = np.abs(np.fft.rfft(audio))
    h.check("recordings are handed to Whisper as 16 kHz audio (no audio decoder needed)",
            audio.dtype == np.float32 and len(audio) == 16000 and 0.4 < np.abs(audio).max() < 0.55
            and abs(np.argmax(spectrum) - 440) <= 1, (len(audio), float(np.abs(audio).max())))
    h.check("the transcript arrives (words with times)",
            [w for w, _s, _e in words] == "hello there this is my first line".split()
            and all(0 <= s < e <= take.duration + 0.01 for _w, s, e in words), words)

    # A second clip later on, then a retake of the first: shorter, so the
    # second clip moves up (Voice ripples).
    sc.frame_current = 100
    os.environ["PLASTRON_FAKE_WORDS"] = "second clip words"
    yield from record_for(1.0)
    second = [s for s in voice_clips() if clips.start(s) == 100]
    h.check("recording somewhere empty makes another clip", len(second) == 1, [span(s) for s in voice_clips()])
    second = second[0]
    first_len, second_start = clips.length(first), clips.start(second)
    sc.frame_current = 20                          # inside the first clip
    os.environ["PLASTRON_FAKE_WORDS"] = "hello again"
    yield from record_for(0.6)
    sc = scene()
    h.check("recording over a voice clip adds a take of it", len(first.plastron_voice.takes) == 2
            and first.plastron_voice.active == 1, len(first.plastron_voice.takes))
    h.check("...starting at the clip's start, with the new take's length",
            clips.start(first) == 10 and clips.length(first) < first_len, span(first))
    h.check("...and ripple moves the next clip up",
            clips.start(second) == second_start - (first_len - clips.length(first)),
            (second_start, clips.start(second)))
    h.check("...the old take isn't left muted", not first.mute)

    # Switch back to take 1.
    for s in clips.all_clips(sc):
        s.select = False
    first.select = True
    sc.sequence_editor.active_strip = first
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.voice_take(step=-1)
    h.check("switching back to take 1 restores its length (and ripples)",
            first.plastron_voice.active == 0 and clips.length(first) == first_len
            and clips.start(second) == second_start, (span(first), span(second)))

    # Space (stopping playback) stops recording too.
    sc.frame_current = 300
    h.key('R', ctrl=True)
    yield 0.6
    h.key('SPACE')
    yield 0.6
    h.check("stopping playback stops recording", not record.recording()
            and any(clips.start(s) == 300 for s in voice_clips()), [span(s) for s in voice_clips()])
    transcribe.wait_all()
    h.check("every take gets transcribed",
            all(t.status == 'DONE' for _s, t in takes.all_takes(scene())),
            [(t.status, t.error) for _s, t in takes.all_takes(scene())])
    h.screenshot("voice")

    # --- Transcript bar -----------------------------------------------------------------
    sc = scene()
    area = h.area('SEQUENCE_EDITOR')
    region = h.region(area)
    timeline_view.frame(h.window(), area, region, sc)
    yield 0.5
    h.redraw()
    boxes, _ell, bands = bar.layout_for(region, sc)
    first_words = [b for b in boxes if b["strip"] == first.name]
    said = "hello there this is my first line".split()
    shown = [b["text"] for b in first_words]
    _boxes, ellipses, _bands = bar.layout_for(region, sc)
    h.check("each voice clip's words show in its track's transcript bar (in order, '…' if they don't all fit)",
            len(bands) == 2 and len(shown) >= 3 and shown == said[:len(shown)]
            and (len(shown) == len(said) or ellipses), shown)
    x0 = region.view2d.view_to_region(clips.start(first), 0, clip=False)[0]
    x1 = region.view2d.view_to_region(clips.end(first), 0, clip=False)[0]
    h.check("...inside the clip's edges", all(x0 <= b["x"] and b["x"] + b["w"] <= x1 + 1 for b in first_words))
    again = bar.layout_for(region, sc)[0]
    h.check("the layout is kept (not redone) while nothing changes", again is boxes)

    # Click a word: playhead jumps there.
    word = first_words[2]
    h.move(region.x + word["x"] + word["w"] / 2, region.y + word["y"] + word["h"] / 2)
    yield 0.2
    h.check("hovering a word lights it up", bar._hover["box"] is not None
            and bar._hover["box"]["text"] == "this")
    h.screenshot("transcript_hover")
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.3
    h.check("clicking a word moves the playhead to it", sc.frame_current == round(word["f0"]),
            (sc.frame_current, word["f0"]))
    # Shift+click a later word selects the run; Delete cuts that audio.
    word2 = first_words[3]
    h.move(region.x + word2["x"] + word2["w"] / 2, region.y + word2["y"] + word2["h"] / 2)
    yield
    h._event('LEFT_SHIFT', 'PRESS')
    h._event('LEFTMOUSE', 'PRESS', shift=True)
    h._event('LEFTMOUSE', 'RELEASE', shift=True)
    h._event('LEFT_SHIFT', 'RELEASE')
    yield 0.3
    h.check("Shift+click selects a run of words", bar.selection()["indices"] == {2, 3},
            bar.selection()["indices"])
    total_before = sum(clips.length(s) for s in voice_clips())
    h.key('DEL')
    yield 0.5
    sc = scene()
    pieces = sorted((s for s in voice_clips() if takes.is_voice(s) and clips.start(s) < 60),
                    key=clips.start)
    cut_len = total_before - sum(clips.length(s) for s in voice_clips())
    h.check("Delete cuts those words' audio: the clip is split around them and closes up (ripple)",
            len(pieces) == 2 and clips.end(pieces[0]) == clips.start(pieces[1]) and cut_len > 0,
            ([span(p) for p in pieces], cut_len))
    h.redraw()
    yield 0.2
    boxes, _e, _b = bar.layout_for(region, sc)

    def heard(strip):          # words whose middle is inside the clip
        out = []
        for w, ws, we in takes.words(takes.active_take(strip)):
            mid = bar.word_frame(sc, strip, (ws + we) / 2)
            if clips.start(strip) <= mid < clips.end(strip):
                out.append(w)
        return out
    texts = heard(pieces[0]) + heard(pieces[1])
    h.check("...and those words are gone (the rest still line up with their audio)",
            texts == ["hello", "there", "my", "first", "line"], texts)
    wrong = [(b["strip"], b["text"]) for b in boxes if b["strip"] in {p.name for p in pieces}
             and b["trimmed"] == (b["text"] in heard(sc.sequence_editor.strips_all[b["strip"]]))]
    h.check("...each piece greys out exactly the words trimmed off it", not wrong, wrong)

    # Collapse: one line with "…".
    voice = track("Voice")
    voice.collapse = True
    h.redraw()
    yield 0.2
    boxes, ellipses, _b = bar.layout_for(region, sc)
    lines = {round(b["baseline"]) for b in boxes if b["strip"] == pieces[0].name}
    h.check("collapsing a track's bar shows one line", len(lines) <= 1, lines)
    voice.collapse = False

    # Zoomed far in, words sit at their exact times.
    sc.frame_current = clips.start(pieces[0])
    with h.override('SEQUENCE_EDITOR'):
        for _i in range(12):
            bpy.ops.view2d.zoom_in()
        bpy.ops.sequencer.view_frame()
    yield 0.3
    h.redraw()
    boxes, _e, _b = bar.layout_for(region, sc)
    exact = [b for b in boxes if b["strip"] == pieces[0].name and not b["trimmed"]]
    h.check("zoomed in, words sit at their exact times",
            exact and all(abs(b["x"] - region.view2d.view_to_region(b["f0"], 0, clip=False)[0]) < 1
                          for b in exact), [(b["text"], b["x"]) for b in exact])
    h.screenshot("transcript_zoomed")

    # --- Script linking -------------------------------------------------------------------
    text = bpy.data.texts["Script"]
    text.from_string("Hello there!\nThis is my first line.\nA line we have not recorded yet.\n")
    lines, unspoken = script_link.match(sc, text)
    heard = dict((w, f) for w, f in reversed(script_link.spoken(sc)))
    h.check("script lines are matched to where they're spoken",
            lines.get(0) == heard["hello"] and lines.get(1) == heard["my"], (lines, heard))
    gone = {text.lines[li].body[c0:c1] for li, c0, c1 in unspoken}
    h.check("script words not recorded yet are found", {"not", "recorded", "yet", "This", "is"} <= gone
            and "Hello" not in gone, gone)
    script = h.area('TEXT_EDITOR')
    sregion = h.region(script)
    with h.override('TEXT_EDITOR'):
        x, y = script.spaces.active.region_location_from_cursor(1, 3)
    sc.frame_current = 400
    h.move(sregion.x + x + 2, sregion.y + y + 6)
    yield
    h._event('LEFTMOUSE', 'PRESS')
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.4
    h.check("clicking a script line moves the playhead to where it's spoken",
            sc.frame_current == round(heard["my"]) and text.current_line_index == 1,
            (sc.frame_current, heard["my"], text.current_line_index))
    h.type_text("x")
    yield 0.2
    h.check("...and the script can still be edited there", "x" in text.lines[1].body, text.lines[1].body)
    h.screenshot("script_link")

    # Transcribe again (from the packed take).
    t = takes.active_take(pieces[0])
    t.words_json, t.status = "", 'FAILED'
    os.environ["PLASTRON_FAKE_WORDS"] = "redone words"
    for s in clips.all_clips(sc):
        s.select = False
    pieces[0].select = True
    sc.sequence_editor.active_strip = pieces[0]
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.voice_transcribe()
    transcribe.wait_all()
    h.check("Transcribe Again re-reads a take from the project",
            [w for w, _s, _e in takes.words(takes.active_take(pieces[0]))] == ["redone", "words"])


h.run(steps())
