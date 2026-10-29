# Presets

Shared presets store (code: `plastron/core/presets.py`), one folder per kind:
`brushes/` now; `motion/`, `drop_warp/`, `export/` later.

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
| smooth         | stroke smoothing on                                         |
| smooth_radius  | how far behind the pen the stroke trails (pixels)           |
| spacing        | dab spacing, % of the brush size                            |
