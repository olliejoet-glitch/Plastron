"""Left-hand hotkeys (ARCHITECTURE §10). Operators poll on the CaraPainter workspace flag, so
outside it the keys fall through to Blender's defaults."""
import bpy

# (operator, key, modifiers, properties)
KEYS = [
    ("pl.brush_size", 'Q', {}, {"step": -1}),
    ("pl.brush_size", 'W', {}, {"step": 1}),
    ("pl.eraser_toggle", 'E', {}, {}),
    ("pl.brush_tool", 'B', {}, {}),
    ("pl.gesture_opacity", 'A', {}, {}),
    ("pl.gesture_huesat", 'S', {}, {"new_layer": True}),
    ("pl.gesture_huesat", 'S', {"shift": True}, {"new_layer": False}),
    ("pl.pick_color", 'Z', {}, {"lit": True}),                  # what you see (user's choice, 0.21.1)
    ("pl.pick_color", 'Z', {"shift": True}, {"lit": False}),    # the unlit paint
    ("pl.toggle_base_view", 'C', {}, {}),
    ("pl.toggle_form_view_key", 'C', {"shift": True}, {}),
    ("pl.layer_toggle_visibility", 'V', {}, {}),
    ("pl.lasso_select", 'L', {}, {}),
    ("pl.gesture_mask", 'D', {}, {}),
    ("pl.paint_target_toggle", 'T', {}, {}),
    ("pl.gesture_form", 'F', {}, {}),
    ("pl.gesture_threshold", 'F', {"shift": True}, {}),
    ("pl.transform", 'T', {"ctrl": True}, {}),
    ("pl.deselect", 'D', {"ctrl": True}, {}),
    ("pl.layer_merge", 'E', {"ctrl": True}, {}),
    ("pl.layer_group", 'G', {"ctrl": True}, {}),
]

_items = []


def register():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:  # background mode
        return
    km = kc.keymaps.new(name="Image Paint", space_type='EMPTY')
    for op, key, mods, props in KEYS:
        kmi = km.keymap_items.new(op, key, 'PRESS', **mods)
        for k, v in props.items():
            setattr(kmi.properties, k, v)
        _items.append((km, kmi))
    # looking at the model doesn't need paint mode: the flat-colour view also works in Object Mode
    km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
    _items.append((km, km.keymap_items.new("pl.toggle_base_view_key", 'C', 'PRESS')))
    _items.append((km, km.keymap_items.new("pl.toggle_form_view_key", 'C', 'PRESS', shift=True)))
    # layer commands work from Object Mode too
    _items.append((km, km.keymap_items.new("pl.layer_merge_key", 'E', 'PRESS', ctrl=True)))
    _items.append((km, km.keymap_items.new("pl.layer_group_key", 'G', 'PRESS', ctrl=True)))
    # ... and with the mouse over the layer panel (mode keymaps only cover the viewport itself)
    km = kc.keymaps.new(name="Window", space_type='EMPTY')
    _items.append((km, km.keymap_items.new("pl.layer_merge_key", 'E', 'PRESS', ctrl=True)))
    _items.append((km, km.keymap_items.new("pl.layer_group_key", 'G', 'PRESS', ctrl=True)))


def unregister():
    for km, kmi in _items:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _items.clear()


def draw_prefs(layout):
    import rna_keymap_ui
    kc = bpy.context.window_manager.keyconfigs.user
    km = kc.keymaps.get("Image Paint")
    if km is None:
        return
    col = layout.column()
    col.label(text="Hotkeys (active only in the CaraPainter workspace):")
    for _km, kmi in _items:
        user = next((i for i in km.keymap_items if i.idname == kmi.idname and i.type == kmi.type
                     and i.shift == kmi.shift and i.ctrl == kmi.ctrl), None)
        if user is not None:
            rna_keymap_ui.draw_kmi([], kc, km, user, col, 0)
