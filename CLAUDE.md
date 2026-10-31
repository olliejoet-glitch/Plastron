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
- **Stage 3 done** (drawing basics): RASTER switch (below),
  tools B / E / G / Shift+B blur / Shift+S smudge, Alt+click colour pick,
  options bar (brush picker, colour, size, opacity, pressure, smoothing),
  layers / groups / fills / adjustments / masks / Blend If (`plastron/layers`),
  cached panel images re-made after edits (shown on the timeline clips),
  onion skin, brush presets (shared presets store).
- **Stage 4 done** (voiceover and transcript): record at playhead with
  retakes (Ctrl+R), local transcription (faster-whisper, own process),
  transcript bars, hover / click / select / cut by words, script linking.
  Real microphone + real Whisper can't run here (no mic; Hugging Face
  blocked): tests use stand-ins (PLASTRON_FAKE_MIC / _TRANSCRIBE).
- **Stage 5 done** (transform and selection, on pixels): L lasso / M rectangle
  selection, V move, Ctrl+T transform (scale, rotate, distort, warp),
  Ctrl+C / X / V between panels, Ctrl+Alt+F flips (`features/canvas_edit`).
- **Next: stage 6** (camera and motion). Wait for Ollie to ask.
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
│  │  ├─ tools.py            drawing tools, tool strip order, brush palette / library
│  │  ├─ voice.py            recording, transcription model + prompt, transcript bar look
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
│  │  ├─ presets.py          shared presets store: kinds, built-in + saved JSON, menu
│  │  ├─ deps.py             extra pip packages, installed once in the background
│  │  ├─ windows_taskbar.py  Windows: Plastron's own taskbar group, icon, relaunch (ctypes)
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
│  │                         canvas_sync (what the canvas shows at the playhead),
│  │                         brush_presets, brush_palette (import) + abr (.abr reader), onion
│  │  └─ voice/              recorder (mic), takes (voice clips + takes), record
│  │                         (Ctrl+R, switch takes), transcribe (+ _worker: own
│  │                         process), transcript_layout (pure) + transcript_bar,
│  │                         script_link (script <-> transcript)
│  │  └─ canvas_edit/        shapes (pure numpy: masks, homography, warp, resample),
│  │                         pixels (undoable layer writes, screen <-> canvas),
│  │                         selection (L / M, stencil), transform (Ctrl+T, V),
│  │                         clipboard (copy / paste, flips)
│  ├─ presets/               ★ preset files, one folder per kind (brushes/ now); README
│  │                         lists the fields. Store code: core/presets.py
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
- Python workspace tools for the timeline: `bl_space_type='SEQUENCE_EDITOR'`,
  `bl_context_mode='SEQUENCER'`; their keymap is named "Sequence Editor Tool:
  Sequencer, <label>" (must be in BLENDER_KEEP).
- New asset-library files aren't seen until `asset.library_refresh` runs
  with the 3D view's ASSET_SHELF region as context (works while hidden).
  Call `wm.call_asset_shelf_popover` straight from the keymap: called from
  another operator, the pop-up never shows.
- Making a panel image (numpy flatten + PNG) costs 0.3-0.8 s at 960×540:
  never do heavy work right after a stroke.
- `clips._set` must MOVE content for a pure shift (content_start += d):
  moving handles instead trims, which slides a sound clip's audio.
- Strip.split copies Plastron's PointerProperties (voice takes, panel data).
- A Plastron action that passes clicks on (PASSES_ON in config/keymap.py)
  doesn't count as a clash, so Blender's own item on that key stays on
  (e.g. the script click still places the text cursor).
- Timer callbacks have no window in context: wrap ops in a temp_override
  with a window (voice/record.py `_window_override`).
- Blender's "Sequencer Tool: Select Box" press-select grabs clip edges itself
  (~14 px inside a clip) before Plastron's edge drag: it's switched off
  (BLENDER_DROP) and clip_trim runs Blender's select itself when the click
  isn't on an edge (EXEC at the mouse, then PASS_THROUGH so a drag moves).
- Of two Plastron items on one key in one keymap, Blender tries the one
  added LATER first (SHORTCUTS order reversed).
- Stripping keymaps must keep "File Browser*" or Open / Save / Import
  dialogs can't be clicked.
- faster-whisper's own audio loader passes `metadata_errors` to PyAV's
  `av.open`, which PyAV 19 removed (TypeError). The worker reads our WAVs
  itself (numpy, resampled to 16 kHz) and hands Whisper an array, which
  skips that loader.
- Blender can't undo pixels written from Python, but it undoes which image
  a layer points at: every pixel edit puts its result in a NEW image
  (canvas_edit/pixels.replace_image, CaraPainter's trick).
- Blender never undoes tool settings (the paint stencil lives there): the
  selection is kept in scene.plastron_selection and copied to the stencil
  after every undo / redo / load.
- Operators called from Python don't push undo steps (only from the UI /
  keymap): test undo with real key presses.
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
  paper colour at 480×270, re-made 2.5 s after the last stroke / layer edit
  / undo (and for every panel when the paper colour changes).
  Opaque for now; the animatic export may want alpha later.
- Brush presets: Pencil, Ink, Marker, Soft shading (plastron/presets/brushes/
  *.json: base texture brush + size, opacity, pressure, smoothing, spacing).
  Presets menu in the options bar; "Save current as preset..." writes to
  the config folder (plastron_presets/brushes/), deletable there. A preset
  sets the shared base brush's settings (Pencil and Ink share
  "Paint Hard Pressure").
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
- Snapping (Ollie: off by default; hold Ctrl while dragging an edge or
  slicing to snap; the header magnet turns it on, then Ctrl stops it):
  playhead, clip edges, markers (beats later). Projects saved before keep
  their magnet setting. Blender's own clip move has the same Ctrl behaviour.
