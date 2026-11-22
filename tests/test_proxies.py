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
                    "-i", "testsrc=size=640x360:rate=30:duration=3", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", movie], check=True)
    made = media.place(sc, movie, frame=100)
    video = made[0]
    files = proxies.proxy_files(video)
    for _ in range(300):
        yield 0.1
        if all(os.path.exists(p) and os.path.getsize(p) > 0 for p in files):
            break
    yield 0.5
    h.check("placed footage gets its half-size preview copy", all(os.path.exists(p) for p in files), files)
    h.check("...and then counts as having one", not proxies.missing(video))
    h.check("...plays from it in the preview", video.use_proxy and video.proxy.build_50)


h.run(steps())
