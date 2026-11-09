"""Exports (stage 7), in the File menu:

    animatic   the animatic as a video (panels, voice, music)
    sheet      every panel as a printable PDF grid, notes underneath
    shotlist   the panels' notes as a shot list (CSV)
    video      Export Video with presets (YouTube 4K...), Export Frame (PNG)
    captions   Export Captions (.srt) from the voice transcripts
"""

from . import animatic, captions, sheet, shotlist, video

_MODULES = (animatic, sheet, shotlist, video, captions)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()


def panels_in_order(scene):
    """Every panel, in time order (then top track first)."""
    from ...timeline import clips
    from ..storyboard.panels import all_panels
    return sorted(all_panels(scene), key=lambda s: (clips.start(s), -s.channel))


def timecode(scene, frame):
    fps = scene.render.fps / scene.render.fps_base
    f = frame - scene.frame_start
    seconds, frames = divmod(f, round(fps))
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}+{int(frames):02d}"


def status_label(strip):
    from ...config import review
    sid = getattr(strip.plastron_panel, "status", "")
    return next((label for s, label, _t, _h in review.STATUS if s == sid), "")
