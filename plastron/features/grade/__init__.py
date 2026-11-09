"""Grade mode: colour grading on the same timeline (config/grade.py).

    grade   a clip's grade (Blender's colour modifiers), looks, copy / paste,
            Grade Everything (an adjustment clip over the whole project)
    panel   the Grade panel (the picture's sidebar)
"""

from . import grade, panel

_MODULES = (grade, panel)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
