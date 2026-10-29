"""Blender interface that Plastron hides.

Plastron's own panels are never hidden by these rules.
"""

# Hide every Blender panel in these (editor, region) places.
# Region names: 'UI' = sidebar, 'TOOLS' = toolbar, 'WINDOW' = main area,
# 'HEADER' = header popovers.
HIDE_PANELS_IN = [
    ('PROPERTIES', 'WINDOW'),    # the tools area: only Plastron's tool strip + layers
    ('VIEW_3D', 'UI'),
    ('VIEW_3D', 'TOOLS'),
    ('SEQUENCE_EDITOR', 'UI'),
    ('SEQUENCE_EDITOR', 'TOOLS'),
    ('TEXT_EDITOR', 'UI'),
]

# Hide Blender's asset shelves (e.g. the brush shelf under the canvas) in these editors.
HIDE_ASSET_SHELVES_IN = ['VIEW_3D']

# Blender headers replaced with Plastron's slimmer versions (see plastron/ui/).
REPLACE_HEADERS = [
    "TOPBAR_HT_upper_bar",       # top bar: File menu, undo/redo, mode switcher
    "SEQUENCER_HT_header",       # timeline header: transport controls
    "VIEW3D_HT_tool_header",     # canvas options bar: brush size, strength...
]
