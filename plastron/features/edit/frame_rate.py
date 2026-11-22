"""Frame rate check (Ollie: "I've filmed on my phone camera, so I'm worried a
variable frame rate will steadily cause the audio and video to drift out of
sync").

What was found (tested): Blender shows each frame of a variable-frame-rate
video at its own timestamp, so VFR alone doesn't drift. What DID put phone
footage out of sync: a 30 fps video in the 24 fps project played every
frame as a project frame (25 % slow: 20 s of picture over 25 s, its sound
20 s). Footage is now placed playing at its real speed (media.place ->
match_rate), and the check fixes clips placed before.

Check Frame Rate (Clip panel, a selected video): reads the file's own frame
timing (MP4 / MOV: every frame's duration from its "stts" table, pure
Python) and shows: the frame rate it was filmed at (constant or variable:
the range), the project's, and whether the clip plays at real speed here
(else Play at Real Speed fixes it).
"""

import os
import struct

import bpy

from ...timeline import clips, events, ripple

CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts"}


# --- reading the file (pure) --------------------------------------------------------------

def _boxes(f, start, end):
    """(type, payload start, payload end) of the boxes between start and end."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        head = f.read(8)
        if len(head) < 8:
            return
        size, kind = struct.unpack(">I4s", head)
        body = pos + 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            body = pos + 16
        elif size == 0:
            size = end - pos
        if size < 8:
            return
        yield kind, body, min(pos + size, end)
        pos += size


def _find(f, start, end, kind):
    return next(((b, e) for k, b, e in _boxes(f, start, end) if k == kind), None)


def read_tracks(path):
    """[{"kind": "vide" / "soun", "timescale", "duration" (s), "deltas":
    [(count, ticks)]}] for each track of an MP4 / MOV file; None if it
    can't be read."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            moov = _find(f, 0, size, b"moov")
            if moov is None:
                return None
            out = []
            for kind, b, e in _boxes(f, *moov):
                if kind != b"trak":
                    continue
                mdia = _find(f, b, e, b"mdia")
                if mdia is None:
                    continue
                hdlr, mdhd = _find(f, *mdia, b"hdlr"), _find(f, *mdia, b"mdhd")
                minf = _find(f, *mdia, b"minf")
                stbl = _find(f, *minf, b"stbl") if minf else None
                stts = _find(f, *stbl, b"stts") if stbl else None
                if not (hdlr and mdhd and stts):
                    continue
                f.seek(hdlr[0] + 8)
                handler = f.read(4).decode("latin-1")
                f.seek(mdhd[0])
                version = f.read(1)[0]
                if version == 1:
                    f.seek(mdhd[0] + 4 + 16)
                    timescale, duration = struct.unpack(">IQ", f.read(12))
                else:
                    f.seek(mdhd[0] + 4 + 8)
                    timescale, duration = struct.unpack(">II", f.read(8))
                f.seek(stts[0] + 4)
                n = struct.unpack(">I", f.read(4))[0]
                raw = f.read(8 * n)
                deltas = [struct.unpack_from(">II", raw, 8 * i) for i in range(len(raw) // 8)]
                out.append({"kind": handler, "timescale": timescale,
                            "duration": duration / timescale if timescale else 0.0, "deltas": deltas})
            return out
    except (OSError, struct.error, IndexError):
        return None


def video_timing(tracks):
    """From read_tracks: {"frames", "seconds", "fps" (average), "min_fps",
    "max_fps", "variable", "sound_seconds"} or None."""
    vid = next((t for t in tracks or [] if t["kind"] == "vide"), None)
    if vid is None or not vid["timescale"]:
        return None
    ts = vid["timescale"]
    frames = sum(c for c, _d in vid["deltas"])
    ticks = sum(c * d for c, d in vid["deltas"])
    seconds = ticks / ts if ticks else vid["duration"]
    real = [d for c, d in vid["deltas"] if d > 0]
    if not frames or not seconds or not real:
        return None
    # Frame rate over each run of equal frame lengths, weighted: the steady
    # range (one odd frame at a cut doesn't make a file "variable").
    runs = sorted((ts / d, c) for c, d in vid["deltas"] if d > 0)
    total = sum(c for _r, c in runs)
    cut = max(1, total // 100)            # (ignore the slowest / fastest 1 %)

    def at(k):
        acc = 0
        for rate, c in runs:
            acc += c
            if acc > k:
                return rate
        return runs[-1][0]
    lo, hi = at(cut - 1), at(total - cut)
    snd = next((t for t in tracks if t["kind"] == "soun"), None)
    return {"frames": frames, "seconds": seconds, "fps": frames / seconds, "min_fps": lo, "max_fps": hi,
            "variable": hi - lo > 0.05 * (frames / seconds),
            "sound_seconds": snd["duration"] if snd else None}


# --- playing at real speed ----------------------------------------------------------------

def project_fps(scene):
    return scene.render.fps / scene.render.fps_base


def speed_of(strip):
    return float(strip.get("plastron_speed", 1.0))


MEDIA_S = "plastron_media_s"     # strip: how long its whole video really is (s)


def media_seconds(strip):
    """How long the clip's whole video really is. Blender counts a movie in
    its own frames (frame_duration / fps) until it's retimed; after that
    frame_duration is timeline frames, so the length is kept when Plastron
    retimes it (or read from the file)."""
    if MEDIA_S in strip:
        return float(strip[MEDIA_S])
    if not len(strip.retiming_keys) and strip.fps:
        return strip.frame_duration / strip.fps
    info = video_timing(read_tracks(bpy.path.abspath(strip.filepath)))
    return info["seconds"] if info else 0.0


def plays_at(scene, strip):
    """How fast the clip's picture plays compared with real time (1 = real
    speed, not counting a speed set on purpose in the Clip panel)."""
    whole = strip.content_end - strip.content_start           # timeline frames of all the media
    media_s = media_seconds(strip)
    if whole <= 0 or media_s <= 0:
        return 1.0
    return media_s * project_fps(scene) / whole / speed_of(strip)


def match_rate(scene, strip):
    """Make a video play at its real speed in this project (its frame rate
    differs from the project's). Returns True if it changed."""
    if strip.type != 'MOVIE' or not strip.fps:
        return False
    strip[MEDIA_S] = media_seconds(strip)
    rate = plays_at(scene, strip)
    if abs(rate - 1.0) < 0.002:
        return False
    target = speed_of(strip) / rate
    if not ripple._retime(scene, strip, target):
        return False
    return True


class PLASTRON_OT_clip_frame_rate(bpy.types.Operator):
    """Check the selected video's frame rate (variable? plays at real speed here?)"""
    bl_idname = "plastron.clip_frame_rate"
    bl_label = "Check Frame Rate"

    @classmethod
    def poll(cls, context):
        sed = context.scene.sequence_editor
        s = sed.active_strip if sed else None
        return s is not None and s.type == 'MOVIE'

    def invoke(self, context, _event):
        return context.window_manager.invoke_popup(self, width=round(380 * context.preferences.system.ui_scale))

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        scene = context.scene
        strip = scene.sequence_editor.active_strip
        layout = self.layout
        layout.label(text=strip.name, icon='FILE_MOVIE')
        info = video_timing(read_tracks(bpy.path.abspath(strip.filepath)))
        col = layout.column(align=True)
        if info is None:
            col.label(text=f"Frame rate: {strip.fps:.2f} fps (this kind of file's timing can't be read)")
        elif info["variable"]:
            col.label(text=f"Variable frame rate: {info['min_fps']:.1f}-{info['max_fps']:.1f} fps "
                           f"(average {info['fps']:.2f})", icon='INFO')
            col.label(text="Frames are shown at their own times: no drift from this.")
        else:
            col.label(text=f"Constant frame rate: {info['fps']:.2f} fps", icon='CHECKMARK')
        if info and info["sound_seconds"] is not None and abs(info["sound_seconds"] - info["seconds"]) > 0.1:
            col.label(text=f"In the file: picture {info['seconds']:.1f} s, sound {info['sound_seconds']:.1f} s",
                      icon='ERROR')
        col.label(text=f"Project: {project_fps(scene):g} fps")
        rate = plays_at(scene, strip)
        if abs(rate - 1.0) < 0.002:
            col.label(text="Plays at real speed here: in sync with its sound.", icon='CHECKMARK')
        else:
            row = layout.row()
            row.alert = True
            row.label(text=f"Plays at {rate * 100:.0f} % speed here: it drifts from its sound", icon='ERROR')
            layout.operator("plastron.clip_real_speed", icon='TIME')


class PLASTRON_OT_clip_real_speed(bpy.types.Operator):
    """Make the selected videos play at their real speed (their frame rate differs from the project's)"""
    bl_idname = "plastron.clip_real_speed"
    bl_label = "Play at Real Speed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        sed = scene.sequence_editor
        todo = {s for s in clips.top_clips(scene) if s.select and s.type == 'MOVIE'}
        if sed.active_strip is not None and sed.active_strip.type == 'MOVIE':
            todo.add(sed.active_strip)
        done = 0
        for strip in todo:
            s = clips.start(strip)
            if match_rate(scene, strip):
                done += 1
                partners = [p for p in clips.linked(strip) if p.type == 'SOUND']
                if partners and clips.end(strip) > clips.end(partners[0]) + 1:
                    strip.right_handle = clips.end(partners[0])
                if clips.start(strip) != s:
                    strip.content_start += s - clips.start(strip)
        events.clips_changed(scene)
        self.report({'INFO'}, f"{done} video{'s' if done != 1 else ''} now play at real speed" if done
                    else "Already at real speed")
        return {'FINISHED'}


classes = (PLASTRON_OT_clip_frame_rate, PLASTRON_OT_clip_real_speed)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
