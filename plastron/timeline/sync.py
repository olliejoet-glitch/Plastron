"""Sound back in sync with its picture (Ollie: "despite having linked clips,
my audio and video has drifted out of sync").

A video and its own sound start their media at the same timeline frame when
placed (content_start), and splits / moves / ripple keep that. A linked
picture and sound cut from the SAME file whose media starts differ have
drifted. The timeline header then shows a red "Out of sync" button; Resync
slides each drifted sound's media back under its picture (the clips stay
where they are; trimmed if the media can't reach). The picture is the
reference. Checked once per timeline change (cached), not per draw.
"""

import os

import bpy

from . import clips, events

TOLERANCE = 0.5           # frames of difference that still count as in sync

_cache = {"scene": None, "drifted": None}


def _source(strip):
    if strip.type == 'MOVIE':
        path = strip.filepath
    elif strip.type == 'SOUND' and strip.sound is not None:
        path = strip.sound.filepath
    else:
        return None
    return os.path.normcase(os.path.normpath(bpy.path.abspath(path))) if path else None


def drifted(scene, pool=None):
    """[(sound, picture, frames off)] for linked sounds out of step with their
    own picture (same file)."""
    pool = list(pool) if pool is not None else clips.top_clips(scene)
    index = clips.link_index(clips.top_clips(scene))
    out = []
    for sound in pool:
        if sound.type != 'SOUND':
            continue
        src = _source(sound)
        if src is None:
            continue
        for pic in clips.linked_in(index, sound):
            if pic.type == 'MOVIE' and _source(pic) == src:
                off = sound.content_start - pic.content_start
                if abs(off) > TOLERANCE:
                    out.append((sound, pic, off))
                break
    return out


def drifted_cached(scene):
    if _cache["scene"] != scene.name or _cache["drifted"] is None:
        _cache.update(scene=scene.name, drifted=[(s.name, p.name, o) for s, p, o in drifted(scene)])
    return _cache["drifted"]


def _forget(*_args, **_info):
    _cache["drifted"] = None


def resync(scene, pairs):
    """Slide each sound's media back under its picture. Returns how many."""
    changes = {}
    for sound, pic, _off in pairs:
        content = pic.content_start
        length = sound.content_end - sound.content_start
        start = max(clips.start(sound), round(content))
        end = min(clips.end(sound), round(content + length))
        if end - start < 1:
            continue
        changes[sound] = (start, end, content)
    if changes:
        with events.batch():
            clips.apply(scene, changes)
            events.clips_changed(scene)
    _forget()
    return len(changes)


class PLASTRON_OT_clip_resync(bpy.types.Operator):
    """Put linked sound back in sync with its picture (the selected clips, else every clip)"""
    bl_idname = "plastron.clip_resync"
    bl_label = "Resync Sound"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        chosen = [s for s in clips.top_clips(scene) if s.select]
        pairs = drifted(scene, clips.with_linked(chosen) if chosen else None)
        if not pairs and chosen:
            pairs = drifted(scene)
        n = resync(scene, pairs)
        self.report({'INFO'}, f"Put {n} sound clip{'s' if n != 1 else ''} back in sync" if n else
                    "Everything's in sync")
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'} if n else {'CANCELLED'}


def draw_header(layout, context):
    scene = context.scene
    if scene is None or scene.sequence_editor is None:
        return
    bad = drifted_cached(scene)
    if bad:
        row = layout.row(align=True)
        row.alert = True
        worst = max(abs(o) for _s, _p, o in bad)
        row.operator("plastron.clip_resync", text=f"Out of sync ({len(bad)}, up to {worst:.0f} f)",
                     icon='ERROR')


def register():
    bpy.utils.register_class(PLASTRON_OT_clip_resync)
    events.listen("clips_changed", _forget)
    from . import header
    header.add_section(draw_header)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_clip_resync)
