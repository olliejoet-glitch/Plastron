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
- **Stage 6 done** (camera and motion): camera start / end per panel (pan,
  zoom, slight rotation) set with the camera controls box (canvas corner), Camera
  View (the canvas looks through the camera), easing dot graph
  (`widgets/dot_graph`), camera shake, layer / group start / end motion
  (box, live in playback), motion presets, Clean View (F)
  (`features/motion`). Then: a 3D multiplane view under the script (track
  cards moved in depth, 3D camera keyed as it moves) (`features/scene3d`).
- **Stage 7 done** (planning, review, export): shot status (clip colour),
  notes, versions (keep / flip / compare), framing guides, speed playback
  (pitch kept), temp sounds bin, board view (drag to reorder), exports
  (animatic MP4, panel sheet PDF, shot list CSV) (`features/review`,
  `features/export`). Not yet: the animatic shows each panel's start state
  (no camera moves / 3D camera); drag-and-drop import is Blender's own.
- **Next**: wait for Ollie to ask.
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
   - Exception: the 3D Camera's keyframes (Ollie asked for auto-keyed
     camera moves) are played by Blender's animation system.
   - Exception (Ollie: "I really need the layers to move with playback"):
     motion plays live. The motion frame hook moves the canvas view (camera)
     and writes a few shader values per MOVING layer (moved or at a depth); which layers move is
     cached per stretch of clips, so a still project costs nothing.
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
8. **UI should be tactile and on screen** (Ollie): transforms and shapes you
   drag on the canvas (boxes, handles), not little coordinate sliders or
   number fields. Number fields only where nothing on screen can do the job.

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
│  │  ├─ motion.py           camera zoom / rotation limits, drag handles, shake, layer refresh delay
│  │  ├─ scene3d.py          the 3D scene: its camera lens, the view's start angle, card colour
│  │  ├─ review.py           shot statuses, guides, speeds, temp sounds, board look, compare
│  │  ├─ export.py           animatic size / codec, panel sheet page + grid
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
│  │  ├─ views.py            which 3D view is the canvas / the 3D scene view
│  │  ├─ theme.py, preferences.py, modes.py, util.py
│  ├─ ui/                    topbar.py (File menu, undo/redo, mode switcher),
│  │                         drag_scroll.py (pen scrolling of tools area / script)
│  ├─ timeline/              the one shared timeline (see its __init__ for the module list)
│  │                         tracks (model over channels), clips (overlap-safe moves),
│  │                         ripple (pure planners), snapping, mix, track_headers,
│  │                         header, ops, view (framing), events (features listen;
│  │                         timeline knows no features)
│  ├─ layers/                Photoshop-style layer stacks on materials (from CaraPainter):
│  │                         props, blend_lib, layer_trees, compiler (node trees),
│  │                         flatten (same maths in numpy), stack (edits), paint_target
│  │                         (aims Texture Paint at the active layer), ops, ui (Layers panel)
│  ├─ widgets/               shared UI components: dot_graph (easing now; pitch /
│  │                         volume / speed later: Float Curve nodes in ".PLASTRON Graphs")
│  ├─ features/              one package per feature; list in features/__init__.py
│  │  └─ storyboard/         canvas_view (navigation), canvas_frame (overlay),
│  │                         tools (tool switching, tool strip), options_bar,
│  │                         canvas_color (Canvas panel: paper colour = world colour),
│  │                         panels (panel clips + layer-stack materials, New Panel),
│  │                         panel_cache (cached images, re-made after edits),
│  │                         canvas_sync (what the canvas shows at the playhead),
│  │                         brush_presets, brush_palette (import) + abr (.abr reader), onion,
│  │                         stabiliser (Off / Slight / Max), script_panels
│  │                         (panels from the script's lines + script bar),
│  │                         stroke_guard (is a brush stroke running?)
│  │  └─ voice/              recorder (mic), takes (voice clips + takes), record
│  │                         (Ctrl+R, switch takes), transcribe (+ _worker: own
│  │                         process), transcript_layout (pure) + transcript_bar,
│  │                         script_link (script <-> transcript)
│  │  └─ canvas_edit/        shapes (pure numpy: masks, homography, warp, resample),
│  │                         pixels (undoable layer writes, screen <-> canvas),
│  │                         selection (L / M, stencil), transform (Ctrl+T, V),
│  │                         clipboard (copy / paste, flips)
│  │  └─ motion/             camera (strip.plastron_motion, frame maths, shake),
│  │                         view_follow (Camera View), camera_pad (camera
│  │                         controls box), canvas_fit (painting grows to fit
│  │                         the camera), layer_motion (live positions,
│  │                         painted-layer UV shift), edit (layer box), thumbnails
│  │                         (panel_cache hook), ui (Motion panel, presets)
│  │  └─ scene3d/            the 3D (multiplane) view: track cards, keyed camera, pen-follows modes
│  │  └─ review/             notes (Panel panel: status, note), versions, guides,
│  │                         speed (2x etc. playback), sounds (temp sounds bin), board
│  │  └─ export/             animatic (MP4), sheet (hand-written PDF), shotlist (CSV)
│  ├─ presets/               ★ preset files, one folder per kind (brushes/, motion/); README
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
- Blender 5 video output: set `image_settings.media_type = 'VIDEO'` before
  `file_format = 'FFMPEG'` (the enum item isn't there otherwise).
- In camera view, test screenshots are stale until a mouse move + redraw +
  a short wait.
- `clips.apply` can't untangle a cyclic reorder (each clip wants another's
  place): park the clips past the end first (review/board.reorder).
- A new sound strip overlapping another is bumped: make it on a spare
  channel, trim it, then set its channel (review/sounds.drop).
- aud has no audio device under Xvfb: test audio by writing files.
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
- A modal operator started from a button in the tools area gets mouse
  coordinates relative to THAT region: find the canvas under
  event.mouse_x / mouse_y yourself (motion/edit.py `_canvas_under`), and
  handle Enter / Esc before passing events on.
- Texture Paint lands strokes at the mesh's UV: to paint a layer shown moved,
  shift the canvas mesh's UVs (the canvas has its own "Canvas Paint Sheet"
  mesh) and shift every layer's look back (stack.view_shift).
