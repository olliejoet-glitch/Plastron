"""A long voice recording, in real time (Ollie: "if I record for 15 minutes
straight, would it encounter any bugs?"). Skipped unless
PLASTRON_LONG_MINUTES is set, e.g.:

    PLASTRON_LONG_MINUTES=15 PLASTRON_TEST_TIMEOUT=1800 python tests/run_tests.py long_recording

Records with the stand-in microphone (blocks arriving on a thread in real
time, like the real one) while the timeline plays (and loops: the project is
much shorter), then checks the take on the timeline, its file, transcription,
the transcript bar, Normalise, Remove Breaths, and save / reopen, timing each
and watching Blender's memory."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

MINUTES = float(os.environ.get("PLASTRON_LONG_MINUTES", "0") or 0)

record = h.module("features.voice.record")
takes = h.module("features.voice.takes")
transcribe = h.module("features.voice.transcribe")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")


def rss_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def steps():
    yield 1.0
    if not MINUTES:
        h.check("long recording test skipped (set PLASTRON_LONG_MINUTES to run it)", True)
        return
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base
    voice = next(t for t in tracks.all_tracks(sc) if tracks.name(sc, t) == "Voice")
    tracks.set_active(sc, voice)
    sc.frame_current = 1
    os.environ["PLASTRON_FAKE_WORDS"] = " ".join(f"word{i}" for i in range(int(MINUTES * 150)))  # ~150 words a minute
    start_mem = rss_mb()
    tl = h.area('SEQUENCE_EDITOR')
    h.move(*h.center(h.region(tl)))
    yield 0.2
    h.key('R', ctrl=True)
    rec_t0 = time.monotonic()
    yield 1.0
    h.check("recording started, the timeline playing", record.recording()
            and bpy.context.screen.is_animation_playing)
    seconds = MINUTES * 60
    t0 = time.monotonic()
    peak = 0.0
    loops = 0
    last = sc.frame_current
    while time.monotonic() - t0 < seconds:
        yield 15.0
        if sc.frame_current < last:
            loops += 1
        last = sc.frame_current
        peak = max(peak, rss_mb())
        print(f"LONG {time.monotonic() - t0:7.1f} s  frame {sc.frame_current:6d}  rss {rss_mb():7.1f} MB  "
              f"blocks {len(record._rec['mic'].chunks) if record.recording() else '-'}  "
              f"dropped {record._rec['mic'].dropped if record.recording() else '-'}", flush=True)
        if not record.recording():
            break
    still = record.recording()
    elapsed = time.monotonic() - t0
    h.check(f"still recording after {MINUTES:g} minutes (the playhead looping {loops}x over the short project)",
            still and bpy.context.screen.is_animation_playing, (still, elapsed))
    h.check("...memory stays sensible (under 600 MB more than at the start)", peak - start_mem < 600,
            (start_mem, peak))
    t = time.monotonic()
    h.key('R', ctrl=True)
    recorded = time.monotonic() - rec_t0          # (as long as it really ran: the loop overshoots a little)
    yield 2.0
    stop_s = time.monotonic() - t
    strip = bpy.context.scene.sequence_editor.active_strip
    seconds = recorded
    want = int(seconds * fps)
    h.check(f"the take lands on the Voice track at the start, {MINUTES:g} minutes long",
            strip is not None and takes.is_voice(strip) and strip.channel == tracks.channel_of(sc, voice)
            and clips.start(strip) == 1 and abs(clips.length(strip) - want) <= fps * 3,
            strip and (clips.start(strip), clips.length(strip), want))
    take = takes.active_take(strip)
    h.check("...packed into the project, with all its sound", take.sound.packed_file is not None
            and abs(take.duration - seconds) < 3, (take.duration, stop_s))
    h.check("...the project now ends with it", sc.frame_end >= clips.end(strip) - 1, (sc.frame_end, clips.end(strip)))
    t = time.monotonic()
    transcribe.wait_all(timeout=600)
    yield 1.0
    words = takes.words(takes.active_take(strip))
    h.check("transcribed: words all along the take", len(words) > MINUTES * 100 and words[-1][2] > seconds * 0.9,
            (len(words), words[-1] if words else None, round(time.monotonic() - t, 1)))
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.sequencer.view_all()
    h.redraw()
    yield 1.0
    h.screenshot("long_recording")

    for s in clips.all_clips(sc):
        s.select = s == strip
    t = time.monotonic()
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.audio_normalise(which='SELECTED')
    norm_s = time.monotonic() - t
    peak = max(peak, rss_mb())
    h.check("Normalise on the long take works", "plastron_lufs" in strip, round(norm_s, 1))
    t = time.monotonic()
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.breaths_remove()
    h.check("Remove Breaths on the long take works", True, round(time.monotonic() - t, 1))
    path = os.path.join(bpy.app.tempdir, "long", "Long.blend")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t = time.monotonic()
    bpy.ops.wm.save_as_mainfile(filepath=path)
    save_s = time.monotonic() - t
    size = os.path.getsize(path) / 1e6
    import shutil
    shutil.rmtree(os.path.join(bpy.app.tempdir, "plastron_recordings"), ignore_errors=True)   # (only the project)
    bpy.ops.wm.open_mainfile(filepath=path)
    yield 2.0
    sc = bpy.context.scene
    again = next((s for s in clips.all_clips(sc) if takes.is_voice(s)), None)
    take = takes.active_take(again) if again else None
    h.check("saved and reopened (the recording's temporary file gone): the take is there, whole, in the project",
            again is not None and abs(clips.length(again) - want) <= fps * 3
            and take.sound.packed_file is not None and take.sound.packed_file.size > seconds * 48000 * 2 * 0.95,
            (round(save_s, 1), round(size, 1), take and take.sound.packed_file and take.sound.packed_file.size))
    h.check("...and it sounds (read back from the project)",
            len(h.module("features.audio.analysis").clip_samples(sc, again, 16000)) > seconds * 16000 * 0.95)
    print(f"LONG summary: stop {stop_s:.1f} s, normalise {norm_s:.1f} s, save {save_s:.1f} s, "
          f"file {size:.0f} MB, memory {start_mem:.0f} -> peak {peak:.0f} MB", flush=True)


h.run(steps())
