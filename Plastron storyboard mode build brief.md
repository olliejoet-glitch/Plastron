# Plastron storyboard mode: build brief

Oct 28, 2026 · @Ollie

## Overview

Build storyboard mode for Plastron: one place to write a script, record voiceover, sketch storyboard panels, and time them on a timeline.

Plastron is a full audiovisual video editing app, built as a Blender application template. It should feel like its own app, with only the tools the user needs, laid out where they expect them, and Photoshop-style shortcuts. Storyboard mode is the first feature to build, but it is one part of the whole app, not a standalone tool. The other planned features (listed at the end of this brief) will be added to the same app over time.

**Build it as the foundation of the full editor:**

- **One timeline:** storyboard mode uses Plastron's main timeline and track system, not a separate one. The same tracks, ripple and lock toggles, snapping, and clips will carry the final edit, so an animatic can grow into the finished video in the same file.
- **Modular features:** each feature lives in its own module with a clear place to plug in, so later features (audio tools, grading, effects, exports) can be added without reworking storyboard mode.
- **Shared systems:** build the dot graph, presets, shortcuts, and track headers as shared components that every future feature will use.
- **Modes, not apps:** storyboard mode is a layout of the app. Switching to editing, audio, or other modes later should keep the same project, timeline, and media.

Everything in this brief has been agreed with the user. Where a detail isn't specified, pick the simplest option that fits and note it in the project notes file so it can be changed later. The user's main goal is easy customisation: they will regularly ask for things to be moved, removed, or changed, so the code should be organised to make that fast.

## Technical foundation and constraints

- **Blender application template:** Plastron launches straight into its own layout, theme, and keymap via a desktop shortcut with its own icon. Hide Blender's default menus, workspace tabs, and panels that Plastron doesn't use.
- **Separate portable Blender install:** Plastron runs from its own copy of the latest stable Blender, so the user's normal Blender setup is untouched and updates happen only when chosen.
- **One add-on repo:** keep all Plastron code in one add-on folder with a notes file (CLAUDE.md) describing structure, conventions, and the user's preferences, so future sessions can change things quickly.
- **Grease pencil v3:** target the grease pencil system introduced in Blender 4.3. Older grease pencil code and tutorials don't apply.
- **Reference:** Blender Studio's Storypencil add-on (GPL) already links grease pencil drawings to editor clips. Borrow its approach where useful rather than starting from zero.
- **Licence:** Plastron is GPL, as required for Blender add-ons. It's for personal use.

