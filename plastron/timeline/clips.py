"""Low-level clip helpers on top of Blender's sequencer strips.

Uses Blender 5.2's timing names (left_handle / right_handle / content_start;
the frame_final_* names are deprecated). End frames are exclusive.

Blender pushes a strip to another channel if a change makes it overlap a
neighbour even for a moment, so all repositioning goes through apply(),
which orders the changes so nothing ever overlaps.
"""

import uuid

LINK = "plastron_link"      # clips sharing this id move / trim / cut together (a video + its sound)


def link(strips):
    """Link these clips: edits to one carry to the others. They're also
    Blender's "connected" strips, so its own click-select and drag-move take
    them together."""
    uid = uuid.uuid4().hex[:10]
    for strip in strips:
        strip[LINK] = uid
    _connect(strips)


def _connect(strips):
    import bpy
    if len(strips) < 2:
        return
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        area = next((a for a in window.screen.areas if a.type == 'SEQUENCE_EDITOR'), None)
        if area is None:
            continue
        scene = strips[0].id_data
        was = {s: s.select for s in scene.sequence_editor.strips_all}
        for s in was:
            s.select = s in strips
        try:
            with bpy.context.temp_override(window=window, area=area, scene=scene):
                bpy.ops.sequencer.connect()
        except RuntimeError as err:
            print("Plastron: couldn't connect clips:", err)
        for s, sel in was.items():
            s.select = sel
        return


def unlink(strip):
    if LINK in strip:
        del strip[LINK]


def linked(strip, among=None):
    """The other clips linked to strip (among: the clips to look in)."""
    uid = strip.get(LINK)
    if not uid:
        return []
    pool = among if among is not None else strip.id_data.sequence_editor.strips_all
    return [s for s in pool if s != strip and s.get(LINK) == uid]


def with_linked(strips, among=None):
    """strips plus everything linked to them (order kept, no repeats)."""
    out = list(strips)
    for strip in list(out):
        for other in linked(strip, among):
            if other not in out:
                out.append(other)
    return out


def editor(scene):
    if scene.sequence_editor is None:
        scene.sequence_editor_create()
    return scene.sequence_editor


def all_clips(scene):
    return list(editor(scene).strips_all) if scene.sequence_editor else []


def top_clips(scene):
    return list(scene.sequence_editor.strips) if scene.sequence_editor else []


def start(strip):
    return strip.left_handle


def end(strip):
    return strip.right_handle


def length(strip):
    return strip.right_handle - strip.left_handle


def on_channel(scene, channel):
    return sorted((s for s in top_clips(scene) if s.channel == channel), key=start)


def at(scene, channel, frame):
    """The clip on a channel covering frame, or None."""
    for strip in on_channel(scene, channel):
        if start(strip) <= frame < end(strip):
            return strip
    return None


def next_after(scene, channel, frame, exclude=None):
    """First clip on channel starting at or after frame."""
    for strip in on_channel(scene, channel):
        if strip != exclude and start(strip) >= frame:
            return strip
    return None


def previous_before(scene, channel, frame, exclude=None):
    """Last clip on channel ending at or before frame."""
    found = None
    for strip in on_channel(scene, channel):
        if strip != exclude and end(strip) <= frame:
            found = strip
    return found


def _set(strip, new_start, new_end, new_content=None):
    """Move/resize one strip to [new_start, new_end), never covering frames
    outside its old and new ranges on the way. new_content: where its content
    starts (content_start) at the end, for edits that slide what the clip
    shows (a ripple trim of its start), else it moves with the clip."""
    if new_content is not None:
        _set(strip, new_start, new_end)
        _slide(strip, new_content - strip.content_start)
        return
    old_start, old_end = start(strip), end(strip)
    if (old_start, old_end) == (new_start, new_end):
        return
    if new_start - old_start == new_end - old_end:
        # A move: the content moves with it (moving the handles instead would
        # trim a sound clip, putting different audio at the same place).
        strip.content_start += new_start - old_start
        return
    lo, hi = max(old_start, new_start), min(old_end, new_end)
    if lo < hi:
        # Ranges overlap: shrink to the shared part, then grow.
        if old_end != hi:
            strip.right_handle = hi
        if old_start != lo:
            strip.left_handle = lo
        if new_end != hi:
            strip.right_handle = new_end
        if new_start != lo:
            strip.left_handle = new_start
    else:
        # Disjoint: shrink to the new length, slide, then fix the end.
        keep = min(old_end - old_start, new_end - new_start)
        if old_end - old_start != keep:
            strip.right_handle = old_start + keep
        strip.content_start += new_start - old_start
        if end(strip) != new_end:
            strip.right_handle = new_end


def _slide(strip, d):
    """Slide the content by d frames under the clip, which stays where it is."""
    d = round(d)
    if not d:
        return
    s, e = start(strip), end(strip)
    if d < 0:
        # The content moves left (later content shows): trim the head first
        # (shrinks), then move back into the clip's own place.
        strip.left_handle = min(s - d, e - 1)
        strip.content_start += d
        strip.left_handle = s
        if end(strip) != e:
            strip.right_handle = e
    else:
        # The content moves right (earlier content shows): shrink the tail
        # first, move (the clip only covers its own place), then grow back.
        if e - d > s:
            strip.right_handle = e - d
            strip.content_start += d
            strip.left_handle = s
        else:
            strip.right_handle = s + 1
            strip.content_start += d
            strip.left_handle = s
        if end(strip) != e:
            strip.right_handle = e


def _free(scene, strip, new_start, new_end):
    """True if [new_start, new_end) on strip's channel touches no other
    strip's *current* position."""
    for other in on_channel(scene, strip.channel):
        if other != strip and start(other) < new_end and new_start < end(other):
            return False
    return True


def apply(scene, changes):
    """changes: {strip: (new_start, new_end)} or (new_start, new_end,
    content_start) to also slide what it shows. Applies them all without ever
    making two strips overlap on a channel (which would make Blender bump one
    to another channel)."""
    def differs(strip, target):
        if (start(strip), end(strip)) != tuple(target[:2]):
            return True
        return len(target) > 2 and target[2] is not None and abs(strip.content_start - target[2]) > 0.5

    pending = {s: tuple(t) for s, t in changes.items() if differs(s, t)}
    guard = len(pending) + 2
    while pending and guard:
        guard -= 1
        for strip, target in list(pending.items()):
            if _free(scene, strip, target[0], target[1]):
                _set(strip, *target)
                del pending[strip]
    for strip, target in pending.items():   # cyclic case: shrink, then grow
        _set(strip, target[0], target[0] + 1)
    for strip, target in pending.items():
        _set(strip, *target)
