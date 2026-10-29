"""Timeline header: transport controls and the current frame."""

from ..core import hidden_ui


def draw(self, context):
    layout = self.layout
    scene = context.scene
    playing = context.screen.is_animation_playing

    row = layout.row(align=True)
    row.operator("screen.frame_jump", text="", icon='REW').end = False
    row.operator("screen.animation_play", text="", icon='PAUSE' if playing else 'PLAY')
    row.operator("screen.frame_jump", text="", icon='FF').end = True

    layout.prop(scene, "frame_current", text="")
    layout.separator_spacer()


def register():
    hidden_ui.replace("SEQUENCER_HT_header", "draw", draw)


def unregister():
    pass