- Held keys repeat (Ollie): Q / W, Ctrl+Z / Ctrl+Shift+Z, Ctrl+= / Ctrl+-
  (REPEAT in config/keymap.py).
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
  Stage 5 (pixels): L lasso, M rectangle (drag; Shift adds, Alt takes away;
  the tool stays on, navigation works, another tool key or Esc ends it),
  Ctrl+D deselect, Ctrl+A all, Ctrl+Shift+I invert, Delete erases the
  selection on the active layer. V moves the selection (or the whole layer).
  Ctrl+T: drag inside = move, corner = scale (Shift: proportional), edge
  middle = stretch, outside = rotate (Shift: 15°), Ctrl+corner = distort /
  perspective, W = warp (4x4 points; the surface passes through them),
  Enter / double-click / Ctrl+T applies, Esc / right-click cancels. The
  selection moves with transformed pixels. Ctrl+C / Ctrl+X copy / cut the
  selection (or layer); Ctrl+V pastes in place as a new "Pasted" layer on
  the panel being drawn on (and selects it). Ctrl+Alt+F flips the selection
  left-right in place, or the active layer / every paint layer of the active
  group; Ctrl+Alt+Shift+F upside down. Outside the selection is tinted
  (SELECTION_COLOR) with a white edge.
  Same pan/zoom drags work on the timeline.
- Timeline keys (stage 2): N new panel, Ctrl+K split, Delete/Backspace delete,
  I / O loop range.
- Edge drags grab EDGE_GRAB_PX (8) outside a clip and EDGE_GRAB_INSIDE_PX
  (16, at most a third of the clip) inside it; further in, a click selects
  and a drag moves (Blender). Transcript word clicks win except within 8 px
  of a clip edge.
- Active track (Ollie wanted clearer feedback): its header row is tinted
  orange and its timeline row has a faint orange tint with orange edges
  (ACTIVE_* in config/timeline.py).
- Timeline tools (Ollie): S = Slice tool (knife cursor; click a clip to cut it
  there, snapping like edge drags, Ctrl = no snap, Shift+click = every track),
  A = back to Move (move clips, drag edges). Header shows Move | Slice. Both
  keys work over the timeline and the canvas. Slice is a Blender workspace
  tool (timeline/edit_tools.py); clip_trim stands aside while it's on.
  Blender's timeline resets the cursor itself, so in Slice mode a MOUSEMOVE
  tool-keymap item sets the knife cursor and an orange line shows where the
  cut would go (only the clip under the mouse; Shift: full height).
- Brush palette (Ollie): right-click on the canvas opens Blender's texture
  brush shelf as a pop-up (all libraries). The import button next to the
  brush picker in the options bar takes Photoshop .abr (sampled tips, v1/2/6+),
  images (a tip: light = paint, or the alpha if transparent) and Blender .blend
  brushes. Each file becomes "<config>/plastron_brushes/<name>.blend"
  (asset library "Plastron Brushes", added at every start), brushes marked
  as assets; nothing is kept in the project. Tip brushes use a mask texture
  in View Plane mapping, constant falloff, 25 % spacing, pressure size.
- Painting speed (Ollie: "SO laggy"): panel images are re-made only after
  2.5 s without painting, at 480×270 (making one took 0.3-0.8 s at 960×540,
  which froze the start of the next stroke). Texture Paint occlusion,
  backface culling, normal falloff and seam bleed are off and EEVEE
  shadows / ray tracing / fast GI are off (canvas_sync.FAST_SETTINGS, applied
  at every load). Brush presets don't smooth by default (smoothing trails
  behind the pen).
- Windows taskbar (Ollie: Blender icon, grouped with his other Blender):
  each Plastron window gets AppUserModelID "Plastron.App", the Plastron icon
  and a relaunch command (launch.ps1), so it has its own taskbar button and
  pinning it pins the launcher. Untestable here (Linux).
- Voice recording (stage 4): Ctrl+R records onto the active audio track
  (else the top one) from the playhead while the timeline plays; Ctrl+R or
  Space stops. Over an existing voice clip it records a new take of it from
  the clip's start (old take muted while recording); the header shows
  Take n/m arrows for the selected clip; switching takes changes the clip's
  length following ripple. A new clip makes room like New Panel. Takes are
  packed into the project (no audio folder to lose). 48 kHz mono.
- Packages (sounddevice, faster-whisper) install themselves into Blender's
  config folder (plastron_python/) in the background at the first start;
  the Whisper model ("small.en", config/voice.py) downloads at the first
  transcription into plastron_models/. CPU int8. A prompt full of "um"s
  keeps fluffs in the transcript. The header shows what the worker is doing
  (getting the model, %) and how long; its output goes to
  "<config>/plastron_transcribe.log". Jobs over 30 min are stopped.
  Failures: header message + Transcribe Again on the clip. Blender's Python
  is found from sys.executable or next to Blender (deps.python()).
- Transcript bars (Blender can't add a row under a track): the bottom half
  of each audio track's row (BAR_FRACTION); words wrap in as many lines as
  fit (taller rows = more lines, Ctrl+Alt+drag), the last line ending "…";
  the header's "…" button collapses a track's bar to one line. Zoomed in
  far enough, words sit at their exact times. Trimmed words show greyed and
  struck through (wrapped view only). Layout is cached and redone only when
  the view or the clips / transcripts change.
- Cut by words: click a word (playhead jumps there), Shift+click to extend,
  Delete / Backspace cuts from midway after the previous word to midway
  before the next (follows ripple). Clicking elsewhere clears the selection.
- Script linking: words matched with difflib (fluffs skipped). Clicking a
  script line jumps to its first heard word; unheard script words are
  underlined orange.
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
