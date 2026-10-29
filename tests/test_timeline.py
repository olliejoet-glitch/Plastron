"""Timeline: tracks, panels, ripple on/off, lock, delete, split, insert, add
tracks, audio mix, loop range, the canvas following the playhead, and
playback doing no work inside a panel."""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import harness as h  # noqa: E402

tracks = h.module("timeline.tracks")
clips = h.module("timeline.clips")
ripple = h.module("timeline.ripple")
panels = h.module("features.storyboard.panels")
panel_cache = h.module("features.storyboard.panel_cache")
canvas_sync = h.module("features.storyboard.canvas_sync")


def scene():
    return bpy.context.scene


def track(name):
    return next(t for t in tracks.all_tracks(scene()) if tracks.name(scene(), t) == name)


def ch(name):
    return tracks.channel_of(scene(), track(name))


def span(strip):
    return (clips.start(strip), clips.end(strip))


def sound_file():
    path = os.path.join(bpy.app.tempdir, "beep.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\0\0" * 24000 * 20)     # 20 s
    return path


def add_sound(name, channel, start, length):
    s = clips.editor(scene()).strips.new_sound(name, sound_file(), channel, start)
    s.right_handle = start + length
    return s


def add_panel(channel, start, length):
    return panels.create(scene(), channel, start, length)


def clear_clips():
    sed = clips.editor(scene())
    for s in list(sed.strips):
        sed.strips.remove(s)


def strokes(mat):
    """Painted pixels in a panel's layers."""
    total = 0
    for layer in mat.plastron_stack.layers:
        if layer.paint_image is not None:
            px = np.empty(len(layer.paint_image.pixels), np.float32)
            layer.paint_image.pixels.foreach_get(px)
            total += int((px[3::4] > 0.05).sum())
    return total


def shows(obj):
    return obj.material_slots[0].material


def cached_darkness(strip):
    """How much of a panel's cached image is dark (painted)."""
    img = bpy.data.images.load(panel_cache.strip_path(strip), check_existing=False)
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return float((px.reshape(-1, 4)[:, :3].mean(1) < 0.3).mean())


