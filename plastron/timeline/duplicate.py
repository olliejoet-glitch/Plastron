"""Alt+drag a clip: a copy of it (and of the clips selected with it, and
their linked sounds) follows the pen; let go to drop it (Ollie: "alt drag
on a clip to duplicate it and be able to drag that clip elsewhere").

The copies are made with Blender's own duplicate, then each feature makes
them their own (a panel gets its own copy of the painting; event
"clip_duplicated"), linked clips get a link of their own, and Blender's
drag-move carries them. Where they land follows the track's ripple
(ripple_move: fresh copies leave no gap). Esc / right-click, or a click
without moving, takes the copies away again.
"""

import uuid

import bpy

from . import clips, events, tracks

SRC = "plastron_dup_src"
pending = {"names": {}, "op": 0}      # copy name -> (channel, start, end) of what it copies


def clip_at(scene, region, x, y):
    frame, ch = region.view2d.region_to_view(x, y)
    return clips.at(scene, int(ch), int(frame)) if ch >= 1 else None


def _last_op_pointer():
    wm = bpy.context.window_manager
    return wm.operators[-1].as_pointer() if wm and len(wm.operators) else 0


def duplicate(scene, strips):
    """Copies of strips (Blender's duplicate, then made their own). Returns {copy: original}."""
    for s in clips.all_clips(scene):
        s.select = s in strips
        if SRC in s:
            del s[SRC]
    for s in strips:
        s[SRC] = s.name
    bpy.ops.sequencer.duplicate()
    sed = clips.editor(scene)
    made = {}
    for s in list(sed.strips_all):
        src = s.get(SRC)
        if src and src != s.name and src in sed.strips_all:
            made[s] = sed.strips_all[src]
    for s in list(sed.strips_all):
        if SRC in s:
            del s[SRC]
    relink = {}
    for copy, original in made.items():
        uid = original.get(clips.LINK)
        if uid:
            relink.setdefault(uid, []).append(copy)
        events.emit("clip_duplicated", scene, original=original, new=copy)
    for group in relink.values():
        new_uid = uuid.uuid4().hex[:10]
        for s in group:
            s[clips.LINK] = new_uid
    return made


class PLASTRON_OT_clip_duplicate_drag(bpy.types.Operator):
    """Alt+drag a clip: drag a copy of it"""
    bl_idname = "plastron.clip_duplicate_drag"
    bl_label = "Duplicate Clip"
    bl_options = {'REGISTER'}           # (the drag that follows makes the undo step)

    @classmethod
    def poll(cls, context):
        from ..core.views import is_timeline
        return context.scene is not None and is_timeline(context.space_data)

    def invoke(self, context, event):
        scene = context.scene
        hit = clip_at(scene, context.region, event.mouse_region_x, event.mouse_region_y)
        if hit is None or clips.editor(scene).channels[hit.channel].lock:
            return {'PASS_THROUGH'}
        if not hit.select:
            for s in clips.all_clips(scene):
                s.select = False
            hit.select = True
        chosen = [s for s in clips.top_clips(scene) if s.select]
        chosen = clips.with_linked(chosen, clips.top_clips(scene))
        made = duplicate(scene, chosen)
        if not made:
            return {'CANCELLED'}
        pending["names"] = {c.name: (o.channel, clips.start(o), clips.end(o)) for c, o in made.items()}
        pending["op"] = _last_op_pointer()
        for s in clips.all_clips(scene):
            s.select = s in made
        bpy.ops.transform.seq_slide('INVOKE_DEFAULT', release_confirm=True)
        return {'FINISHED'}


def take_back(scene):
    """The drag was cancelled (or never moved): the copies go."""
    from . import ripple
    sed = clips.editor(scene)
    for name in list(pending["names"]):
        strip = sed.strips_all.get(name)
        if strip is not None:
            events.emit("clip_removing", scene, strip=strip)
            ripple.remove(scene, strip)
    pending["names"] = {}


def register():
    bpy.utils.register_class(PLASTRON_OT_clip_duplicate_drag)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_clip_duplicate_drag)
