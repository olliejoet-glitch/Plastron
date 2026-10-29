"""Blender preferences Plastron sets every time it starts.

Plastron runs from its own portable Blender, so none of this touches Ollie's
normal Blender. Preferences are not saved by Blender: this file is the single
source of truth.
"""

PREFERENCES = {
    "view.show_splash": False,
    "view.show_developer_ui": False,
    "view.show_tooltips_python": False,
    "filepaths.use_load_ui": False,        # opening a project never changes Plastron's layout
    "inputs.use_mouse_emulate_3_button": False,  # Plastron binds Alt+Shift / Ctrl+Alt drags itself
    "edit.undo_steps": 64,
    "use_preferences_save": False,
}