def steps():
    yield 1.0
    sc = scene()

    # --- New project ----------------------------------------------------------
    names = [tracks.name(sc, t) for t in reversed(tracks.all_tracks(sc))]
    h.check("default tracks, top to bottom", names == ["Panels", "Background", "Voice", "Music"], names)
    kinds = [t.kind for t in reversed(tracks.all_tracks(sc))]
    h.check("video tracks above audio tracks", kinds == ['VIDEO', 'VIDEO', 'AUDIO', 'AUDIO'], kinds)
    h.check("Panels and Voice ripple by default",
            track("Panels").ripple and track("Voice").ripple and not track("Background").ripple)
    h.check("Panels is the active track", tracks.active(sc).uid == track("Panels").uid)
    starters = panels.all_panels(sc)
    h.check("new project has one starter panel", len(starters) == 1, len(starters))
    p1 = starters[0]
    h.check("starter panel: Panels track, frame 1, 2 s", p1.channel == ch("Panels") and span(p1) == (1, 49), span(p1))
    mat1 = p1.plastron_panel.material
    h.check("panel has its own layer stack, one paint layer at the paint resolution",
            mat1 is not None and [l.name for l in mat1.plastron_stack.layers] == ["Sketch"]
            and tuple(mat1.plastron_stack.layers[0].paint_image.size) == (2400, 1350))
    h.check("panel's cached image exists", os.path.exists(panel_cache.strip_path(p1)), panel_cache.strip_path(p1))
    canvas = bpy.data.objects["Canvas"]
    h.check("canvas shows the starter panel", shows(canvas) == mat1)
    h.check("canvas is the active object, in paint mode",
            bpy.context.view_layer.objects.active == canvas and canvas.mode == 'TEXTURE_PAINT')
    ip = sc.tool_settings.image_paint
    h.check("painting goes to the panel's active layer",
            ip.mode == 'IMAGE' and ip.canvas == mat1.plastron_stack.layers[0].paint_image)

    # --- New panel at playhead -----------------------------------------------
    sc.frame_current = 49
    p2 = panels.new_at_playhead(sc)
    h.check("New Panel starts at the playhead", span(p2) == (49, 97), span(p2))
    h.check("...and the playhead stays on it", sc.frame_current == 49)
    yield
    mat2 = p2.plastron_panel.material
    h.check("canvas switches to the new panel", shows(canvas) == mat2)
    h.check("...and painting follows", ip.canvas == mat2.plastron_stack.layers[0].paint_image)
    h.check("project end follows the last clip", sc.frame_end == 96, sc.frame_end)

    # Draw on panel 2, then scrub to panel 1 and back.
    area = h.area('VIEW_3D')
    cx, cy = h.center(h.region(area))
    yield from h.drag((cx - 120, cy), (cx + 120, cy + 40))
    yield 0.3
    h.check("painting goes into the panel under the playhead",
            strokes(mat2) > 100 and strokes(mat1) == 0, (strokes(mat2), strokes(mat1)))
    yield 3.0                                   # the panel image is re-made after a pause
    h.check("the panel's cached image shows the painting", cached_darkness(p2) > 0.001,
            cached_darkness(p2))
    h.check("...other panels' images are untouched", cached_darkness(p1) == 0.0)
    sc.frame_current = 20
    yield
    h.check("scrubbing to panel 1 shows panel 1", shows(canvas) == mat1)
    sc.frame_current = 60
    yield
    h.check("scrubbing back shows panel 2's painting", shows(canvas) == mat2)

    # --- Ripple ON (Panels) ----------------------------------------------------
    p3 = add_panel(ch("Panels"), 97, 48)
    voice = add_sound("Voice", ch("Voice"), 97, 40)
    music = add_sound("Music", ch("Music"), 97, 40)
    bg = add_panel(ch("Background"), 97, 48)
    ripple.trim(sc, p1, 'RIGHT', 60)
    h.check("ripple: lengthening P1 pushes P2, P3 on", (span(p1), span(p2), span(p3)) == ((1, 60), (60, 108), (108, 156)),
            (span(p1), span(p2), span(p3)))
    h.check("ripple: other ripple tracks shift too (Voice)", span(voice) == (108, 148), span(voice))
    h.check("ripple: non-ripple tracks stay (Music, Background)", span(music) == (97, 137) and span(bg) == (97, 145))
    ripple.trim(sc, p1, 'RIGHT', 30)
    h.check("ripple: shortening pulls everything back", (span(p1), span(p2), span(p3), span(voice)) ==
            ((1, 30), (30, 78), (78, 126), (78, 118)), (span(p1), span(p2), span(p3), span(voice)))
    ripple.trim(sc, p2, 'LEFT', 40)
    h.check("ripple: trimming a start keeps its place and closes up", (span(p2), span(p3)) == ((30, 68), (68, 116)),
            (span(p2), span(p3)))
    h.check("clips never jump to another track", all(s.channel == ch("Panels") for s in (p1, p2, p3)))

    # --- Ripple OFF (Background) -------------------------------------------------
    b1 = add_panel(ch("Background"), 1, 48)
    ripple.trim(sc, b1, 'RIGHT', 200)
    h.check("no ripple: lengthening stops at the next clip", span(b1) == (1, 97), span(b1))
    ripple.trim(sc, b1, 'RIGHT', 30)
    h.check("no ripple: shortening leaves a gap", span(b1) == (1, 30) and span(bg) == (97, 145), (span(b1), span(bg)))
    ripple.trim(sc, bg, 'LEFT', 10)
    h.check("no ripple: start stops at the previous clip", span(bg) == (30, 145), span(bg))

    # --- Lock ------------------------------------------------------------------------
    clips.editor(sc).channels[ch("Voice")].lock = True
    before = span(voice)
    ripple.trim(sc, p1, 'RIGHT', 40)
    h.check("locked tracks don't shift in a ripple", span(voice) == before, span(voice))
    ripple.trim(sc, voice, 'RIGHT', 300)
    h.check("locked clips can't be trimmed", span(voice) == before)
    clips.editor(sc).channels[ch("Voice")].lock = False
    ripple.trim(sc, p1, 'RIGHT', 30)

    # --- Delete --------------------------------------------------------------------
    clips.apply(sc, {voice: (clips.start(p3), clips.start(p3) + 40)})   # Voice starts with P3
    voice_before, music_before = span(voice), span(music)
    p3_before = span(p3)
    gone = p2.plastron_panel.material
    ripple.delete(sc, [p2])
    h.check("ripple delete closes the gap", span(p3) == (30, 78), (p3_before, span(p3)))
    h.check("...on every ripple track", span(voice) == (voice_before[0] - 38, voice_before[1] - 38), span(voice))
    h.check("...but not on others", span(music) == music_before)
    h.check("deleted panel's painting is no longer used", gone.users == 0, gone.users)
    ripple.delete(sc, [b1])
    h.check("delete without ripple leaves a gap", span(bg) == (30, 145))

    # --- Split ---------------------------------------------------------------------
    sc.frame_current = 50
    img = p3.plastron_panel.material.plastron_stack.layers[0].paint_image
    dab = np.zeros((img.size[1], img.size[0], 4), np.float32)
    dab[100:200, 100:300] = 1.0
    img.pixels.foreach_set(dab.ravel())
    left_strokes = strokes(p3.plastron_panel.material)
    right = ripple.split(sc, [p3], 50)
    h.check("split cuts a clip in two", len(right) == 1 and span(p3) == (30, 50) and span(right[0]) == (50, 78),
            (span(p3), right and span(right[0])))
    r = right[0]
    rm = r.plastron_panel.material
    h.check("each half has its own painting (a copy)",
            rm is not None and rm != p3.plastron_panel.material and left_strokes > 0
            and strokes(rm) == left_strokes
            and rm.plastron_stack.layers[0].paint_image != img)
    h.check("...and its own cached image",
            panel_cache.strip_path(r) != panel_cache.strip_path(p3) and os.path.exists(panel_cache.strip_path(r)))

    # --- New Panel at a playhead inside a panel -------------------------------------
    clear_clips()
    tracks.set_active(sc, track("Panels"))
    a = add_panel(ch("Panels"), 1, 48)
    b = add_panel(ch("Panels"), 49, 48)
    sc.frame_current = 20
    n = panels.new_at_playhead(sc)
    h.check("ripple: inside a panel, it's cut at the playhead and the new one starts there",
            (span(a), span(n), span(b)) == ((1, 20), (20, 68), (68, 116)), (span(a), span(n), span(b)))
    sc.frame_current = 20
    n2 = panels.new_at_playhead(sc)
    h.check("ripple: at a panel's start, the new one goes in front and the rest move along",
            (span(n2), span(n), span(b)) == ((20, 68), (68, 116), (116, 164)), (span(n2), span(n), span(b)))

    clear_clips()
    tracks.set_active(sc, track("Background"))
    c = add_panel(ch("Background"), 1, 48)
    d = add_panel(ch("Background"), 49, 48)
    sc.frame_current = 10
    n = panels.new_at_playhead(sc)
    h.check("no ripple: cut at the playhead, the new panel fills the rest of the gap",
            (span(c), span(n), span(d)) == ((1, 10), (10, 49), (49, 97)), (span(c), span(n), span(d)))
    sc.frame_current = 49
    result = panels.new_at_playhead(sc)
    h.check("no ripple, a panel starts right at the playhead: explains instead of overlapping",
            isinstance(result, str), result)
    tracks.set_active(sc, track("Panels"))

    # --- Adding tracks keeps every clip on its track -----------------------------------------
    clear_clips()
    pp = add_panel(ch("Panels"), 1, 48)
    vv = add_sound("v", ch("Voice"), 1, 48)
    bpy.ops.plastron.track_add(kind='AUDIO')
    bpy.ops.plastron.track_add(kind='VIDEO')
    names = [tracks.name(sc, t) for t in reversed(tracks.all_tracks(sc))]
    h.check("new video track on top, new audio track on top of the audio tracks",
            names == ["Video 3", "Panels", "Background", "Audio 3", "Voice", "Music"], names)
    h.check("clips stay on their tracks", pp.channel == ch("Panels") and vv.channel == ch("Voice"))
    h.check("new track becomes active", tracks.name(sc, tracks.active(sc)) == "Video 3")

    # --- Audio mix -------------------------------------------------------------------
    mm = add_sound("m", ch("Music"), 1, 48)
    track("Voice").volume = 0.5
    vv.plastron.volume = 0.5
    h.check("clip volume x track volume", abs(vv.volume - 0.25) < 1e-6, vv.volume)
    track("Music").solo = True
    h.check("solo: other audio tracks go silent", vv.volume == 0.0 and abs(mm.volume - 1.0) < 1e-6,
            (vv.volume, mm.volume))
    track("Music").solo = False
    h.check("un-solo restores the mix", abs(vv.volume - 0.25) < 1e-6)

    # --- Loop range ------------------------------------------------------------------
    sc.frame_current = 10
    bpy.ops.plastron.loop_set(side='IN')
    sc.frame_current = 30
    bpy.ops.plastron.loop_set(side='OUT')
    h.check("I / O set the loop range", sc.use_preview_range and
            (sc.frame_preview_start, sc.frame_preview_end) == (10, 30),
            (sc.frame_preview_start, sc.frame_preview_end))
    sc.use_preview_range = False

    # --- Backgrounds show under panels ------------------------------------------------
    clear_clips()
    tracks.set_active(sc, track("Panels"))
    top = add_panel(ch("Panels"), 1, 48)
    under = add_panel(ch("Background"), 1, 96)
    sc.frame_current = 5
    canvas_sync.invalidate(sc)
    disp = bpy.data.objects[canvas_sync.DISPLAY_PREFIX + track("Background").uid]
    h.check("background track shows under the panel",
            shows(canvas) == top.plastron_panel.material and shows(disp) == under.plastron_panel.material
            and not disp.hide_viewport and disp.location.y > canvas.location.y)

    # --- Scrubbing onto a panel makes it drawable, whatever track was active -----------
    tracks.set_active(sc, track("Voice"))          # e.g. after clicking an audio track
    sc.frame_current = 60                          # past the background, over nothing...
    yield
    sc.frame_current = 10                          # ...then onto the panel
    yield
    h.check("scrubbing onto a panel puts it on the canvas even if another track was active",
            shows(canvas) == top.plastron_panel.material, shows(canvas).name)
    h.check("...without changing the active track (where new panels go)",
            tracks.active(sc).uid == track("Voice").uid)
    tracks.set_active(sc, track("Background"))     # chose the background on purpose
    sc.frame_current = 11
    yield
    h.check("an active track with a clip there keeps priority",
            shows(canvas) == under.plastron_panel.material)
    tracks.set_active(sc, track("Panels"))

    # --- Performance: playback inside one stretch does no work ---------------------------
    clear_clips()
    add_panel(ch("Panels"), 1, 400)
    sc.frame_end = 400
    sc.frame_current = 5
    canvas_sync.invalidate(sc)
    yield 0.6
    panel_cache.flush_now()   # the new panel's image (re-making it tags the timeline)
    # Let the setup edits' debounced updates settle (shaders compile slowly here).
    work = -1
    for _ in range(20):
        if canvas_sync._state["work"] == work:
            break
        work = canvas_sync._state["work"]
        yield 0.5
    frames_before = sc.frame_current
    h.move(cx, cy)
    h.key('SPACE')
    yield 0.3      # (starting playback is an edit: one debounced update may follow)
    work = canvas_sync._state["work"]
    yield 1.5
    h.key('SPACE')
    yield 0.3
    h.check("playback moved the playhead", sc.frame_current != frames_before)
    h.check("no canvas work during playback inside a panel", canvas_sync._state["work"] == work,
            canvas_sync._state["work"] - work)
    h.screenshot("timeline")


h.run(steps())
