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
    if not _connected(strips):      # (a split's right halves are: Blender connects them itself)
        _connect(strips)


def _connected(strips):
    """True if each of these clips is already connected to all the others."""
    names = {s.name for s in strips}
    for s in strips:
        have = {c.name for c in s.connections}
        if not (names - {s.name}) <= have:
            return False
    return True


def _connect(strips, op="connect"):
    import bpy
    if len(strips) < (2 if op == "connect" else 1):
        return
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        area = next((a for a in window.screen.areas if a.type == 'SEQUENCE_EDITOR'), None)
        if area is None:
            continue
        scene = strips[0].id_data
        was = [s for s in scene.sequence_editor.strips_all if s.select]
        for s in was:                       # (only clips whose selection changes are set:
            s.select = False                #  setting all of them, per link, was slow)
        for s in strips:
            s.select = True
        try:
            with bpy.context.temp_override(window=window, area=area, scene=scene):
                getattr(bpy.ops.sequencer, op)()
        except RuntimeError as err:
            print(f"Plastron: couldn't {op} clips:", err)
        for s in strips:
            s.select = False
        for s in was:
            s.select = True
        return


def unlink(strip):
    if LINK in strip:
        del strip[LINK]


def unlink_all(strips):
    """Unlink these clips from each other and everything (Blender's
    connection too): they move / trim / cut on their own again."""
    for strip in strips:
        unlink(strip)
    _connect(list(strips), op="disconnect")


def linked(strip, among=None):
    """The other clips linked to strip (among: the clips to look in)."""
    uid = strip.get(LINK)
    if not uid:
        return []
    pool = among if among is not None else strip.id_data.sequence_editor.strips_all
    return [s for s in pool if s != strip and s.get(LINK) == uid]


def link_index(pool):
    """{link id: [clips]} of pool, for looking up many clips' partners at
    once (linked() searches the whole pool each time: slow per clip with
    hundreds of clips)."""
    out = {}
    for s in pool:
        uid = s.get(LINK)
        if uid:
            out.setdefault(uid, []).append(s)
    return out


def linked_in(index, strip):
    """linked(), from a link_index."""
    uid = strip.get(LINK)
    return [o for o in index.get(uid, ()) if o != strip] if uid else []


def with_linked(strips, among=None):
    """strips plus everything linked to them (order kept, no repeats)."""
    out = list(strips)
    if not out:
        return out
    pool = among if among is not None else out[0].id_data.sequence_editor.strips_all
    by_link = {}                     # (one pass: hundreds of um clips at once)
    for s in pool:
        uid = s.get(LINK)
        if uid:
            by_link.setdefault(uid, []).append(s)
    seen = set(out)
    for strip in list(out):
        uid = strip.get(LINK)
        for other in by_link.get(uid, ()) if uid else ():
            if other not in seen:
                seen.add(other)
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
    _shift_keys(strip, new_start - old_start)
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


def _shift_keys(strip, delta):
    """A clip's keys follow its start, as when Blender moves it itself (each
    clip owns its animation: its card, its camera, its fades...)."""
    if not delta:
        return
    scene = strip.id_data
    ad = scene.animation_data
    action = ad.action if ad else None
    if action is None:
        return
    base = 'sequence_editor.strips_all["{}"].'.format(strip.name.replace("\\", "\\\\").replace('"', '\\"'))
    if hasattr(action, "fcurves"):
        curves = list(action.fcurves)
    else:
        curves = [fc for layer in action.layers for st in layer.strips
                  for bag in getattr(st, "channelbags", []) for fc in bag.fcurves]
    for fc in curves:
        if fc.data_path.startswith(base):
            for k in fc.keyframe_points:
                k.co[0] += delta
                k.handle_left[0] += delta
                k.handle_right[0] += delta
            fc.update()


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
    if not pending:
        return
    # Where every clip is now, per channel, kept in step as clips move, in
    # start order: clips on a channel never overlap, so a free-check only
    # looks at the neighbours around the spot (was: every clip on the
    # channel, for every clip moved: slow with hundreds).
    import bisect
    rows = {}                      # channel -> ([starts], [(start, end, strip)])
    for s in top_clips(scene):
        rows.setdefault(s.channel, []).append((start(s), end(s), s))
    seen = {s for items in rows.values() for _a, _b, s in items}
    for s in pending:
        if s not in seen:
            rows.setdefault(s.channel, []).append((start(s), end(s), s))
    for ch, items in list(rows.items()):
        items.sort(key=lambda t: t[0])
        rows[ch] = ([t[0] for t in items], items)

    def free(strip, a, b):
        starts, items = rows[strip.channel]
        i = max(0, bisect.bisect_right(starts, a) - 1)
        while i < len(items) and items[i][0] < b:
            s0, e0, other = items[i]
            if e0 > a and other != strip:
                return False
            i += 1
        return True

    def place(strip, target):
        starts, items = rows[strip.channel]
        old = start(strip)
        i = bisect.bisect_left(starts, old)
        while i < len(items) and items[i][0] == old and items[i][2] != strip:
            i += 1
        if i >= len(items) or items[i][2] != strip:     # (not where expected: look everywhere)
            i = next((k for k, t in enumerate(items) if t[2] == strip), len(items))
        if i < len(items):
            del starts[i]
            del items[i]
        _set(strip, *target)
        a, b = start(strip), end(strip)
        j = bisect.bisect_left(starts, a)
        starts.insert(j, a)
        items.insert(j, (a, b, strip))

    # Leftward moves earliest first, rightward latest first: most settle in one pass.
    order = sorted(pending, key=lambda s: (pending[s][0] - start(s) > 0,
                                           start(s) if pending[s][0] <= start(s) else -start(s)))
    pending = {s: pending[s] for s in order}
    guard = len(pending) + 2
    while pending and guard:
        guard -= 1
        for strip, target in list(pending.items()):
            if free(strip, target[0], target[1]):
                place(strip, target)
                del pending[strip]
    for strip, target in pending.items():   # cyclic case: shrink, then grow
        _set(strip, target[0], target[0] + 1)
    for strip, target in pending.items():
        _set(strip, *target)
