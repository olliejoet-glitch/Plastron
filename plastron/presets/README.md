# Presets

Shared presets store (code: `plastron/core/presets.py`), one folder per kind:
`brushes/`, `motion/`; `drop_warp/`, `export/` later.

Each preset is a small JSON file. The ones here ship with Plastron; to change
one, edit its file. `"order"` sets where it shows in lists. Presets saved from
inside Plastron go to Blender's config folder (`plastron_presets/<kind>/`),
which updates keep, and are listed after these.

## brushes/

| field          | meaning                                                     |
|----------------|-------------------------------------------------------------|
| base           | Blender texture brush it starts from (see config/tools.py)  |
| size           | brush radius in screen pixels                               |
| opacity        | 0-1 (Blender's brush strength)                              |
| pressure_size  | pen pressure changes the size                               |
| pressure_opacity | pen pressure changes the opacity                          |

| spacing        | dab spacing, % of the brush size                            |

Smoothing isn't part of a brush preset: the Stabiliser (Off / Slight / Max in
the options bar, set up in config/tools.py) applies to every brush.

## motion/

Used by both the Camera and the Layer presets menus in the Motion panel
(tools area). A layer only uses "curve"; presets without one (shakes) show
for the camera only.

| field  | meaning                                                              |
|--------|----------------------------------------------------------------------|
| curve  | the easing graph's points, [time, amount] from [0, 0] to [1, 1]; amount over 1 overshoots |
| handle | point shape: "AUTO" (smooth, the default), "AUTO_CLAMPED", "VECTOR" (sharp) |
| shake  | camera shake [amount in % of the frame width, wobbles per second]     |