- `animation_playback_post` exists (fires once when playback stops).
- Setting `scene.frame_current` from Python runs frame_change handlers only
  on the next event loop: yield before checking their effect in tests.
- Moving a canvas view without stale matrices: canvas_view.screen_to_world
  works from view_location / view_rotation / distance directly.
- In a Properties editor, buttons take a click (even Alt+Shift+click) before
  the region's keymaps; "Screen Editing" keymap items run before buttons.
  Blender's text.scroll doesn't start from an Alt+Shift+LMB item.
- Simulated events can't make a double-click (Blender times real clicks):
  test double-click actions through the function they call.
- Blender's input_samples (the stabiliser's Steady) averages pen PRESSURE
  as well as position (paint_stroke_sample_average), so Slight / Max make
  pressure lag.
- An open pop-up (popover) swallows the next click anywhere: close it (Esc)
  before simulating clicks in tests.
- A 3D view always shows the window's scene (a second Blender scene can't
  sit in the same window's layout).
- core/handlers.add(..., first=True) puts a handler before the others (an
  edit must be read before another handler reacts to it).
- tests: h.area('VIEW_3D') is the canvas, h.area('SCENE_3D') the 3D scene view;
  h.flat_canvas() for tests of the flat canvas / 2D camera tools.
- Setting a view's view_perspective to 'CAMERA' makes that camera the
  scene camera too; leaving it, Blender settles the view after a redraw
  (fit later, from a timer).
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
- Layout (Ollie swapped them): tools 12 % | canvas 70 % | script over the
  3D scene over its keyframes 18 %, timeline 30 % high. No status bar (messages show in the top bar).
