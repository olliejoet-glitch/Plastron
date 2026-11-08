"""The one place Plastron hooks into Blender's app handlers.

Every handler goes through add(), so per-frame cost can be audited in one
spot (and the tests check it). Handlers in PER_FRAME run during playback and
scrubbing: anything added there must be an O(1) "did anything relevant
change?" check that returns early.
"""

import bpy
from bpy.app.handlers import persistent

PER_FRAME = {
    "frame_change_pre", "frame_change_post",
    "depsgraph_update_pre", "depsgraph_update_post",
}

_added = []  # (handler list name, function)


def add(list_name, func, first=False):
    """first: run before the handlers already there (e.g. read an edit before
    another handler reacts to it)."""
    wrapped = persistent(func)
    if first:
        getattr(bpy.app.handlers, list_name).insert(0, wrapped)
    else:
        getattr(bpy.app.handlers, list_name).append(wrapped)
    _added.append((list_name, wrapped))
    return wrapped


_on_load = []  # functions run after every project load


def on_load(func, first=False):
    """Run func(scene) after any project is opened or a new one is made.
    first: before the others (e.g. put the window back on the main scene)."""
    if first:
        _on_load.insert(0, func)
    else:
        _on_load.append(func)
    return func


def run_on_load(*_args):
    """Run every on_load function now (also used for the file open at startup)."""
    for func in _on_load:
        func(bpy.context.scene)


def registered():
    """[(list name, function name)] of everything Plastron has hooked."""
    return [(name, getattr(f, "__name__", repr(f))) for name, f in _added]


def register():
    add("load_post", run_on_load)


def unregister():
    for list_name, func in reversed(_added):
        handlers = getattr(bpy.app.handlers, list_name)
        if func in handlers:
            handlers.remove(func)
    _added.clear()
    _on_load.clear()
