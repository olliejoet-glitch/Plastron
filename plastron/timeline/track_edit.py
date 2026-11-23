"""Tidying tracks (Ollie: "rename tracks and stuff in Edit mode ... so I
can have them close together whilst editing; I don't think I need a
Background layer; the Script I can turn on and off in Edit mode").

- Remove Track (the header's "-" next to + Video / + Audio Track): removes
  the active track (asks first if it has clips); the tracks above close up.
- Script lane in Edit mode: the header's "Script" eye hides it there (it's
  parked above the other tracks, out of view, so the rest sit together);
  it's shown again in other modes and when the eye is clicked again.
  Remembered in the project (scene.plastron_timeline.script_hidden_edit).
- Renaming: double-click a track's name (Blender's own).
"""

import bpy

from ..core import handlers, modes
from . import events, tracks

EDIT_MODE = "Edit"


def apply(scene, mode_name):
    """Show / hide the Script lane for the mode now shown."""
    lane = tracks.script_track(scene) if scene is not None and hasattr(scene, "plastron_timeline") else None
    if lane is None:
        return
    hide = mode_name == EDIT_MODE and scene.plastron_timeline.script_hidden_edit
    if lane.hidden != hide:
        tracks.set_hidden(scene, lane, hide)
        _reframe()


def _reframe():
    from . import view
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR' and area.spaces.active.view_type == 'SEQUENCER':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is not None:
                    try:
                        view.frame(window, area, region, window.scene)
                    except RuntimeError:
                        pass
                area.tag_redraw()


def _mode_name(context):
    window = context.window or (context.window_manager.windows[0] if context.window_manager.windows else None)
    return window.workspace.name if window else ""


def _flag_changed(self, context):
    apply(self.id_data, _mode_name(context))


def _after_switch(context, mode_name):
    apply(context.scene, mode_name)


def _on_load(scene):
    apply(scene, _mode_name(bpy.context))


class PLASTRON_OT_track_remove(bpy.types.Operator):
    """Remove the active track (the last track clicked) and its clips; the tracks above close up"""
    bl_idname = "plastron.track_remove"
    bl_label = "Remove Track"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and tracks.active(context.scene) is not None

    def invoke(self, context, event):
        scene = context.scene
        track = tracks.active(scene)
        from . import clips
        if clips.on_channel(scene, tracks.channel_of(scene, track)):
            return context.window_manager.invoke_confirm(
                self, event, title=f"Remove {tracks.name(scene, track)} and its clips?", confirm_text="Remove")
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        track = tracks.active(scene)
        if track.kind == 'SCRIPT':
            self.report({'INFO'}, "The Script lane can't go: hide it in Edit mode (the Script eye) instead")
            return {'CANCELLED'}
        name = tracks.name(scene, track)
        tracks.remove(scene, list(tracks.all_tracks(scene)).index(track))
        self.report({'INFO'}, f"Removed {name}")
        _reframe()
        return {'FINISHED'}


def draw_header(layout, context):
    """Edit mode: the Script lane's eye."""
    if _mode_name(context) != EDIT_MODE or tracks.script_track(context.scene) is None:
        return
    tl = context.scene.plastron_timeline
    layout.prop(tl, "script_hidden_edit", text="Script", toggle=True, invert_checkbox=True,
                icon='HIDE_ON' if tl.script_hidden_edit else 'HIDE_OFF')


def register():
    bpy.utils.register_class(PLASTRON_OT_track_remove)
    from . import header
    header.add_section(draw_header)
    modes.after_switch.append(_after_switch)
    handlers.on_load(_on_load)


def unregister():
    if _after_switch in modes.after_switch:
        modes.after_switch.remove(_after_switch)
    bpy.utils.unregister_class(PLASTRON_OT_track_remove)
