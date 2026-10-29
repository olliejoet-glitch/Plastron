"""CaraPainter — Photoshop-style base colour layer stacks for EEVEE. See docs/ARCHITECTURE.md."""
import bpy

from . import handlers, props
from .ops import attach, bake, gestures, hybrid, keylight, layers, masks, select, transform, view
from .ops import brushes, formview, multiselect, newmat, thickness
from .ops import outline as silhouette   # (ui.outline is the selection outline)
from .ops import library as lib_ops  # (painterly_layers.library is the scanner package)
from .ui import floating, hud, keymap, outline, panel, workspace


class PL_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    library_folders: bpy.props.CollectionProperty(type=lib_ops.PL_LibFolder)
    brush_folders: bpy.props.CollectionProperty(type=lib_ops.PL_LibFolder)

    def draw(self, context):
        lib_ops.draw_prefs(self.layout)
        brushes.draw_prefs(self.layout)
        keymap.draw_prefs(self.layout)


_classes = (
    *attach.classes, *layers.classes, *keylight.classes, *view.classes, *gestures.classes,
    *select.classes, *transform.classes, *masks.classes, *hybrid.classes, *bake.classes,
    *lib_ops.classes, *formview.classes, *brushes.classes, *multiselect.classes, *thickness.classes, *silhouette.classes, *newmat.classes, *workspace.classes, *panel.classes, PL_Preferences,
)


def register():
    props.register()
    for c in _classes:
        bpy.utils.register_class(c)
    lib_ops.register()
    brushes.subscribe()
    handlers.register()
    keymap.register()
    hud.register()
    outline.register()
    silhouette.register()
    floating.register()
    bpy.types.VIEW3D_HT_header.append(panel.header_button)
    bpy.app.timers.register(_migrate_open_file, first_interval=0.5)   # (no load_post when enabled live)
    from .ops.keylight import watch_views
    if not bpy.app.timers.is_registered(watch_views):
        bpy.app.timers.register(watch_views, first_interval=1.0, persistent=True)


def _migrate_open_file():
    try:
        props.migrate_tree_pointers()
    except Exception as e:
        print("CaraPainter: tree migration:", e)
    return None


def unregister():
    from .ops.keylight import watch_views
    if bpy.app.timers.is_registered(watch_views):
        bpy.app.timers.unregister(watch_views)
    bpy.types.VIEW3D_HT_header.remove(panel.header_button)
    floating.unregister()
    silhouette.unregister()
    outline.unregister()
    hud.unregister()
    keymap.unregister()
    handlers.unregister()
    brushes.unsubscribe()
    lib_ops.unregister()
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
    props.unregister()