- Pen scrolling (Ollie couldn't scroll the tools area: a pen has no wheel):
  Alt+Shift+drag scrolls the tools area and the script 1:1 with the hand
  (ui/drag_scroll.py, using view2d.pan with exact pixels: scroll_up / down
  always jump 40 px). It's in the "Screen Editing" keymap so it works even
  when the drag starts on a button; it passes on elsewhere, so the canvas /
  timeline pans still work.
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
  pressure toggles, Stabiliser Off / Slight / Max (Ollie: he only uses off,
  slight and very smooth). STABILISER in config/tools.py: Slight = average
  the last 6 pen positions (unified input samples, no dead zone); Max = 32 +
  Blender's lazy-mouse smoothing (radius 40, strength 0.9; Blender's radius
  can't go below 10 px). Global for every brush, remembered (user_settings),
  re-applied on tool / preset changes; brush presets don't set smoothing.
  The ▾ next to the switch (Ollie) opens a pop-up to tune Slight / Max
  (steady, trailing smoothing on/off, radius, strength); changes are stored
  in user_settings "stabiliser_values" on top of config's, Reset clears them.
- Tools: Pencil = "Paint Hard Pressure", Eraser = "Erase Hard", Fill, Blur,
  Smudge (Blender's essential texture brushes; config/tools.py). Each tool
  remembers the last brush used with it for the session (B brings back your
  last pencil brush). Photoshop's blur/smudge key R is the view rotate, so
  they're Shift+B / Shift+S. Alt+click picks the colour you see (merged).
- Paint resolution 3600×2025 (PAINT_RESOLUTION; Ollie found 2400×1350 a bit
  low res); the camera frame is the middle 2880×1620, the rest is bleed.
  Not 4K: a layer holds w×h×4 bytes in memory (~29 MB here, ~52 MB at 4K).
  Existing panels keep their size; pasting between panels of different
  sizes rescales. New panels start with one paint layer
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
  at every load). Viewport TAA is 1 sample, no reprojection (Ollie: strokes
  looked thin and faint while drawing, then filled in: EEVEE was blending in
  older frames and refining over 16 samples). Brush presets don't smooth by default (smoothing trails
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
- Camera moves (stage 6): the scene camera never moves (no keyframes, no
  drivers). Each panel strip has `plastron_motion`: start / end (x, y in %
  of the frame width, zoom 1 = normal frame / 2 = twice as close, rotation
  up to ±45°), an easing graph and shake (amount % of frame width, speed
  wobbles/s, a little tilt; deterministic per panel). The shot = the panel
  being drawn on. Zoom blends evenly in scale. The animatic export (stage 7)
  will crop per frame from the same maths (camera.state_at / corners / crop).
- Camera View (Ollie: the frame must not slide across the screen, it should
  look like moving a camera): on by default (options bar toggle,
  remembered). The canvas view looks through the camera: the frame stays
  still on screen and the drawing pans / zooms / turns behind it, while
  scrubbing, playing and setting a move. Only the UI view changes
  (view_follow keeps which camera state each view has taken on and moves it
  by the difference, so your own pan / zoom / rotate stay). Off = the stage
  view: the frame moves over the drawing.
- Camera controls (Ollie: no camera mode, "a little box on the side with a
  drag and zoom box"): a box in the canvas's bottom-left corner
  (motion/camera_pad.py, sizes / speeds CAMERA_PAD in config/motion.py),
  shown whenever a panel is on the canvas. Start | End picks which end
  you're setting and moves the playhead there (until picked: the end nearer
  the playhead, per panel). Pan pad: drag to move the camera (0.15 % of the
  frame per px; orange dot = this end, blue = the other end); Zoom strip:
  drag right = in (exponential); Turn strip: drag = rotate. Shift = fine.
  Double-click a part puts it back. One undo step per drag. Its LMB item
  lives in the "Image Paint" keymap (so it beats a brush stroke) and passes
  the click on outside the box. The Motion panel's camera Start / End do
  the same as the box's. The old drag-the-frame mode
  (motion_set target CAMERA) has no key any more.
- Setting a layer's move: Start / End in the Motion panel's Layer section
  open a box around the active layer's / group's drawing (+24 px) on the
  canvas; drag to move it; the path to the other end shows (other end in
  blue). Tab swaps Start / End. Enter / double-click / Done keep (one undo
  step), Esc / right-click / Cancel put both ends back. No position number
  fields in the panel (just easing, shake, presets, Reset).
- Layer motion: move_start / move_end in canvas pixels, eased by its own dot
  graph; a group's move carries its layers. Layers move live with playback
  and scrubbing. The layer being painted is shown moved too: the canvas
  mesh's UVs follow it (stack.view_shift, re-aimed 0.12 s after scrubbing
  stops, at clip edges and after edits) so strokes land where you see them,
  and selections / transforms / paste work in that layer's own pixels.
- Oversized canvas grows to fit (Ollie couldn't paint where the camera had
  panned past the painting's edge, invisible as the paper is the world
  colour): 0.6 s after a camera move stops changing, every frame position
  along it (ends, easing, overshoot, shake) is checked and the painting is
  padded around the middle (layers/stack.pad_canvas, one undo step; masks
  repeat their edge). Never shrinks; max 3 frame widths (CANVAS_FIT in
  config/motion.py). stack.frame_w / frame_h hold the frame's pixel size
  (0 = the standard 80 % share); canvas_sync.frame_px / sheet_size(stack)
  give it, each sheet object is scaled to its painting, and paste between
  panels lines up by the camera frame. Image-source fill layers would
  shift scale when a painting grows (rare; not handled).
