"""Link / unlink clips by hand (Ollie: "link a video and an audio track so
they automatically stay connected, like in DaVinci").

Ctrl+Alt+L (Resolve's key) or the header's chain button on the selected
clips: not all linked together -> linked (they select, move, trim, cut,
delete and ripple together, like a video and its own sound); already linked
together -> unlinked.

Clips cut differently (Ollie separated a recording's ums, then linked it to
its video: one long video was linked to every piece, so deleting an um took
the whole video along) are linked piece by piece: each clip is cut where the
others have cuts, then the pieces over the same stretch are linked (an um
piece's partner is marked as an um too, so Delete takes both).
"""

import bpy

from . import clips, events


def selected(scene):
    return [s for s in clips.top_clips(scene) if s.select]


UM = "plastron_um"


def mismatched(strips):
    """True if the clips are on two or more tracks and not cut the same."""
    spans = {}
    for s in strips:
        spans.setdefault(s.channel, []).append((clips.start(s), clips.end(s)))
    if len(spans) < 2:
        return False
    first, *rest = (sorted(v) for v in spans.values())
    return any(r != first for r in rest)


def link_matching(scene, strips):
    """Cut each clip at the others' cuts inside it, then link the pieces over
    the same stretch. Returns how many links were made."""
    import bisect
    with events.batch():
        strips = list(strips)
        clips.unlink_all(strips)
        cuts = sorted({f for s in strips for f in (clips.start(s), clips.end(s))})
        pieces = []
        for s in strips:
            a, b = clips.start(s), clips.end(s)
            inside = cuts[bisect.bisect_right(cuts, a):bisect.bisect_left(cuts, b)]
            pieces.append(s)
            for f in reversed(inside):              # (from the right: s stays the left part)
                right = s.split(frame=f, split_method='SOFT')
                if right is not None:
                    events.emit("clip_split", scene, original=s, new=right)
                    pieces.append(right)
        groups = {}
        for s in pieces:
            groups.setdefault((clips.start(s), clips.end(s)), []).append(s)
        made = 0
        for group in groups.values():
            if len({s.channel for s in group}) < 2:
                continue
            clips.link(group)
            made += 1
            if any(s.get(UM) for s in group):
                for s in group:
                    s[UM] = 1
        events.clips_changed(scene)
    return made


def linked_together(strips):
    ids = {s.get(clips.LINK) for s in strips}
    return len(strips) > 1 and len(ids) == 1 and None not in ids


class PLASTRON_OT_clip_link(bpy.types.Operator):
    """Link the selected clips so they stay together (or unlink them if they already are)"""
    bl_idname = "plastron.clip_link"
    bl_label = "Link Clips"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.sequence_editor is not None

    def execute(self, context):
        scene = context.scene
        strips = selected(scene)
        if len(strips) > 2 and mismatched(strips):
            n = link_matching(scene, strips)
            self.report({'INFO'}, f"Cut to match and linked {n} pair{'s' if n != 1 else ''}")
        elif linked_together(strips):
            clips.unlink_all(strips)
            self.report({'INFO'}, f"Unlinked {len(strips)} clips")
        elif len(strips) < 2:
            strips = clips.with_linked(strips)
            if len(strips) > 1:
                clips.unlink_all(strips)
                self.report({'INFO'}, "Unlinked")
            else:
                self.report({'INFO'}, "Select two or more clips to link")
                return {'CANCELLED'}
        else:
            clips.unlink_all(clips.with_linked(strips))
            clips.link(strips)
            self.report({'INFO'}, f"Linked {len(strips)} clips")
        events.clips_changed(scene)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def draw_header(layout, context):
    strips = selected(context.scene)
    if strips:
        together = linked_together(strips) or (len(strips) == 1 and bool(strips[0].get(clips.LINK)))
        layout.operator("plastron.clip_link", text="", icon='LINKED' if together else 'UNLINKED',
                        depress=together)


def register():
    bpy.utils.register_class(PLASTRON_OT_clip_link)
    from . import header
    header.add_section(draw_header)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_clip_link)
