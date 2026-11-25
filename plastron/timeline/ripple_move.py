"""Ripple for whole-clip drags (Ollie: "I need ripple edits to work with
dragging whole clips too").

Blender's own drag-move (transform.seq_slide) just slots a dropped clip into
free space. Once a drag ends, on tracks with ripple on:

- the gap the clip left is closed (later clips on that track move up), and
- the clip is put in at the cut nearest where it was dropped: its middle
  over a clip's first half, it goes in before that clip, over the second
  half after it;
  the clips from there on move along to make room. Dropped into a gap it
  fits, it just stays there.

A video's sound (linked) goes with it, and so do the sounds of clips that
move up or along. Like resizing, every track with ripple on moves along
(Ollie: "just like with resizing a clip"; RIPPLE_MOVE_ALL_TRACKS in
config/timeline.py). Locked tracks never move. On a track without ripple
the clip goes exactly where it's dropped and cuts into what's there, like
Resolve's overwrite (OVERWRITE_ON_DROP in config/timeline.py).

plan() is pure (numbers in, numbers out); apply_drag() reads the drag that
just ended and applies the plan.
"""

import bpy

from . import clips, events, tracks


def plan(old, mains, followers, ripple, locked, links, fresh=(), all_tracks=None):
    """old: {key: (channel, start, end)} of every clip before the drag.
    mains: {key: (dest channel, intended start)} the dragged clips.
    followers: {key: (main key, channel)} clips riding with a main (its sound).
    ripple / locked: sets of channels. links: {key: [keys linked to it]}.
    fresh: new copies (Alt+drag): old = what they copy; they leave no gap.
    Returns {key: (channel, start, end)} for every clip that should change."""
    if all_tracks is None:
        from ..config import timeline as cfg
        all_tracks = cfg.RIPPLE_MOVE_ALL_TRACKS
    moving = set(mains) | set(followers)
    pos = {k: list(v) for k, v in old.items()}

    def shift_stay(channel, from_frame, delta):
        # Like resizing (Ollie): every ripple track moves, not just this one.
        chans = (set(ripple) | {channel}) if (all_tracks and channel in ripple) else {channel}
        done = set()
        for k, (ch, s, e) in old.items():
            if k in moving or ch not in chans or ch in locked or pos[k][1] < from_frame:
                continue
            pos[k][1] += delta
            pos[k][2] += delta
            done.add(k)
        for k in list(done):                       # their linked clips go along
            for other in links.get(k, ()):
                if other in moving or other in done or old[other][0] in locked:
                    continue
                pos[other][1] += delta
                pos[other][2] += delta
                done.add(other)

    # 1. Where each dropped block goes, judged on the timeline as it looked.
    blocks = {}
    for k, (dest, want) in mains.items():
        blocks.setdefault(dest, []).append((k, want))
    anchors = {}
    for dest, items in blocks.items():
        if dest not in ripple or dest in locked:
            continue
        bs = min(w for _k, w in items)
        be = max(w + old[k][2] - old[k][1] for k, w in items)
        others = sorted((old[k][1], old[k][2], k) for k in old if k not in moving and old[k][0] == dest)
        if not any(s < be and bs < e for s, e, _k in others):
            anchors[dest] = ('time', bs, be - bs)
            continue
        centre = (bs + be) / 2                     # (where the dragged clip's middle is)
        after_mid = [k for s, e, k in others if (s + e) / 2 > centre]
        if after_mid:
            anchors[dest] = ('before', after_mid[0], be - bs)
        else:
            anchors[dest] = ('after', others[-1][2], be - bs)

    # 2. Close the gaps they left (from the right, so frames stay valid).
    left = sorted(((old[k][0], old[k][1], old[k][2]) for k in mains if k not in fresh), key=lambda t: -t[1])
    for ch, s, e in left:
        if ch in ripple and ch not in locked:
            shift_stay(ch, e, -(e - s))
            a = anchors.get(ch)
            if a and a[0] == 'time' and a[1] >= e:
                anchors[ch] = ('time', a[1] - (e - s), a[2])

    # 3. Make room and put them in.
    out = {}
    for dest, items in blocks.items():
        a = anchors.get(dest)
        if a is None:
            continue                               # (no ripple there: Blender's result stays)
        kind, ref, length = a
        if kind == 'before':
            at = pos[ref][1]
        elif kind == 'after':
            at = pos[ref][2]
        else:
            at = ref
            stay = sorted((pos[k][1], pos[k][2]) for k in old if k not in moving and old[k][0] == dest)
            hit = [(s, e) for s, e in stay if s < at + length and at < e]
            if hit:                                 # (the gap closed up under it)
                s, e = hit[0]
                at = s if (s + e) / 2 > at + length / 2 else e
        overlap = any(pos[k][1] < at + length and at < pos[k][2]
                      for k in old if k not in moving and old[k][0] == dest)
        if overlap or kind != 'time':
            shift_stay(dest, at, length)
        bs = min(w for _k, w in items)
        for k, want in items:
            s = at + (want - bs)
            out[k] = (dest, s, s + old[k][2] - old[k][1])
    for k, (main, channel) in followers.items():
        if main in out:
            d = out[main][1] - old[main][1]
            out[k] = (channel, old[k][1] + d, old[k][2] + d)
    for k in old:
        if k not in moving and tuple(pos[k]) != tuple(old[k]):
            out[k] = tuple(pos[k])
    return out


