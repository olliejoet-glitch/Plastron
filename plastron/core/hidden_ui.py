"""Hides Blender UI listed in config/hidden_ui.py; restores it on exit.

Panels stay registered (add-ons may extend them) but get a poll() that
returns False. Blender only reads poll() at registration, so each panel is
re-registered: children unregistered first, parents registered first.
Headers are replaced by swapping their draw methods; Plastron's UI modules
call replace() with their own versions.
"""

import bpy

from ..config import hidden_ui as cfg

_hidden_panels = []   # (class, original poll or None), children first
_replaced = []        # (class, attribute name, original)


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def panels_to_hide():
    """Blender panels and asset shelves to hide, children first."""
    places = set(cfg.HIDE_PANELS_IN)
    found = []
    for cls in set(_all_subclasses(bpy.types.Panel)):
        if cls.__name__.startswith("PLASTRON_") or not getattr(cls, "is_registered", False):
            continue
        place = (getattr(cls, "bl_space_type", None), getattr(cls, "bl_region_type", None))
        if place in places:
            found.append(cls)
    for cls in set(_all_subclasses(bpy.types.AssetShelf)):
        if cls.__name__.startswith("PLASTRON_") or not getattr(cls, "is_registered", False):
            continue
        if getattr(cls, "bl_space_type", None) in cfg.HIDE_ASSET_SHELVES_IN and \
                getattr(cls, "bl_idname", cls.__name__) not in cfg.KEEP_ASSET_SHELVES:
            found.append(cls)
    by_id = {getattr(c, "bl_idname", c.__name__): c for c in found}

    def depth(cls):
        d, parent = 0, getattr(cls, "bl_parent_id", "")
        while parent in by_id and d < 20:
            d, parent = d + 1, getattr(by_id[parent], "bl_parent_id", "")
        return d

    return sorted(found, key=depth, reverse=True)   # children first


def replace(class_name, attr, func):
    """Swap a Blender UI class's method (e.g. a header's draw) for Plastron's."""
    if class_name not in cfg.REPLACE_HEADERS:
        return
    cls = getattr(bpy.types, class_name)
    _replaced.append((cls, attr, getattr(cls, attr)))
    setattr(cls, attr, func)


def _never(cls, context):
    return False


def _set_polls(entries, make_poll):
    """Re-register panels with new polls. entries: [(class, original)] children first."""
    for cls, _original in entries:
        bpy.utils.unregister_class(cls)
    for cls, original in reversed(entries):
        poll = make_poll(original)
        if poll is None:
            if "poll" in cls.__dict__:
                delattr(cls, "poll")
        else:
            cls.poll = poll
        bpy.utils.register_class(cls)


def register():
    # Add-ons (e.g. Cycles) register their panels after Plastron, so hide
    # once startup has finished.
    bpy.app.timers.register(hide_panels, first_interval=0.01)


def hide_panels():
    entries = [(cls, cls.__dict__.get("poll")) for cls in panels_to_hide()
               if not is_hidden(cls)]
    try:
        _set_polls(entries, lambda _original: classmethod(_never))
        _hidden_panels.extend(entries)
    except (RuntimeError, ValueError) as ex:
        print("Plastron: couldn't hide panels:", ex)
    return None


def is_hidden(cls):
    return any(c is cls for c, _ in _hidden_panels)


def unregister():
    try:
        _set_polls(_hidden_panels, lambda original: original)
    except (RuntimeError, ValueError) as ex:
        print("Plastron: couldn't restore panels:", ex)
    _hidden_panels.clear()
    for cls, attr, original in reversed(_replaced):
        setattr(cls, attr, original)
    _replaced.clear()
