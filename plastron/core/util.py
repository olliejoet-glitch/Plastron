"""Small helpers shared by core systems."""


def resolve_path(obj, path):
    """Return (owner, attribute) for a dotted path like "overlay.show_floor"."""
    *parents, attr = path.split(".")
    for name in parents:
        obj = getattr(obj, name)
    return obj, attr


def get_path(obj, path):
    owner, attr = resolve_path(obj, path)
    return getattr(owner, attr)


def set_path(obj, path, value):
    owner, attr = resolve_path(obj, path)
    setattr(owner, attr, value)


def operator_exists(idname):
    """True if an operator like "plastron.panel_new" is registered."""
    import bpy
    module, _, name = idname.partition(".")
    try:
        getattr(getattr(bpy.ops, module), name).get_rna_type()
        return True
    except (AttributeError, KeyError):
        return False