**Performance rules (the user's top technical priority):**

- Nothing may make Blender re-evaluate every frame. Previous custom tools for this user hit this problem repeatedly.
- Panels not being drawn on show on the timeline as cached images, so long animatics scrub and play smoothly.
- Destructive edits (warp, perspective, flips) apply to the strokes on confirm, not as live modifiers.
- Transcription runs once after each recording. Transcript layout is recalculated only on zoom or edit, never during scrubbing or playback.

**Testing:** the user wants to do the absolute minimum manual testing. Test as much as possible by running Blender headless from scripts: shortcuts bound, menus hidden, clips created and resized, ripple behaviour, export output. Leave only look-and-feel checks to the user, and tell them exactly what to check.

## Layout

Storyboard mode is one screen with four areas:

- **Script panel (left):** a plain text area for writing the script, line by line.
- **Canvas (centre):** shows whichever panel is under the playhead and is where drawing happens. Scrubbing to a moment and drawing edits that panel.
- **Tool strip (right):** a short vertical strip of the drawing tools, plus a layers panel for the current panel.
- **Timeline (bottom):** video and audio tracks, a ruler you scrub on, and a playhead.

Keep the interface minimal. Anything not listed in this brief stays hidden.

## Timeline and tracks

Each storyboard panel is a clip on the timeline, and its length is its timing. Panels are created manually only, never automatically from voiceover timing.

- **New panel at playhead:** a button and a shortcut.
- **Resize to retime:** drag a panel's edges to change its length.
- **Scrubbing:** a ruler and playhead that work like Blender's normal timeline.
- **Multiple tracks:** any number of video and audio tracks, with an "add track" button. Each track header shows its name, a ripple toggle, a lock toggle, and mute, solo, and volume controls.
- **Per-track ripple:** with ripple on, resizing or deleting a clip shifts everything after it on that track and on every other track with ripple on. With ripple off, other clips stay put, leaving gaps or stopping at the next clip. Blender's built-in behaviour doesn't fully cover this (it can push clips when lengthening but doesn't pull them back when shortening), so build a proper ripple feature.
- **Lock per track:** a locked track can't be edited or shifted, so finished voiceover or music can't be nudged by accident.
- **Shared backgrounds:** a background drawn on a track below the panels and stretched across several panels. Panels above only need the creature or foreground.
- **Split at playhead:** one key cuts a clip in two.
- **Snapping:** clips snap to the playhead, other clip edges, and beat markers.
- **Volume per clip** as well as per track.
- **Loop playback:** set a range and loop it.
- **Audio scrubbing:** hear the audio while dragging the playhead.
- **Undo and redo:** Ctrl+Z and Ctrl+Shift+Z work the same way for timeline edits and drawing.
- **Autosave and crash recovery:** frequent automatic saves with easy recovery, since heavy grease pencil files are a crash risk.

## Voiceover and transcript

**Recording**

- **Record at playhead:** records the microphone onto the selected audio track starting at the playhead. Blender can't record audio itself, so use a small Python audio library and drop the result in as a clip.
- **Retakes:** new takes of the same line stack on the same clip. The user can flip between them, and swapping a take respects the track's ripple setting.

**Transcript bar**

Every audio track has a transcript bar underneath it, showing what was actually said.

- **Local transcription:** run once after each recording, on the user's computer, with a timestamp for each word. It shows what was said, including fluffs and ad-libs, not the script.
- **Clip-bound text:** each clip's words stay within that clip's edges and wrap when needed.
- **Height:** the bar grows to fit the longest-wrapping clip on that track, so track rows stay aligned.
- **Collapse:** a toggle shrinks the bar to one line ending in "…".
- **Zoom-aware layout:** when zoomed in far enough, words sit at their exact time positions on one line. When zoomed out, they switch to wrapped text.
- **Hover and click:** hovering a word highlights its exact spot on the waveform. Clicking it moves the playhead there.
- **Trimmed words:** words in a trimmed-off part of a clip show greyed out and struck through.

**Cut by words:** select words in the transcript bar and delete them to cut the matching audio. It follows that track's ripple setting.

**Script linking:** clicking a line in the script panel moves the playhead to where it's spoken, matched through the transcript. Script words that haven't been recorded yet are highlighted.

## Drawing

Drawing uses grease pencil, presented the Photoshop way. These shortcuts override Blender's defaults inside Plastron only.

| Key | Action |
| --- | --- |
| B | Pencil |
| E | Eraser |
| Q | Smaller brush |
| W | Bigger brush |
| L | Lasso select strokes |
| M | Rectangle select |
| V | Move |
| Ctrl+T | Transform (scale, rotate, move, warp, perspective) |
| Ctrl+C / Ctrl+V | Copy and paste between panels, in place by default |
| Ctrl+F | Flip canvas view (drawing unchanged) |
| Ctrl+Alt+F | Flip selected strokes, or selected layers if no strokes are selected |
| Alt+click | Eyedropper |
| Space+drag | Pan |
| Hold key + drag | Rotate canvas view, snapping back on release |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo |

Also add keys for zoom and fit to screen.

**Layers per panel**

- Each panel has its own Photoshop-style layers panel: visibility, opacity, lock, and reordering.
- **Layer groups**, which grease pencil v3 supports natively.
- **Blend modes**, at least normal, multiply, and screen.

**Transform (Ctrl+T)**

- A box around the selection with handles to scale, rotate, and move.
- **Warp mode:** a grid over the selection that the user drags to bend the strokes, like Photoshop's warp.
- **Perspective and distort:** drag individual corners to skew the selection into perspective (corner pin). Not Photoshop's separate plane-based Perspective Warp tool.
- Warp and perspective apply to the strokes on confirm, not as live effects.

**Brushes and feel**

- Pencil, eraser, and fill tools.
- A few brush presets, such as pencil, ink, marker, and soft shading.
- **Stroke smoothing:** a stabiliser slider.
- **Pressure settings** for how pen pressure affects size and opacity.
- **Value swatches:** four preset greys matching the user's four value groups.
- **Onion skin:** a faint view of the previous or next panel.

## Camera and animation

**Oversized canvas**

- Each panel's canvas extends well beyond the camera frame, with the area outside the frame dimmed.
- A toggle hides everything outside the frame for a clean view.
- The camera frame's position is set at the start and end of the clip, for pans. The same approach handles zoom and a slight rotation.

**Layer and group motion**

- Select a layer or layer group, set its position at the start of the clip and again at the end, and it moves between them.
- No full keyframe animation is needed.

**The dot graph**

Easing and extra points for camera and layer motion use the dot graph: a curve with points the user adds and drags. Build it as one reusable component, because Plastron will later use the same graph for audio pitch, audio volume, and clip speed.

**Motion presets**

Presets for ease in, ease out, overshoot, and a small camera shake. Store them where Plastron's other presets will live, such as the drop warp presets planned for later.

## Planning and review

- **Board view:** a toggle that switches the timeline to a grid of panel thumbnails. Drag to reorder, then switch back with the timeline updated.
- **Shot status:** a colour tag per panel: sketch, blocking, animated, or final. When a render replaces a sketch, the old sketches stay stacked underneath as versions. The user can flip between versions or show a sketch faintly over the render to compare.
- **Panel notes:** a small text field per panel for camera moves, sound ideas, or acting notes.
- **Framing guides:** toggleable canvas overlays for rule of thirds, YouTube safe areas, and a 9:16 frame for checking whether a shot works as a Short.
- **Speed playback:** play at 1.5x or 2x with the voice kept at normal pitch.
- **Temp sound drops:** a small sound effects bin for dragging in placeholder sounds, tagged so they're easy to find and replace later.

## Import and export

- **Drag-and-drop import:** images, audio, and video dropped straight onto tracks.
- **Animatic export:** one click to export a video of the animatic with sketches, voice, and temp music.
- **Panel sheet export:** all panels as a printable grid or PDF, with each panel's notes underneath.
- **Shot list export:** panel notes exported as a shot list.

## Out of scope and build order

**Not wanted (decided against):** panels created automatically from voiceover timing, panel-to-Blender-shot handoff, a runtime tracker, an "edit in Photoshop" round trip, panel transitions, and Photoshop's plane-based Perspective Warp tool.

**Coming to Plastron after storyboard mode:** breath remover, auto-ducking, loudness normalising, creature voice stacks, captions exported as .srt, drop warp presets, colour grading, value group editor, bake in place, Shorts reframing, export presets, music fitting, beat detection, and video templates. Design storyboard mode so these can plug in, especially the shared dot graph and the presets system. Snapping should already support beat markers once beat detection exists.

**Suggested build order**

1. Application template, portable install setup, minimal layout, and keymap.
2. Panels as clips: create, resize, scrub, multiple tracks, per-track ripple and lock, split, snapping, undo, and autosave.
3. Drawing basics: tools, shortcuts, layers and groups, brush presets, smoothing, pressure, onion skin, and cached panel images.
4. Voiceover recording with retakes, then the transcript bar, cut by words, and script linking.
5. Transform tools: Ctrl+T, warp, perspective, flips, and copy-paste between panels.
6. Camera and motion: oversized canvas, camera moves, layer and group motion, the dot graph, and motion presets.
7. Planning, review, and export: board view, shot status and versions, notes, guides, speed playback, temp sounds, and all exports.

After each stage, run the automated tests, then give the user a short list of anything they need to check by eye.
