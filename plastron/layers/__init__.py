"""Photoshop-style layer stacks (shared system), ported from Ollie's CaraPainter.

    props.py         data on Material.plastron_stack
    blend_lib.py     the 26 blend modes as node groups (Photoshop formulas)
    layer_trees.py   one node tree per layer; compiler.py chains them
    flatten.py       the same maths in numpy -> a flat image (panel thumbnails)
    stack.py         add / remove / move / duplicate / group / masks / copy
    paint_target.py  aims Blender's Texture Paint at the active layer
    ops.py, ui.py    operators and the layers panel
    events.py        "this stack changed" for listeners
"""

import bpy

from . import events, ops, props, ui

_CLASSES = ops.classes + ui.classes


def register():
    props.register()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
    events.clear()
