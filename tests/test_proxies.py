"""Preview copies (features/edit/proxies.py): placed footage gets its
half-size copy built (the preview plays from it, not the full-size video)."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
proxies = h.module("features.edit.proxies")


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "proxy")
    os.makedirs(folder, exist_ok=True)
    movie = os.path.join(folder, "big.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1920x1080:rate=30:duration=10", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", movie], check=True)
    bpy.context.window_manager.plastron_mode = 'Edit'
    yield 1.0
    import time as _t
    t0 = _t.time()
    made = media.place(sc, movie, frame=100)
    print("PLACE took", _t.time() - t0)
    video = made[0]
    yield 0.2
    h.check("while the copy is made (in the background: placing doesn't wait for it), the preview header says so",
            proxies.building(sc) == 1, (proxies.building(sc), proxies._building, proxies.missing(video)))
    h.redraw()
    yield 0.3
    h.screenshot("proxies_building")
    files = proxies.proxy_files(video)
    for _ in range(300):
        yield 0.1
        if all(os.path.exists(p) and os.path.getsize(p) > 0 for p in files):
            break
    yield 0.5
    h.check("placed footage gets its half-size preview copy", all(os.path.exists(p) for p in files), files)
    h.check("...and then counts as having one", not proxies.missing(video))
    h.check("...plays from it in the preview", video.use_proxy and video.proxy.build_50)
    h.check("...and the notice goes", proxies.building(sc) == 0, proxies.building(sc))

    meter = h.module("features.edit.playback_meter")
    sc.frame_current = 100
    with h.override('PREVIEW'):
        bpy.ops.screen.animation_play()
    for _ in range(30):
        yield 0.1
        h.redraw()
    with h.override('PREVIEW'):
        rate = meter.fps()
    h.screenshot("playback_meter")
    with h.override('PREVIEW'):
        bpy.ops.screen.animation_cancel(restore_frame=False)
    yield 0.3
    h.check("while playing, the preview header shows the frames really drawn per second", rate is not None and rate > 0,
            rate)


h.run(steps())
