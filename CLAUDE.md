# Plastron: project notes for Claude

Read this first in every session. Keep it up to date whenever structure,
conventions, or decisions change.

## What Plastron is

Plastron is a full audiovisual video editing app for one user (Ollie), built as
a **Blender application template** that runs from its own **portable Blender
5.2.3 LTS** install on **Windows 10**. It launches straight into its own layout,
theme, and keymap, with Photoshop-style drawing shortcuts.

- The agreed spec is `Plastron storyboard mode build brief.md` (repo root).
  Everything in it is agreed; don't re-litigate it.
- Storyboard mode is the first feature. It's a **mode** (a layout) of the one
  app, not a separate tool. Later modes (edit, audio, grading...) share the same
  project, timeline, and media.
- GPL-3.0, personal use.

## Status

- **Stage 1 done**: app template, Windows installer + self-updating launcher,
  storyboard layout, theme, top bar, keymap (Blender's stripped), canvas
  navigation, Photoshop tool keys, tool strip, test runner. Canvas colour
  setting added after Ollie's feedback.
- **Stage 2 done**: panels as clips (image clip + own drawing), New Panel,
  trim edges with snapping, tracks with headers (ripple / solo / volume +
  Blender's name / mute / lock), add tracks, per-track ripple, lock, split,
  delete, loop range, audio mix, canvas follows the playhead (backgrounds
  underneath), undo, autosave + crash recovery.
- **Stage 3 in progress** (drawing basics). Done: RASTER switch (below),
  tools B / E / G / Shift+B blur / Shift+S smudge, Alt+click colour pick,
  options bar (brush picker, colour, size, opacity, pressure, smoothing),
  layers / groups / fills / adjustments / masks / Blend If (`plastron/layers`),
  cached panel images re-made after edits (shown on the timeline clips),
  onion skin. Left: brush presets.
  Wait for Ollie to ask before starting a stage.
- **DONE: drawing switched from grease pencil to RASTER** (Ollie: wants to
  select/move pixels, lay down blobs of colour, erase precisely). Brush engine
  = **Blender's own Texture Paint** (fast, Ollie likes the feel, can add his own
  brushes). Panels hold a Photoshop-style layer stack instead of a GP drawing;
  timeline, tracks, ripple, panel clips, canvas-follows-playhead all stay.
  From Ollie's CaraPainter add-on (`reference/painterly_layers/`, GPL, his own)
  take ONLY: paint layers, fill layers (colour / image + scale, rotation,
  offset, tiling break), groups, layer blend modes (all 26, Photoshop
  formulas: compiler/blend_lib.py), opacity / visibility, per-layer
  hue / saturation / value / curve, and its approach of painting via Texture
  Paint single-image mode aimed at the active layer's image
  (ops/layers.py `sync_paint_target`). NOT its lights, masks, analysis,
  outline, bake, library, 3D decal transform. Plan proposed to Ollie (canvas =
  textured plane; one material per panel; numpy flatten into the panel's
  cached image; packed layer images). Paint resolution and masks / adjustment
  layers / Blend If. Ollie: 2400×1350 OK; bring masks, adjustment layers and
  Blend If in too (masks: 2D sources only — paint, image; noise maybe).
  Overrides the brief's "grease pencil v3".

## Ollie's standing preferences (always apply)

1. **Never make Blender re-evaluate every frame.** Cache, bake, and recalculate
   only on edits. Concretely:
   - No drivers. No per-frame `frame_change_*` / `depsgraph_update_*` work
     unless it's an O(1) "did anything relevant change?" check that returns early.
     All handlers go through `core/handlers.py`; a test fails if any per-frame
     handler appears (update that test deliberately if one is ever justified).
   - Panels show on the timeline as cached images, re-rendered only when edited.
   - Destructive edits (warp, perspective, flips) are applied to strokes on
     confirm, never as live modifiers.
   - Derived values (e.g. strip volume = clip × track volume) are written on
     edit, not computed live.
2. **Minimal manual testing.** Test everything possible by running Blender
   from scripts (see Testing). At the end of each stage, give Ollie a **short**
   list of only the things that need checking by eye.
3. **Easy to change.** Ollie regularly asks to move, remove, or change things.
   Layout, keymap, tools, theme, presets, and hidden UI live in
   `plastron/config/` (and later `plastron/presets/`), one obvious file each.
   Feature code never hard-codes a key, colour, or area size.
4. **Commit after each working step** with clear messages.
5. Where the brief doesn't specify a detail, pick the simplest option that fits
   and log it in "Decisions log" below so it can be changed later.
6. Ollie wants as little manual setup as humanly possible.
7. **Push finished, tested work to `main` without asking** (Ollie's standing
   instruction, so his launcher picks it up and he can test). Develop on the
   session branch, run the full test suite, then push the branch to `main`
   (fast-forward). Never push failing tests to `main`.

## Ollie's setup

- Windows 10, NVIDIA GPU, Wacom Intuos Pro.
- Uses Blender's "Emulate 3 button mouse" navigation: **Alt+Shift+drag = pan**,
  **Ctrl+Alt+drag = zoom**. Plastron binds these itself (emulation is off).
- Final renders are 4K; storyboard work runs at a lighter preview resolution.

## Install and updates (Windows)

- One-time: `irm https://raw.githubusercontent.com/olliejoet-glitch/Plastron/main/install/install.ps1 | iex`
- Everything lives in `C:\Plastron`: `blender\` (portable: has a `portable\`
  folder, so Ollie's normal Blender is untouched), `app\` (this repo at a
  commit), `launch.ps1`, `plastron.ico`.
- The desktop/Start-menu shortcut runs `launch.ps1` (hidden): it downloads the
  latest `main` from GitHub if changed, copies `plastron/` into
  `blender\portable\scripts\startup\bl_app_templates_user\plastron`, makes sure
  the Blender version in `install/blender_version.txt` is installed, then starts
  Blender with `--app-template plastron`. Offline: starts the installed copy.
- **Ollie gets new work only when it reaches `main`.** Bumping
  `install/blender_version.txt` makes every launcher download that Blender.
- The PowerShell scripts can't be run here (no PowerShell allowed); keep them
  ASCII-only (PowerShell 5.1) and review them carefully.

## Folder structure

```
Plastron/
├─ CLAUDE.md, README.md, LICENSE (GPL-3.0)
├─ Plastron storyboard mode build brief.md
├─ install/
│  ├─ install.ps1            one-time bootstrap (downloads launch.ps1, runs it with -Install)
│  ├─ launch.ps1             self-updating launcher (shortcut target)
│  └─ blender_version.txt    pinned Blender version
├─ plastron/                 THE app template
│  ├─ __init__.py            register: core → ui → timeline → features → keymaps (last)
│  ├─ startup.blend          GENERATED by tools/build_startup.py; never edit by hand
│  ├─ config/                ★ everything Ollie asks to tweak
│  │  ├─ keymap.py           every shortcut (+ which Blender keys survive: BLENDER_KEEP)
│  │  ├─ timeline.py         snapping, edge grab distance, new panel length, track header look
│  │  ├─ layout.py           each mode's areas, sizes, visible regions
│  │  ├─ tools.py            drawing tools, tool strip order
│  │  ├─ theme.py            palette + where each colour is used; canvas overlay colours
│  │  ├─ hidden_ui.py        Blender panels/shelves to hide, headers to replace
│  │  ├─ preferences.py      Blender preferences set at every start
│  │  └─ project_defaults.py resolution, fps, audio, canvas size (new projects)
│  ├─ core/                  shared systems, no feature logic
│  │  ├─ handlers.py         the only place app handlers are added (on_load etc.)
│  │  ├─ keymaps.py          builds keymap from config, strips Blender's
│  │  ├─ layout.py           builds mode workspaces (used by the build script)
│  │  ├─ project.py          scene.plastron data; new-project setup; ensure on load
│  │  ├─ autosave.py         autosave copies, crash marker + prompt, File > Recover
│  │  ├─ user_settings.py    in-app choices Ollie makes that must persist (JSON in
│  │  │                      portable config; Blender prefs aren't saved)
│  │  ├─ hidden_ui.py        hides panels (never-poll) and swaps header draws
│  │  ├─ theme.py, preferences.py, modes.py, util.py
│  ├─ ui/topbar.py           slim top bar: File menu, undo/redo, mode switcher
│  ├─ timeline/              the one shared timeline (see its __init__ for the module list)
│  │                         tracks (model over channels), clips (overlap-safe moves),
│  │                         ripple (pure planners), snapping, mix, track_headers,
│  │                         header, ops, view (framing), events (features listen;
│  │                         timeline knows no features)
│  ├─ layers/                Photoshop-style layer stacks on materials (from CaraPainter):
│  │                         props, blend_lib, layer_trees, compiler (node trees),
│  │                         flatten (same maths in numpy), stack (edits), paint_target
│  │                         (aims Texture Paint at the active layer), ops, ui (Layers panel)
│  ├─ widgets/               shared UI components (dot graph later)
│  ├─ features/              one package per feature; list in features/__init__.py
│  │  └─ storyboard/         canvas_view (navigation), canvas_frame (overlay),
│  │                         tools (tool switching, tool strip), options_bar,
│  │                         canvas_color (Canvas panel: paper colour = world colour),
│  │                         panels (panel clips + layer-stack materials, New Panel),
│  │                         panel_cache (cached images, re-made after edits),
│  │                         canvas_sync (what the canvas shows at the playhead)
│  ├─ presets/               shared presets store (from stage 3)
│  └─ assets/                icon_256.png, plastron.ico
├─ tools/
│  ├─ build_startup.py       python tools/build_startup.py → plastron/startup.blend
│  └─ blender_env.py         portable test Blender under Xvfb
└─ tests/
   ├─ run_tests.py           python tests/run_tests.py [name-filter]
   ├─ harness.py             in-Blender helpers: checks, simulated keys/drags, screenshots
   └─ test_*.py              one Blender session per file
```

## Coding conventions

- Target **Blender 5.2 API**. Sequencer strips are `bpy.types.Strip` (not
  `Sequence`). Painting is Texture Paint: object mode `'TEXTURE_PAINT'`,
  `context.mode` `'PAINT_TEXTURE'`, `image_paint.mode = 'IMAGE'` with
  `image_paint.canvas` = the image painted. Brushes are assets:
  `bpy.ops.brush.asset_activate(asset_library_type='ESSENTIALS',
  relative_asset_identifier="brushes/essentials_brushes-mesh_texture.blend/Brush/<name>")`.
- Naming: operators `plastron.<area>_<verb>` (e.g. `plastron.panel_new`),
  classes `PLASTRON_OT_*`, `PLASTRON_PT_*`, `PLASTRON_MT_*`, property groups
  `PLASTRON_PG_*`. Project data hangs off `scene.plastron`. Anything named
  `PLASTRON_*` is never hidden by hidden_ui.
- Every package exposes `register()` / `unregister()` and cleans up fully
  (handlers, keymaps, draw handlers, timers).
- New features: add a package under `features/`, add its name to
  `features/__init__.py`, put its shortcuts in `config/keymap.py`.
- Operators that change a view must call `context.area.tag_redraw()`.
- Keep modules small and single-purpose. Prefer plain data tables in `config/`.
- After changing `config/layout.py`, `config/project_defaults.py`,
  `core/layout.py` or `core/project.py`: run `python tools/build_startup.py`
  (a test fails until you do) and commit the new `startup.blend`.

## Testing

- `python tests/run_tests.py` runs every `tests/test_*.py` in a fresh portable
  Blender (hard-linked copy in `.cache/blender`, template symlinked in, config
  wiped) with the real UI under Xvfb and `--enable-event-simulate`. Any
  traceback/error in the console fails the test. Logs, JSON results and
  screenshots go to `tests/output/` (look at the screenshots: Read the PNG).
- Tests are generators: `yield` lets Blender process events and redraw.
  Simulate input with `h.key()`, `h.drag()`, `h.type_text()`; force a draw with
  `h.redraw()` before reading view matrices.

### Blender gotchas learned (don't relearn them)

- Strip timing: use `left_handle` / `right_handle` / `content_start` (move);
  `frame_start` / `frame_final_*` are deprecated (removed in Blender 6).
- Changing a strip so it overlaps another, even for a moment, makes Blender
  bump it to another channel: always reposition via `timeline.clips.apply()`.
- Channel names must be unique (renaming to a taken name gives ".001").
- `depsgraph_update_post` doesn't fire during playback; it fires on edits.
- The timeline's channel column has its own view that Blender doesn't keep
  in step; measure rows on the main region (track_headers.row_span).
- `view2d.reset` scrolls tracks out of view; frame with `anim.scene_range_frame`.
- Its width can't be set from Python: the startup builder drags the edge with
  simulated events (needs two hover moves first; retries a few offsets).
- Undo reloads data: re-fetch `bpy.context.scene` etc. after undo in tests.
- Swapping the canvas object's (object-linked) material while in Texture Paint
  is fine (canvas_sync relies on it); strokes go to `image_paint.canvas`.
- A finished stroke fires `depsgraph_update_post` once with the painted image
  in `depsgraph.updates` (panel_cache uses it to re-make the panel image).
- `Image.copy()` of a packed image reloads the packed file, losing unsaved
  paint: copy pixels too (layers/stack.py `_clone_image`). Painted packed
  images must be re-packed on save (layers `_save_pre`).
- Brush strokes need "Image Paint" `paint.image_paint` in BLENDER_KEEP.
- Anything reading the screen (Alt+click colour pick with merged, Blender's
  screenshot) gets black under Xvfb; test it loosely.
- Material Preview under Xvfb (llvmpipe) is slow to compile shaders, so
  debounced updates arrive late in tests; it has also crashed once on exit
  (Mesa, after all checks passed). Re-run before suspecting the code.
- Keymap clashes: Plastron keys fire on PRESS; Blender items on the same key
  with CLICK / CLICK_DRAG / DOUBLE_CLICK aren't clashes (keymaps.py).

- In `-b` (background) mode keymaps have **no items**: keymap tests need the UI.
- Blender imports the template as `bl_app_templates_user.plastron`
  (use `h.module("core.layout")` in tests).
- Add-ons (Cycles) register **after** the template, and Blender finishes its
  keymaps after too: panel hiding and keymap stripping run from a timer.
- Never unregister Blender's panels (add-ons `append` to them); hidden_ui
  re-registers them with a never-true `poll`. Same for asset shelves
  (`show_region_asset_shelf` is read-only).
- C-defined panels (e.g. the 3D view's Item/Transform) can't be hidden, so the
  canvas sidebar stays off. The tools area is a Properties editor on its "Tool"
  tab, which draws `VIEW_3D`/`UI` panels with `bl_category = "Tool"`.
- Area geometry updates only after a UI refresh; setting region flags on an
  area whose type just changed crashes Blender. The layout builder yields
  between steps.
- Loading a file cancels non-persistent timers (`persistent=True` if needed).
- Blender 5 timelines show `workspace.sequencer_scene`, not the window scene;
  `core/project.py` points it at the project scene on every load.
- View matrices (`region_data.perspective_matrix`) are stale until a redraw;
  canvas zoom maths uses Blender's ortho formula instead (canvas_view.py).
- `bpy.ops.screen.screenshot` is black under Xvfb; the harness uses
  ImageMagick `import -window root`.
- Blender 5.2 ships a "Storyboarding" app template with scene strips +
  `workspace.use_scene_time_sync` (Storypencil built in). Consider it for the
  stage 2-3 panel design, but panels must show as cached images on the timeline.

## Decisions log (unspecified details, changeable later)

- Blender pinned to **5.2.3 LTS** (`install/blender_version.txt`).
- Install root `C:\Plastron`; shortcuts on desktop and Start menu; Ollie's
  copy updates from `main` at every launch.
- Frame rate **24 fps** (YouTube keeps the upload's rate; 24 is the animation
  standard). Project resolution **3840×2160**, previews at **50 %**.
- Colour view transform **Standard** (AgX shifts greys).
- Layout: script 18 % | canvas 70 % | tools 12 %, timeline 30 % high.
  No status bar (messages show in the top bar).
- Top bar: Plastron icon, File (New, Open, Open Recent, Save, Save As, Recover,
  Quit), undo/redo, mode switcher. Project name on the right.
- Canvas colour: Ollie found white too bright. Default is soft paper
  `#d2cec6`; the Canvas panel (tools area) has swatches (CANVAS_PRESETS in
  config/theme.py) and a picker; the choice is remembered in
  `plastron_settings.json` (core/user_settings.py). It's the project's world
  colour (the canvas is in Material Preview with the scene world).
- Canvas: outside the camera frame dimmed (overlay, not render);
  orthographic front view, rotation locked; Blender's camera drawing hidden.
  Canvas is 16 units wide (`CANVAS_WIDTH`).
- Canvas options bar (replaces Blender's tool header): tool name, brush
  picker (Blender's texture brush shelf as a pop-up; the shelf strip under
  the canvas is hidden), colour, Size, Opacity (= brush strength) with pen
  pressure toggles, Smooth (stroke smoothing + radius).
- Tools: Pencil = "Paint Hard Pressure", Eraser = "Erase Hard", Fill, Blur,
  Smudge (Blender's essential texture brushes; config/tools.py). Each tool
  remembers the last brush used with it for the session (B brings back your
  last pencil brush). Photoshop's blur/smudge key R is the view rotate, so
  they're Shift+B / Shift+S. Alt+click picks the colour you see (merged).
- Paint resolution 2400×1350 (PAINT_RESOLUTION); the camera frame is the
  middle 1920×1080, the rest is bleed. New panels start with one paint layer
  "Sketch". Layer images are 8-bit, packed into the project.
- Panels: image clip (cached image, "<project>_cache/panel_<uid>.png",
  temp folder until first save) + its own layer-stack material
  (`strip.plastron_panel.material`). Split copies the painting. The cached
  image is the camera frame flattened (numpy, layers/flatten.py) over the
  paper colour at 960×540, re-made 0.4 s after the last stroke / layer edit
  / undo (and for every panel when the paper colour changes).
  Opaque for now; the animatic export may want alpha later.
- Onion skin: Onion Skin toggle at the right of the options bar; strength
  (default 25 %) in the Canvas panel; both remembered (user_settings). Shows
  the panels just before and after the one being drawn on (same track),
  faintly (object alpha), just behind it. No colour tint.
- Timeline thumbnails: Blender's "strip ends" thumbnails show each panel's
  cached image. They only appear on tall rows, so projects open with track
  rows ROW_HEIGHT_PX (64) high, bottom track at the bottom
  (timeline/view.py).
- Stage-2 (grease pencil) projects: panels get an empty painting on load;
  their old drawings aren't converted.
- Canvas: one "Canvas" sheet (a flat mesh, camera frame + bleed, always
  active, in Texture Paint) is handed the active panel's material; other
  video tracks get display-only sheets (same mesh, object-linked materials),
  higher tracks nearer the camera. You draw on the active track's clip under the
  playhead; if it has none there, on the topmost visible, unlocked video
  track's clip (Ollie: scrubbing onto a panel must be enough to draw on it).
  That fallback doesn't change the active track (= where new panels go;
  last clicked track row / header).
- New projects: tracks Panels (ripple), Background, Voice (ripple), Music;
  one 2 s starter panel (so drawing works straight away; the project then
  shows as unsaved "*"). New Panel (Ollie: "at the playhead") = 2 s starting
  exactly at the playhead; a panel the playhead is inside is cut short there
  (keeps its drawing); one starting exactly at the playhead stays whole and the
  new panel goes in front. Ripple tracks move later clips just enough; others
  shrink the new panel to the gap (none: explain, don't overlap).
- Ripple: right-edge drag / delete / insert shift later clips on all ripple
  tracks (locked tracks never move). Left-edge drag with ripple ON is
  Premiere's ripple trim: the clip keeps its place, its length changes, later
  clips close up / make room. Without ripple: edges stop at neighbours, gaps
  stay.
- Track headers: name / mute / lock are Blender's channel buttons; Plastron
  draws R (ripple, all tracks), S (solo) and a volume bar (0-200 %, audio
  tracks only). Clicking a track's row or name makes it the active track.
- Audio mix: strip volume = clip volume × track volume × (0 if another track
  is soloed); written on edit. Clip volume shows in the timeline header when a
  sound clip is selected.
- Split (Ctrl+K): selected clips under the playhead, else the active track's.
  Delete: selected clips. Loop: I / O set Blender's preview range; header
  "Loop" toggles it.
- Snapping (on by default, header toggle; hold Ctrl while dragging an edge to
  not snap): playhead, clip edges, markers (beats later).
- The timeline opens framed on the whole project. Blender's "adjust last
  operation" pop-up is hidden. Clip labels show names only.
- Autosave every 2 min (not while playing or mid-drag), last 5 kept, in
  "<project>_autosave/" (untitled: Plastron's settings folder). A marker file
  detects a crash and offers the newest autosave at the next start. Recovering
  into a saved project keeps the old file as "<project>_before_recover.blend".
- Keys: Space = play/pause (types a space in the script panel). Pan =
  Alt+Shift+drag (also middle-mouse drag), zoom = Ctrl+Alt+drag (also wheel,
  Ctrl+= / Ctrl+-). Ctrl+0 fit (frame fills 90 %), Ctrl+1 100 % (preview
  pixels). R hold + move = rotate view, snaps back on release. Ctrl+F flip
  view. **G = Fill** (Photoshop's bucket key). Q/W scale brush ×0.8 / ×1.25.
  L / M / V / Ctrl+T / Ctrl+C / Ctrl+V / Ctrl+Alt+F are reserved for stage 5's
  pixel selection and transform.
  Same pan/zoom drags work on the timeline.
- Timeline keys (stage 2): N new panel, Ctrl+K split, Delete/Backspace delete,
  I / O loop range.
- Blender keymap stripped to essentials (BLENDER_KEEP in config/keymap.py):
  area resizing, UI widgets, scrolling, ruler scrubbing, typing in the script,
  painting strokes, tool click/drag behaviour, strip select/move. No right-click
  menus, no F3 search.
- Timeline: Plastron header (transport + frame), Blender footer hidden, ruler
  shows timecode, Blender's channel headers until stage 2's track headers.
- Blender preferences aren't saved; `config/preferences.py` is applied at each
  start (no splash, opening projects keeps Plastron's layout, 64 undo steps).
- Theme: dark teal, orange (selection/active) and blue (playhead/secondary),
  sampled from Ollie's Blender theme.
- Value swatches (value groups sampled from an image) are **deferred** to the
  later "value group editor" feature. Don't build them in storyboard mode.
