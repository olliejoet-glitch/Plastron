"""Timeline header: transport, add track, snapping, loop range, clip volume."""

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

    layout.separator(type='LINE')
    from .edit_tools import active_tool
    tool = active_tool(context)
    row = layout.row(align=True)
    row.operator("plastron.timeline_tool", text="Move", icon='RESTRICT_SELECT_OFF',
                 depress=tool == 'MOVE').tool = 'MOVE'
    row.operator("plastron.timeline_tool", text="Slice", icon='SCULPTMODE_HLT',
                 depress=tool == 'SLICE').tool = 'SLICE'

    layout.separator(type='LINE')
    row = layout.row(align=True)
    row.operator("plastron.panel_new", text="New Panel", icon='ADD')
    row.operator("plastron.clip_split", text="", icon='SCULPTMODE_HLT')

    layout.separator(type='LINE')
    row = layout.row(align=True)
    row.operator("plastron.track_add", text="Video Track", icon='ADD').kind = 'VIDEO'
    row.operator("plastron.track_add", text="Audio Track", icon='ADD').kind = 'AUDIO'

    layout.separator_spacer()

    strip = scene.sequence_editor.active_strip if scene.sequence_editor else None
    if strip and strip.type == 'SOUND' and strip.select:
        layout.prop(strip.plastron, "volume", text="Clip Volume", slider=True)

    ts = scene.tool_settings
    layout.prop(ts, "use_snap_sequencer", text="", icon='SNAP_ON' if ts.use_snap_sequencer else 'SNAP_OFF')
    row = layout.row(align=True)
    row.prop(scene, "use_preview_range", text="Loop", toggle=True)
    sub = row.row(align=True)
    sub.active = scene.use_preview_range
    sub.prop(scene, "frame_preview_start", text="")
    sub.prop(scene, "frame_preview_end", text="")


def register():
    hidden_ui.replace("SEQUENCER_HT_header", "draw", draw)


def unregister():
    pass
