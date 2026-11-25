"""Titles (features/edit/titles.py): T / Text adds a title at the playhead on
the Titles track and types in it in the preview; Plastron's preview keys
stand aside while typing; Esc / Tab finish; styles, the move / size box,
copy / paste of the text style."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import harness as h  # noqa: E402

titles = h.module("features.edit.titles")
views = h.module("core.views")
clips = h.module("timeline.clips")
tracks = h.module("timeline.tracks")
attrs = h.module("features.edit.attributes")


def preview():
    for area in h.window().screen.areas:
        if area.type == 'SEQUENCE_EDITOR' and views.is_preview(area.spaces.active):
            return area, next(r for r in area.regions if r.type == 'PREVIEW')
    return None, None


def is_typing():
    area, region = preview()
    with bpy.context.temp_override(window=h.window(), area=area, region=region):
        return views.typing(bpy.context)


def title_now():
    sc = bpy.context.scene
    return next((s for s in clips.top_clips(sc) if titles.is_title(s)), None)


def steps():
    yield 1.0
    wm = bpy.context.window_manager
    wm.plastron_mode = 'Edit'
    yield 1.0
    sc = bpy.context.scene
    sc.frame_current = 30
    area, region = preview()
    h.check("(Edit mode has a video preview)", area is not None)
    h.check("nothing is being typed at first (a title not selected)", not is_typing())
    h.move(region.x + region.width // 2, region.y + region.height // 2)
    yield 0.2
    h.key('T')
    yield 0.5
    sc = bpy.context.scene
    t = title_now()
    h.check("T over the preview adds a title at the playhead", t is not None and clips.start(t) == 30,
            [(s.name, s.type) for s in clips.top_clips(sc)])
    track = tracks.track_of_channel(sc, t.channel) if t else None
    h.check("...on a Titles track (a video track, above the others)",
            track is not None and tracks.name(sc, track) == "Titles" and track.kind == 'VIDEO'
            and t.channel == max(tracks.channel_of(sc, x) for x in tracks.video_tracks(sc)))
    h.check("...typing straight away", is_typing())
    h.type_text("Hello")
    yield 0.3
    t = title_now()
    h.check("typing replaces the placeholder word", t.text == "Hello", t.text)
    h.key('RET')
    h.type_text("jkl")
    yield 0.3
    t = title_now()
    h.check("Enter = a new line; J / K / L are just letters while typing (no playing)",
            t.text == "Hello\njkl" and not bpy.context.screen.is_animation_playing, repr(t.text))
    h.key('ESC')
    yield 0.3
    h.check("Esc finishes typing", not is_typing())
    h.key('TAB')
    yield 0.3
    h.check("Tab on the selected title types in it again", is_typing())
    h.key('TAB')
    yield 0.3
    h.check("...and Tab finishes", not is_typing())
    h.key('L')
    yield 0.4
    h.check("not typing: L plays again", bpy.context.screen.is_animation_playing)
    h.key('K')
    yield 0.3

    # Styles.
    sc = bpy.context.scene
    t = title_now()
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.preset_apply(kind="titles", name="Lower Third")
    h.check("the Lower Third style: smaller, a box behind, bottom left",
            abs(t.font_size - 0.045 * sc.render.resolution_y) < 1 and t.use_box and t.anchor_x == 'LEFT'
            and t.location[0] < 0.1, (t.font_size, t.use_box, t.anchor_x, tuple(t.location)))

    # The box: drag inside moves, a corner sizes.
    with bpy.context.temp_override(window=h.window(), area=area, region=region):
        h.redraw()
        r = titles.rect(sc, t)
        x0, y0, x1, y1 = titles._region_rect(region, r)
    loc, size = tuple(t.location), t.font_size
    cx, cy = region.x + (x0 + x1) / 2, region.y + (y0 + y1) / 2
    events = h.module("timeline.events")
    refreshes = []
    counter = lambda scene, **_i: refreshes.append(1)       # noqa: E731
    events.listen("clips_changed", counter)
    yield 0.3
    refreshes.clear()
    h.move(cx, cy)                                          # (a slow drag: 12 moves, 0.15 s apart)
    yield 0.1
    h._event('LEFTMOUSE', 'PRESS')
    yield 0.1
    for i in range(1, 13):
        h.move(cx + 10 * i, cy + 5 * i)
        yield 0.15
    during = len(refreshes)
    h._event('LEFTMOUSE', 'RELEASE')
    yield 0.5
    events._listeners["clips_changed"].remove(counter)
    h.check("dragging a title doesn't refresh the whole timeline on every move (once at the end)",
            during <= 1 and len(refreshes) <= 2, (during, len(refreshes)))
    t = title_now()
    h.check("dragging inside a title's box moves it", t.location[0] > loc[0] + 0.01 and t.location[1] > loc[1] + 0.01,
            (loc, tuple(t.location)))
    with bpy.context.temp_override(window=h.window(), area=area, region=region):
        x0, y0, x1, y1 = titles._region_rect(region, titles.rect(sc, t))
    yield from h.drag((region.x + x1, region.y + y1), (region.x + x1 + 80, region.y + y1 + 40))
    yield 0.3
    t = title_now()
    h.check("dragging a corner makes the text bigger", t.font_size > size * 1.1, (size, t.font_size))
    h.screenshot("titles")

    # Copy / paste the text style onto another title.
    sc = bpy.context.scene
    sc.frame_current = clips.end(t) + 10
    other = titles.add(sc, text="Second")
    yield 0.2
    sc = bpy.context.scene
    t = next(s for s in clips.top_clips(sc) if titles.is_title(s) and s.text.startswith("Hello"))
    other = next(s for s in clips.top_clips(sc) if titles.is_title(s) and s.text == "Second")
    for s in clips.top_clips(sc):
        s.select = s == t
    sc.sequence_editor.active_strip = t
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.attributes_copy()
    for s in clips.top_clips(sc):
        s.select = s == other
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.attributes_paste('EXEC_DEFAULT', **{n: n == "title" for n in attrs.GROUPS})
    h.check("pasting Text Style gives another title the same look (its words stay)",
            other.text == "Second" and abs(other.font_size - t.font_size) < 0.5 and other.use_box
            and tuple(other.location) == tuple(t.location), (other.font_size, t.font_size, other.use_box))


    # A downloaded font is kept in Plastron's fonts folder and packed.
    import shutil
    src_dir = os.path.join(bpy.app.tempdir, "downloads")
    os.makedirs(src_dir, exist_ok=True)
    src = os.path.join(src_dir, "MyMono.woff2")
    shutil.copy(os.path.join(bpy.utils.system_resource('DATAFILES'), "fonts", "DejaVuSansMono.woff2"), src)
    sc = bpy.context.scene
    for s in clips.top_clips(sc):
        s.select = s == other
    sc.sequence_editor.active_strip = other
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.title_font('EXEC_DEFAULT', filepath=src)
    kept = os.path.join(titles.fonts_folder(), "MyMono.woff2")
    h.check("Load Font copies the font into Plastron's fonts folder",
            os.path.exists(kept) and ("MyMono", kept) in titles.your_fonts(), titles.your_fonts())
    h.check("...the title uses it, packed into the project (so it survives the download going)",
            other.font is not None and other.font.packed_file is not None
            and os.path.basename(other.font.filepath) == "MyMono.woff2", other.font and other.font.filepath)
    os.remove(src)
    for s in clips.top_clips(sc):
        s.select = s == t
    with h.override('SEQUENCE_EDITOR'):
        bpy.ops.plastron.title_font_pick(filepath=kept)
    h.check("Your Fonts: one click gives another title the same font", t.font == other.font)


h.run(steps())
