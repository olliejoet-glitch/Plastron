"""Photoshop-style layer stacks (shared system), ported from Ollie's CaraPainter.

    props.py         data on Material.plastron_stack
    blend_lib.py     the 26 blend modes as node groups (Photoshop formulas)
    layer_trees.py   one node tree per layer; compiler.py chains them
    flatten.py       the same maths in numpy -> a flat image (panel thumbnails)
    stack.py         add / remove / move / duplicate / group / masks / copy
    paint_target.py  aims Blender's Texture Paint at the active layer
    ops.py, ui.py    operators and the layers panel
    events.py        "this stack changed" for listeners

Layer images are packed into the project; painted ones are re-packed when
the project is saved.
"""

import bpy

from ..core import handlers
from . import events, ops, props, ui

_CLASSES = ops.classes + ui.classes


def _save_pre(*_args):
    """Painting changes an image's pixels, not its packed copy: re-pack them."""
    for img in bpy.data.images:
        if img.get("plastron_owned") and (img.is_dirty or img.packed_file is None):
            try:
                img.pack()
            except RuntimeError as err:
                print(f"Plastron: could not pack {img.name}: {err}")


def register():
    props.register()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    handlers.add("save_pre", _save_pre)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
    events.clear()
