"""Editing keys (Premiere's): Q / W trim the clip under the playhead to the
playhead (its start / its end; ripple tracks close up), Up / Down jump the
playhead to the previous / next cut, J / K / L play backwards / stop / play.
Keys: config/keymap.py.
"""

import bpy

from . import clips, events, ripple, tracks


def clips_at_playhead(scene):
    """The selected clips under the playhead, else the active track's."""
    frame = scene.frame_current
    chosen = [s for s in clips.top_clips(scene) if s.select and clips.start(s) <= frame < clips.end(s)]
    if not chosen:
        track = tracks.active(scene)
        clip = track and clips.at(scene, tracks.channel_of(scene, track), frame)
        chosen = [clip] if clip else []
    # one per link group: its linked clips trim with it
    out = []
    for strip in chosen:
        if not any(strip in clips.linked(o) for o in out):
            out.append(strip)
    return out


def trim_to_playhead(scene, side):
    frame = scene.frame_current
    done = []
    for strip in clips_at_playhead(scene):
        if side == 'LEFT' and clips.start(strip) < frame:
            start = clips.start(strip)
            ripples = ripple._ripples(scene, strip)
            ripple.trim(scene, strip, 'LEFT', frame)
            done.append(strip)
            if ripples:
                scene.frame_current = start          # (the cut closed up: the playhead stays on it)
        elif side == 'RIGHT' and frame < clips.end(strip) and frame > clips.start(strip):
            ripple.trim(scene, strip, 'RIGHT', frame)
            done.append(strip)
    if done:
        events.clips_changed(scene)
    return done


def cuts(scene):
    edges = set()
    for strip in clips.top_clips(scene):
        edges.add(clips.start(strip))
        edges.add(clips.end(strip))
    return sorted(edges)


def jump(scene, direction):
    frame = scene.frame_current
    edges = cuts(scene)
    if direction > 0:
        later = [e for e in edges if e > frame]
        target = later[0] if later else None
    else:
        earlier = [e for e in edges if e < frame]
        target = earlier[-1] if earlier else None
    if target is not None:
        scene.frame_current = target
    return target


class PLASTRON_OT_trim_to_playhead(bpy.types.Operator):
    """Trim the clip under the playhead to the playhead (ripple tracks close up)"""
    bl_idname = "plastron.trim_to_playhead"
    bl_label = "Trim to Playhead"
    bl_options = {'REGISTER', 'UNDO'}
    side: bpy.props.EnumProperty(items=[('LEFT', "Start", "Cut from the clip's start to the playhead"),
                                        ('RIGHT', "End", "Cut from the playhead to the clip's end")])

    def execute(self, context):
        if not trim_to_playhead(context.scene, self.side):
            self.report({'INFO'}, "No clip under the playhead")
            return {'CANCELLED'}
        return {'FINISHED'}


class PLASTRON_OT_jump_cut(bpy.types.Operator):
    """Move the playhead to the previous / next cut"""
    bl_idname = "plastron.jump_cut"
    bl_label = "Jump to Cut"
    direction: bpy.props.IntProperty(default=1)

    def execute(self, context):
        return {'FINISHED'} if jump(context.scene, self.direction) is not None else {'CANCELLED'}


class PLASTRON_OT_shuttle(bpy.types.Operator):
    """Play backwards (-1), stop (0) or play (1)"""
    bl_idname = "plastron.shuttle"
    bl_label = "Play / Stop"
    direction: bpy.props.IntProperty(default=1)

    def execute(self, context):
        playing = context.screen.is_animation_playing
        backwards = _state["backwards"] if playing else False    # (Space plays forwards)
        if playing and (self.direction == 0 or backwards != (self.direction < 0)):
            bpy.ops.screen.animation_cancel(restore_frame=False)
            playing = False
        if self.direction and not playing:
            bpy.ops.screen.animation_play(reverse=self.direction < 0)
            _state["backwards"] = self.direction < 0
        return {'FINISHED'}


_state = {"backwards": False}


classes = (PLASTRON_OT_trim_to_playhead, PLASTRON_OT_jump_cut, PLASTRON_OT_shuttle)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
