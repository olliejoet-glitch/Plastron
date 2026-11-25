"""Copy / paste clip attributes (features/edit/attributes.py): Ctrl+C over
the timeline copies the selected clip's position / size / grade / fades...;
pasting puts the chosen ones on the selected clips."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

media = h.module("features.edit.media")
clips = h.module("timeline.clips")
attrs = h.module("features.edit.attributes")
grade = h.module("features.grade.grade")
panels = h.module("features.storyboard.panels")


def steps():
    yield 1.0
    sc = bpy.context.scene
    folder = os.path.join(bpy.app.tempdir, "attrs")
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name in ("a", "b"):
        p = os.path.join(folder, name + ".mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc=size=320x180:rate=24:duration=3", "-f", "lavfi", "-i",
                        "sine=frequency=300:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", p], check=True)
        paths.append(p)
    a = next(s for s in media.place(sc, paths[0], frame=200) if s.type == 'MOVIE')
    b = next(s for s in media.place(sc, paths[1], frame=400) if s.type == 'MOVIE')
    a_sound = clips.linked(a)[0]
    yield 0.3
    a.transform.offset_x, a.transform.offset_y = 120.0, -40.0
    a.transform.scale_x = a.transform.scale_y = 0.6
    a.transform.rotation = 0.3
    a.crop.min_x = 10
    a.use_flip_x = True
    a.plastron.opacity = 0.5
    a.plastron.fade_in = 6
    grade.ensure(a)
    grade.apply(a, {"bright": 0.2, "saturation": 0.4})
    a_sound.plastron.volume = 0.3
    b_scale = b.transform.scale_x
    for s in clips.top_clips(sc):
        s.select = s == a
    sc.sequence_editor.active_strip = a
    area = h.area('SEQUENCE_EDITOR')
    reg = h.region(area)
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    h.key('C', ctrl=True)
    yield 0.3
    got = attrs._clipboard
    h.check("Ctrl+C over the timeline copies the selected clip's attributes",
            got.get("position") == (120.0, -40.0) and abs(got["size"][0] - 0.6) < 1e-6 and "grade" in got,
            got)
    h.check("...its linked sound's volume with it", abs(got.get("volume", 0) - 0.3) < 1e-6, got.get("volume"))

    # Paste only position + grade onto b.
    sc = bpy.context.scene
    b = sc.sequence_editor.strips_all[b.name]
    for s in clips.top_clips(sc):
        s.select = s == b
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.attributes_paste('EXEC_DEFAULT', **{n: n in ("position", "grade") for n in attrs.GROUPS})
    yield 0.3
    h.check("pasting the ticked ones: position", (b.transform.offset_x, b.transform.offset_y) == (120.0, -40.0),
            (b.transform.offset_x, b.transform.offset_y))
    h.check("...and grade", grade.is_graded(b) and abs(grade.values(b)["bright"] - 0.2) < 1e-6
            and abs(b.color_saturation - 0.4) < 1e-6, grade.values(b) if grade.is_graded(b) else None)
    h.check("...nothing else (size, flips, fades untouched)",
            abs(b.transform.scale_x - b_scale) < 1e-6 and not b.use_flip_x and b.plastron.fade_in == 0,
            (b.transform.scale_x, b.use_flip_x, b.plastron.fade_in))
    h.check("...and the ticks are remembered", attrs.ticked()["position"] and not attrs.ticked()["size"],
            attrs.ticked())

    # Everything, onto the video and its sound selected together.
    b_sound = clips.linked(b)[0]
    for s in clips.top_clips(sc):
        s.select = s in (b, b_sound)
    attrs.paste(sc, [b, b_sound], attrs._clipboard, list(attrs.GROUPS))
    yield 0.3
    h.check("all of them: size, rotation, crop, flip, opacity, fades",
            abs(b.transform.scale_x - 0.6) < 1e-6 and abs(b.transform.rotation - 0.3) < 1e-6
            and b.crop.min_x == 10 and b.use_flip_x and abs(b.plastron.opacity - 0.5) < 1e-6
            and b.plastron.fade_in == 6,
            (b.transform.scale_x, b.transform.rotation, b.crop.min_x, b.use_flip_x, b.plastron.opacity,
             b.plastron.fade_in))
    h.check("...the sound takes the volume (the video doesn't have one)",
            abs(b_sound.plastron.volume - 0.3) < 1e-6, b_sound.plastron.volume)
    h.check("...and its fades too", b_sound.plastron.fade_in == 6, b_sound.plastron.fade_in)

    # A panel never takes position / size (its painting is fitted to the frame).
    panel = next(s for s in clips.top_clips(sc) if panels.is_panel(s))
    before = (panel.transform.offset_x, panel.transform.scale_x)
    n = attrs.paste(sc, [panel], attrs._clipboard, ["position", "size", "fades"])
    h.check("a panel keeps its own place and size, takes the fades",
            (panel.transform.offset_x, panel.transform.scale_x) == before and panel.plastron.fade_in == 6 and n == 1,
            ((panel.transform.offset_x, panel.transform.scale_x), before, panel.plastron.fade_in))

    # Ctrl+V opens the box (a dialog): with nothing selected it says so instead.
    for s in clips.top_clips(sc):
        s.select = False
    h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
    yield 0.2
    h.key('V', ctrl=True)
    yield 0.3
    h.check("Ctrl+V with nothing selected: nothing happens (asks to select)", True)
    sc = bpy.context.scene
    sc.sequence_editor.strips_all[b.name].select = True
    h.key('V', ctrl=True)
    yield 0.5
    h.redraw()
    yield 0.2
    h.screenshot("paste_attributes")
    h.key('ESC')
    yield 0.2

    # A picture copied on the computer (a screenshot): Ctrl+V over the
    # timeline puts it at the playhead (stand-in for the clipboard: X11
    # Blender can't read clipboard pictures).
    import numpy as np
    ip = h.module("features.canvas_edit.image_paste")
    pic = np.zeros((90, 160, 4), np.float32)
    pic[..., 0], pic[..., 3] = 1.0, 1.0                  # (red)
    real_read, real_seq = ip.read_system, ip.sequence
    ip.read_system = lambda window=None: pic
    try:
        ip.sequence = lambda: 7                          # (copied in Plastron at clipboard change 7...)
        with h.override('SEQUENCE_EDITOR'):
            bpy.ops.plastron.attributes_copy()
        sc = bpy.context.scene
        before = {s.name for s in clips.top_clips(sc)}
        h.move(reg.x + reg.width // 2, reg.y + reg.height // 2)
        yield 0.2
        h.key('V', ctrl=True)                            # (...nothing newer: the attributes box)
        yield 0.4
        h.key('ESC')
        yield 0.3
        sc = bpy.context.scene
        h.check("a picture copied BEFORE Plastron's Ctrl+C doesn't paste (the attributes box opens)",
                {s.name for s in clips.top_clips(sc)} == before)
        with h.override('SEQUENCE_EDITOR'):
            bpy.ops.ed.undo_push(message="before the picture")   # (clips above made from Python: no undo step)
        ip.sequence = lambda: 8                          # (then a screenshot was copied)
        sc.frame_current = 900
        h.key('V', ctrl=True)
        yield 0.5
        sc = bpy.context.scene
        new = [s for s in clips.top_clips(sc) if s.name not in before]
        h.check("Ctrl+V with a newer picture on the computer's clipboard puts it on the timeline at the playhead",
                len(new) == 1 and new[0].type == 'IMAGE' and clips.start(new[0]) == 900,
                [(s.name, s.type, clips.start(s)) for s in new])
        if new:
            path = bpy.path.abspath(os.path.join(new[0].directory, new[0].elements[0].filename))
            h.check("...saved as a PNG that stays (Plastron's settings folder while untitled)",
                    os.path.exists(path) and path.endswith(".png") and "plastron_pasted" in path, path)
            h.check("...on a video track, selected", new[0].select and h.module("timeline.tracks")
                    .track_of_channel(sc, new[0].channel).kind == 'VIDEO')
        h.key('Z', ctrl=True)
        yield 0.4
        sc = bpy.context.scene
        h.check("...one Ctrl+Z takes it away", {s.name for s in clips.top_clips(sc)} == before,
                [s.name for s in clips.top_clips(sc) if s.name not in before])
    finally:
        ip.read_system, ip.sequence = real_read, real_seq


h.run(steps())