- Panels from the script (Ollie): File > Import Script... (txt / md /
  fountain into the script panel) and File > Panels from Script. One panel
  per non-blank line, on the active video track after its last clip (the
  blank starter panel is replaced), each about as long as its line takes
  to read (0.4 s a word, 1.5-8 s: SCRIPT_PANELS in config/timeline.py).
  The panel remembers its line (plastron_panel.script_line / script_text);
  running it again only adds lines without a panel; Import starts the
  links afresh. Clicking a script line not recorded yet jumps to its panel.
  The script panel has a bar (replaces Blender's text header): Paste Script
  (Ollie: "just copy and paste a script in": the clipboard goes into the
  script, or after what's there, and the panels are made), Make Panels,
  Import (file).
- Crash guard (Ollie: Blender crashed painting while the camera had just
  moved): nothing swaps layer images or changes the canvas sheet during a
  brush stroke. storyboard/stroke_guard: a stroke starts at the camera box's
  pass-through press, ends at the painted-image depsgraph update (60 s
  timeout); canvas_fit and the layer_motion re-aim timers wait while busy.
  The camera box grows the painting right when its drag ends.
- Quick brush resize (Ollie): Ctrl+Alt+right-click and move the pen (the
  side button, in the air): Blender's radial control on the brush size,
  let go to set (release_confirm).
- 3D parallax (layer depths + a depth chart) was tried and taken out (Ollie:
  "that 3d move thing isn't working"). What stays: layer_trees.shown_affine
  (moves + an extra shift / scale, layer.para_now, always 1 now), shader
  input MoveS, stack.view_scale, and the canvas paint UVs following the
  painted layer's whole affine.
- 3D scene = multiplane (Ollie: "this 3d view [should] move around the
  frames I'm adding: add a frame on a new layer, drag it forwards or
  backwards in the viewport, then move the camera to add parallax", and the
  camera move auto-keyframed). The right column is script (55 %) over the
  3D scene view (45 %) (config/layout.py "scene3d", features/scene3d,
  config/scene3d.py). Blender's own 3D view (header menus, toolbar,
  transform + navigation gizmos, perspective, Material Preview with the
  paper world) looking at the canvas's own sheets: one card per video track
  (orange outline = the card being drawn on, grey = the others; outlines
  drawn because empty cards are see-through). Moving / turning / scaling a
  card there moves its TRACK: track.place_offset / place_rotation /
  place_scale (props added to PLASTRON_PG_track by scene3d), applied by
  canvas_sync (SHEET_PLACE hook; the Canvas sheet takes the active track's
  placement). Kept two ways: an edit handler (depsgraph_update_post
  "_on_edit", added FIRST) and canvas_sync itself (SHEET_ABSORB: a sheet not
  where canvas_sync last put it was moved by hand, so that's saved before
  re-placing; a pending timeline refresh can fire between the move and the
  depsgraph). "3D Camera" (the scene view's own camera; use_local_camera
  marks the scene view: core/views) starts square-on at the distance that
  frames the picture exactly (16 units * lens / 36 mm); moving it keys
  location / rotation / lens at the playhead under the hood (edits only;
  Blender then plays the animation: allowed, Ollie asked). The canvas's
  flat ortho camera is drawn tiny in 3D (hiding it, hide_viewport, broke the
  canvas's Ctrl+0 fit maths). The CANVAS LOOKS THROUGH THE 3D CAMERA (Ollie:
  "moving the camera needs to actually change what I see on the canvas"):
  canvas view = Blender's camera view (use_local_camera + space.camera = 3D
  Camera, view_perspective 'CAMERA'); "3D Camera" toggle in the options bar
  (on by default, user_settings "canvas_3d_camera"; off = the old flat
  canvas with its 2D camera box / Camera View, which are hidden while on).
  Painting projects from the view, so strokes land on the card under the
  pen; canvas_edit's pixels.canvas_point hits the canvas sheet with a ray
  (works flat, through the camera, and on moved cards). Through the camera:
  Ctrl+0 fits the camera frame to 90 % (measured: frame width on screen =
  zoom factor x the region's longer side, factor = ((sqrt2 + zoom/50)^2)/4),
  Ctrl+= / wheel scale that factor, Alt+Shift+drag pans (Blender), R hold
  rolls the camera itself for the moment (keying held off, put back on
  release), Ctrl+F / Ctrl+1 only on the flat canvas. The frame overlay /
  dimming use the 3D camera's frame. Switching the view into the camera
  makes Blender set scene.camera to it: put back to "Canvas Camera". The
  camera is keyed only when it actually moved (its pose vs the last seen),
  not on any update. Cards animate too (Ollie: "the frames need to be
  moveable and animateable"): moving a card keys its track's place_offset /
  place_rotation / place_scale at the playhead (scene action, group "Card:
  <track>"); a frame hook (_cards_frame, nothing if no card is keyed)
  re-places the sheets from the played values (canvas_sync.apply_places).
  Keyframe view (Ollie: "an editable keyframe view"): a Dope Sheet area under
  the 3D scene view (layout "keys": script 40 % / 3D 38 % / keys 22 %), its
  keymaps kept (Dopesheet, Dopesheet Generic, Animation Channels): select,
  drag, delete keys. Scene view: no toolbar (Ollie: "get rid of all the
  unnecessary stuff"); select something and move + rotate gizmos show
  (show_gizmo_object_translate / rotate). The scene view is told apart by
  having no options bar (core/views: tool header = canvas). Modes follow the pen (MouseMove item
  plastron.view_focus): Object mode over the scene view, Texture Paint with
  the Canvas active over the canvas (no undo steps). Canvas-only things skip
  the scene view: frame overlay, camera box, selection outline, Camera View
  following, fit, canvas tool keys (B, E...). Alt+drag orbits there (its
  item is in Blender's "Object Mode" keymap, WHERE "scene3d", so it never
  meets the canvas's Alt+click colour pick; calling one operator from
  another to choose leaked memory). Ctrl+Space maximises any area (again:
  back). Blender's brush shelf strip under it is folded away at load.
  Blender's toolbar panel is no longer hidden in 3D views.
- Selecting the 3D camera (Ollie: hard to select): a Camera button at the
  left of the scene view's header selects it (lit while selected); the
  camera is drawn 3x Blender's size (CAMERA_DISPLAY_SIZE); click / Shift+click
  select work in the scene view (view3d.select in its "Object Mode" items);
  the canvas's flat ortho camera (drawn at its full 16-unit frame there)
  can't be clicked (hide_select).
- Blend If isn't in the Layers panel any more (Ollie: superfluous); the
  engine still supports it (PLASTRON_PT_blend_if, not registered).
- Panel images (thumbnails) show the panel where it starts: camera start
  frame (rotation left out) and layers at their start.
- Motion presets (presets/motion/): Straight, Ease in, Ease out, Ease in-out,
  Overshoot (set the graph), Camera shake, No shake. Both Motion sub-panels
  have a presets menu (header icon); layers only list presets with a curve.
  "Save current as preset" works for both (shared folder).
- Every panel / layer has its own graph: split copies the camera graph and
  the layers' graphs (copy_material / duplicate copy graphs too). Both
  halves of a split panel keep the whole move.
- Clean View (F, or the options bar button): outside the frame is hidden in
  the area background colour instead of dimmed.
- Stage 7 (review): Panel panel (tools area) shows the panel being drawn
  on: name, status Sketch / Blocking / Animated / Final (sets the clip's
  colour tag; STATUS in config/review.py), a note, the script line, versions.
  Versions: New Version keeps the painting (stacked under the panel) and
  carries on with a copy; arrows flip which one the panel uses; Compare
  shows the version before, 40 % opaque, just in front of the canvas
  ("Canvas Compare" sheet). Guides (options bar pop-up, remembered): rule
  of thirds, YouTube safe areas (action 93 %, title 90 %), 9:16 (Shorts) frame. Speed playback
  (timeline header 1x / 1.5x / 2x): picture via fps_base, sound mixed down
  and time-stretched with pitch kept (audaspace), project audio muted while
  it plays. Temp sounds: a bin folder in Plastron's config
  (plastron_sounds/, subfolders = tags), Sounds pop-up in the timeline
  header, + drops at the playhead on a "Temp Sounds" track, pink, named
  "TEMP ...", Select Temp Sounds finds them. Board (timeline header): the
  board track's panels (active video track, else first with panels) as
  cards; drag to reorder (one after another from the first's start, lengths
  kept), click = playhead there, double-click = back to the timeline.
- Stage 7 (export, File menu): Export Animatic (MP4, H.264 + AAC, 1920×1080;
  panels re-flattened at that size from their start state, project render
  settings put back), Export Panel Sheet (PDF written by hand, A4 landscape,
  3×2 grid, number / name / status / length / note / script under each),
  Export Shot List (CSV). config/export.py.
- Value swatches (value groups sampled from an image) are **deferred** to the
  later "value group editor" feature. Don't build them in storyboard mode.
