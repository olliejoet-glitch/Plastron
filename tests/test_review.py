"""Stage 7 (planning and review): shot status (and the clip's colour), panel
notes, framing guides."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

cfg = h.module("config.review")
notes = h.module("features.review.notes")
guides = h.module("features.review.guides")
canvas_sync = h.module("features.storyboard.canvas_sync")
user_settings = h.module("core.user_settings")


def steps():
    yield 1.0
    sc = bpy.context.scene
    strip = canvas_sync.panel_on_canvas(sc)
    info = strip.plastron_panel
    h.check("a panel starts as a sketch", info.status == "SKETCH")
    info.status = "BLOCKING"
    h.check("setting its status colours its clip on the timeline",
            strip.color_tag == dict((s, t) for s, _l, t, _h in cfg.STATUS)["BLOCKING"], strip.color_tag)
    info.note = "Slow push in; door creak"
    h.check("panels keep notes", strip.plastron_panel.note == "Slow push in; door creak")
    h.redraw()
    yield 0.3
    h.screenshot("panel_info")

    # Guides: toggles remembered; thirds / safe areas / 9:16 drawn in the frame.
    wm = bpy.context.window_manager
    for gid, _label in cfg.GUIDES:
        setattr(wm, guides._prop_name(gid), True)
    h.check("guides toggle on and are remembered",
            set(user_settings.get("guides")) == {g for g, _l in cfg.GUIDES})
    from mathutils import Vector
    frame = (Vector((0, 0)), Vector((160, 0)), Vector((160, 90)), Vector((0, 90)))
    ls = guides.lines(frame, {"THIRDS"})
    xs = sorted({round(p.x, 3) for _c, pts in ls for p in pts if 0 < p.x < 160})
    h.check("rule of thirds lines at a third and two thirds", xs == [53.333, 106.667], xs)
    short = guides.lines(frame, {"SHORT"})[0][1]
    width = max(p.x for p in short) - min(p.x for p in short)
    h.check("the 9:16 frame is full height, 9/16 of it wide", abs(width - 90 * 9 / 16) < 1e-3, width)
    h.move(*h.center(h.region(h.area('VIEW_3D'))))
    yield 0.5
    h.redraw()
    yield 1.0                         # (through the camera the screen updates on a real redraw)
    h.screenshot("guides")
    for gid, _label in cfg.GUIDES:
        setattr(wm, guides._prop_name(gid), False)
    h.check("...and off again", not guides.shown())

    # --- Temp sounds: a bin (folder; subfolders are tags), dropped at the playhead.
    import wave
    import numpy as np
    sounds = h.module("features.review.sounds")
    tag_dir = os.path.join(sounds.folder(), "doors")
    os.makedirs(tag_dir, exist_ok=True)
    wav = os.path.join(tag_dir, "creak.wav")
    tone = (np.sin(2 * np.pi * 330 * np.arange(48000) / 48000) * 12000).astype(np.int16)
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(tone.tobytes())
    found = sounds.matching("door")
    h.check("the bin finds sounds by tag", [n for n, _t, _p in found] == ["creak"], found)
    sc.frame_current = 10
    s1 = sounds.drop(sc, wav)
    s2 = sounds.drop(sc, wav)
    clips = h.module("timeline.clips")
    tracks = h.module("timeline.tracks")
    track = sounds.temp_track(sc)
    h.check("dropped at the playhead on a Temp Sounds track, pink and named TEMP",
            clips.start(s1) == 10 and s1.channel == tracks.channel_of(sc, track)
            and s1.name.startswith("TEMP ") and s1.color_tag == cfg.TEMP_SOUND_COLOR and sounds.is_temp(s1))
    h.check("a second drop goes after the first", clips.start(s2) == clips.end(s1) and s2.channel == s1.channel,
            (clips.start(s2), clips.end(s1)))
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.sounds_select_temp()
    h.check("Select Temp Sounds finds them", s1.select and s2.select)

    # --- Speed playback: the sound sped up with its pitch kept; the picture faster.
    speed = h.module("features.review.speed")
    with h.override('SEQUENCE_EDITOR'):
        path = speed.mixdown(bpy.context)
    snd = speed.stretched(path, 2.0, 0.0)
    out = os.path.join(bpy.app.tempdir, "speed_test.wav")
    import aud
    snd.write(out, 48000, aud.CHANNELS_MONO, aud.FORMAT_S16, aud.CONTAINER_WAV)
    with wave.open(out) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
        rate = w.getframerate()
    fps = sc.render.fps / sc.render.fps_base
    mix_seconds = (sc.frame_end - sc.frame_start + 1) / fps
    piece = data[int(10 / fps / 2 * rate) + 200:int(10 / fps / 2 * rate) + 200 + 8192]
    peak = np.argmax(np.abs(np.fft.rfft(piece))) * rate / len(piece)
    h.check("2x: half as long, same pitch", abs(len(data) / rate - mix_seconds / 2) < 0.3 and abs(peak - 330) < 15,
            (len(data) / rate, mix_seconds / 2, peak))
    base = sc.render.fps_base
    sc.frame_current = 1
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.play_speed(speed=2.0)
    yield 0.4
    h.check("playing at 2x: picture twice as fast, the project's own sound muted",
            abs(sc.render.fps_base - base / 2) < 1e-6 and not sc.use_audio)
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.play_speed(speed=2.0)
    yield 0.4
    h.check("...and stopping puts it all back", abs(sc.render.fps_base - base) < 1e-6 and sc.use_audio)
    h.screenshot("timeline_header")


h.run(steps())
