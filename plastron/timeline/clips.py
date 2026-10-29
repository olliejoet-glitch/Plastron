"""Low-level clip helpers on top of Blender's sequencer strips.

Uses Blender 5.2's timing names (left_handle / right_handle / content_start;
the frame_final_* names are deprecated). End frames are exclusive.

Blender pushes a strip to another channel if a change makes it overlap a
neighbour even for a moment, so all repositioning goes through apply(),
which orders the changes so nothing ever overlaps.
"""


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


def _set(strip, new_start, new_end):
    """Move/resize one strip to [new_start, new_end), never covering frames
    outside its old and new ranges on the way."""
    old_start, old_end = start(strip), end(strip)
    if (old_start, old_end) == (new_start, new_end):
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


def _free(scene, strip, new_start, new_end):
    """True if [new_start, new_end) on strip's channel touches no other
    strip's *current* position."""
    for other in on_channel(scene, strip.channel):
        if other != strip and start(other) < new_end and new_start < end(other):
            return False
    return True


def apply(scene, changes):
    """changes: {strip: (new_start, new_end)}. Applies them all without ever
    making two strips overlap on a channel (which would make Blender bump one
    to another channel)."""
    pending = {s: se for s, se in changes.items() if (start(s), end(s)) != tuple(se)}
    guard = len(pending) + 2
    while pending and guard:
        guard -= 1
        for strip, (s, e) in list(pending.items()):
            if _free(scene, strip, s, e):
                _set(strip, s, e)
                del pending[strip]
    for strip, (s, e) in pending.items():   # cyclic case: shrink, then grow
        _set(strip, s, s + 1)
    for strip, (s, e) in pending.items():
        _set(strip, s, e)
