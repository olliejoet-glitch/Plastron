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

## Ollie's standing preferences (always apply)

1. **Never make Blender re-evaluate every frame.** Cache, bake, and recalculate
   only on edits. Concretely:
   - No drivers. No per-frame `frame_change_*` / `depsgraph_update_*` work
     unless it's an O(1) "did anything relevant change?" check that returns early.
   - Panels show on the timeline as cached images, re-rendered only when edited.
   - Destructive edits (warp, perspective, flips) are applied to strokes on
     confirm, never as live modifiers.
   - Derived values (e.g. strip volume = clip × track volume) are written on
     edit, not computed live.
2. **Minimal manual testing.** Test everything possible by running Blender
   headless (or under Xvfb) from scripts. At the end of each stage, give Ollie a
   **short** list of only the things that need checking by eye.
3. **Easy to change.** Ollie regularly asks to move, remove, or change things.
   Layout, keymap, theme, presets, and hidden UI live in `plastron/config/` and
   `plastron/presets/`, one obvious file each. Feature code never hard-codes a
   key, colour, or area size.
4. **Commit after each working step** with clear messages.
5. Where the brief doesn't specify a detail, pick the simplest option that fits
   and log it in "Decisions log" below so it can be changed later.

## Ollie's setup

- Windows 10, NVIDIA GPU, Wacom Intuos Pro.
- Uses Blender's "Emulate 3 button mouse" navigation: **Alt+Shift+drag = pan**,
  **Ctrl+Alt+drag = zoom**. Plastron uses these, not Space+drag.
- Final renders are 4K; storyboard work runs at a lighter preview resolution.

## Folder structure

> Status: **proposed, awaiting Ollie's OK** (see the proposal in the session).
> Update this section once agreed.

```
Plastron/                         repo root (Ollie's clone)
├─ CLAUDE.md                      this file
├─ Plastron storyboard mode build brief.md
├─ install/                       Windows installer (portable Blender + shortcut)
├─ plastron/                      THE app template (linked into portable Blender)
│  ├─ __init__.py                 register()/unregister(): core, then features
│  ├─ config/                     ★ everything Ollie asks to tweak
│  │  ├─ keymap.py                every shortcut, one table
│  │  ├─ layout.py                each mode's areas, sizes, visible regions
│  │  ├─ theme.py                 colours
│  │  ├─ hidden_ui.py             Blender menus/panels/headers to hide
│  │  └─ project_defaults.py      resolution, fps, autosave settings
│  ├─ presets/                    shared presets store (JSON), one folder per kind
│  ├─ core/                       shared systems (no feature logic)
│  ├─ timeline/                   the one shared timeline + track system
│  ├─ widgets/                    shared UI components (dot graph, drawing helpers)
│  ├─ features/                   one package per feature, each self-registering
│  └─ assets/                     icon, images
└─ tests/                         headless + Xvfb test runner and tests
```

## Coding conventions

- Target **Blender 5.2 API**. Sequencer strips are `bpy.types.Strip` (not
  `Sequence`). Grease pencil is **v3**: ID type `bpy.types.GreasePencil`,
  object type `'GREASEPENCIL'`. Ignore pre-4.3 GP code and tutorials.
- Naming: operators `plastron.<area>_<verb>` (e.g. `plastron.panel_new`),
  classes `PLASTRON_OT_*`, `PLASTRON_PT_*`, `PLASTRON_MT_*`, property groups
  `PLASTRON_PG_*`. Project data hangs off `scene.plastron`.
- Every package exposes `register()` / `unregister()` and cleans up fully
  (handlers, keymaps, draw handlers, timers).
- All app handlers go through `core` (one place to audit for per-frame cost).
- Keep modules small and single-purpose. Prefer plain data tables in `config/`
  over logic.

## Testing

- Blender here: `/usr/local/bin/blender` (5.2.3 LTS, Linux). Headless:
  `blender -b --factory-startup --python <script>`. GUI tests (layout, screen,
  screenshots): `xvfb-run -a -s "-screen 0 1920x1080x24" blender ...`.
- Keyconfigs are fully populated in `-b` mode, so keymap tests can run headless.
- Run all tests: see `tests/` (runner added in stage 1).

## Decisions log (unspecified details, changeable later)

- Blender pinned to **5.2.3 LTS**.
- Frame rate **24 fps** (YouTube has no default; it keeps the upload's rate,
  and 24 is the animation standard). Project resolution **3840×2160** (final
  4K), storyboard preview and cached panel images at **50 % (1920×1080)**.
- Space = play/pause only. Pan = Alt+Shift+drag (also middle-mouse drag),
  zoom = Ctrl+Alt+drag (also wheel). R (hold) + drag = rotate canvas view,
  snapping back on release. Ctrl+= / Ctrl+- zoom, Ctrl+0 fit, Ctrl+1 100 %.
- Timeline keys: N = new panel at playhead, Ctrl+K = split, Delete/Backspace =
  delete, I / O = loop range in / out.
- Blender's keymap is stripped to Plastron's keys plus essentials (text
  editing, UI widgets, modal maps).
- Top bar: slim, with File menu, mode switcher, undo/redo.
- Autosave every 2 min, keep last 5, in a folder beside the project, with
  File > Recover.
- Theme: dark teal throughout, orange and blue highlights (based on Ollie's
  current Blender theme).
- Value swatches (value groups sampled from an image) are **deferred** to the
  later "value group editor" feature. Don't build them in storyboard mode.