_seen = [0]


def apply_drag(scene, last):
    """After Blender's drag-move ended: ripple it. last: {name: (channel,
    start, end)} before the drag. Returns True if anything changed."""
    from . import duplicate
    wm = bpy.context.window_manager
    op = wm.operators[-1] if wm and len(wm.operators) else None
    copies = dict(duplicate.pending["names"])
    is_drag = op is not None and op.bl_idname == "TRANSFORM_OT_seq_slide" and op.as_pointer() != _seen[0]
    if copies and (not is_drag or op.as_pointer() == duplicate.pending["op"]):
        duplicate.take_back(scene)                   # (an Alt+drag cancelled)
        return True
    duplicate.pending["names"] = {}
    if not is_drag:
        return False
    _seen[0] = op.as_pointer()
    dx, dy = (round(v) for v in op.properties.value)
    strips = {s.name: s for s in clips.top_clips(scene)}
    if copies and dx == 0 and dy == 0:              # (an Alt+click: no copy wanted)
        duplicate.pending["names"] = copies
        duplicate.take_back(scene)
        return True
    old = {n: v for n, v in last.items() if n in strips}
    old.update({n: v for n, v in copies.items() if n in strips})
    # The dragged clips: the selected ones (Blender's own drop may have
    # shuffled them right back where they were when dropped on other clips,
    # so "did it move" can't tell: Ollie's ripple drags "did nothing").
    moved = [s for n, s in strips.items() if n in old and (n in copies or s.select)
             and clips.length(s) == old[n][2] - old[n][1]]
    if not moved or (dx == 0 and dy == 0):
        return False
    names = {s.name for s in moved}
    index = clips.link_index(strips.values())     # (partners looked up once, not per clip)
    mains, followers = {}, {}
    for s in moved:
        partner = next((o for o in clips.linked_in(index, s)
                        if o.name in names and o.type != 'SOUND'), None)
        if s.type == 'SOUND' and partner is not None:
            followers[s.name] = (partner.name, s.channel)
        else:
            ch, st, _e = old[s.name]
            mains[s.name] = (ch + dy, st + dx)
    for n, (dest, _w) in mains.items():
        if tracks.track_of_channel(scene, dest) is None:
            return False                          # (placement puts it back)
    ripple = set(tracks.ripple_channels(scene))
    sed = clips.editor(scene)
    locked = {c for c in {v[0] for v in old.values()} if sed.channels[c].lock}
    links = {n: [o.name for o in clips.linked_in(index, s)] for n, s in strips.items()}
    fresh = set(copies) & set(old)
    out = plan(old, mains, followers, ripple, locked, links, fresh)
    # Tracks without ripple: the clip goes exactly where it was dropped and
    # cuts into what's there (Resolve's overwrite, Ollie).
    from ..config import timeline as cfg
    overwrite = []
    for n, (dest, want) in mains.items():
        if n in out or dest in ripple or dest in locked or not cfg.OVERWRITE_ON_DROP:
            continue
        length = old[n][2] - old[n][1]
        out[n] = (dest, want, want + length)
        overwrite.append(n)
    for n, (main, channel) in followers.items():
        if main in out and n not in out:
            d = out[main][1] - old[main][1]
            out[n] = (channel, old[n][1] + d, old[n][2] + d)
            if main in overwrite and channel not in locked and channel not in ripple:
                overwrite.append(n)
    if not out:
        return False
    # Moving clips off to spare channels first, then the others, then them in.
    going = [n for n in out if n in mains or n in followers]
    spare = max([s.channel for s in sed.strips_all] + [len(tracks.all_tracks(scene))]) + 1
    for i, n in enumerate(going):
        strips[n].channel = spare + i
    clips.apply(scene, {strips[n]: (s, e) for n, (_c, s, e) in out.items() if n not in going})
    for n in overwrite:
        clear(scene, *out[n], keep={strips[k] for k in going})
    clips.apply(scene, {strips[n]: (out[n][1], out[n][2]) for n in going})
    for n in going:
        strips[n].channel = out[n][0]
    return True


def clear(scene, channel, start, end, keep=()):
    """Make room on channel for start..end by cutting into what's there
    (Resolve's overwrite): clips inside go, ones overlapping an end are
    trimmed back, one around it all is split in two around the room."""
    from . import ripple
    for o in list(clips.on_channel(scene, channel)):
        if o in keep:
            continue
        s, e = clips.start(o), clips.end(o)
        if e <= start or s >= end:
            continue
        if s >= start and e <= end:
            events.emit("clip_removing", scene, strip=o)
            ripple.remove(scene, o)
        elif s < start and e > end:
            for right in ripple.split(scene, [o], end):
                if right.channel == channel:
                    clips.apply(scene, {o: (s, start)})
        elif s < start:
            clips.apply(scene, {o: (s, start)})
        else:
            if o.type in {'MOVIE', 'SOUND', 'SCENE'}:              # (its footage stays in place)
                clips.apply(scene, {o: (end, e, o.content_start)})
            else:                                                   # (a still / panel: just shorter)
                clips.apply(scene, {o: (end, e)})