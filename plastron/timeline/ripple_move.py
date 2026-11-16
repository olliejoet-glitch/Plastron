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
move up or along. Only the tracks the clip leaves / lands on ripple (moving
a panel doesn't shift the voice). Locked tracks never move. Tracks without
ripple keep Blender's own behaviour.

plan() is pure (numbers in, numbers out); apply_drag() reads the drag that
just ended and applies the plan.
"""

import bpy

from . import clips, tracks


def plan(old, mains, followers, ripple, locked, links, fresh=()):
    """old: {key: (channel, start, end)} of every clip before the drag.
    mains: {key: (dest channel, intended start)} the dragged clips.
    followers: {key: (main key, channel)} clips riding with a main (its sound).
    ripple / locked: sets of channels. links: {key: [keys linked to it]}.
    fresh: new copies (Alt+drag): old = what they copy; they leave no gap.
    Returns {key: (channel, start, end)} for every clip that should change."""
    moving = set(mains) | set(followers)
    pos = {k: list(v) for k, v in old.items()}

    def shift_stay(channel, from_frame, delta):
        done = set()
        for k, (ch, s, e) in old.items():
            if k in moving or ch != channel or ch in locked or pos[k][1] < from_frame:
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
    moved = [s for n, s in strips.items() if n in old
             and (n in copies or old[n] != (s.channel, clips.start(s), clips.end(s)))
             and clips.length(s) == old[n][2] - old[n][1]]
    if not moved or (dx == 0 and dy == 0):
        return False
    names = {s.name for s in moved}
    mains, followers = {}, {}
    for s in moved:
        partner = next((o for o in clips.linked(s, list(strips.values()))
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
    links = {n: [o.name for o in clips.linked(s, list(strips.values()))] for n, s in strips.items()}
    fresh = set(copies) & set(old)
    out = plan(old, mains, followers, ripple, locked, links, fresh)
    for n in fresh:                       # copies on a track without ripple: where they were dropped
        if n in mains and n not in out:
            dest, want = mains[n]
            length = old[n][2] - old[n][1]
            if strips[n].channel != dest and all(
                    not (clips.start(o) < want + length and want < clips.end(o))
                    for o in clips.on_channel(scene, dest) if o != strips[n]):
                out[n] = (dest, want, want + length)
    for n, (main, channel) in followers.items():
        if n in fresh and main in out and n not in out:
            d = out[main][1] - old[main][1]
            out[n] = (channel, old[n][1] + d, old[n][2] + d)
    if not out:
        return False
    # Moving clips off to spare channels first, then the others, then them in.
    going = [n for n in out if n in mains or n in followers]
    spare = max([s.channel for s in sed.strips_all] + [len(tracks.all_tracks(scene))]) + 1
    for i, n in enumerate(going):
        strips[n].channel = spare + i
    clips.apply(scene, {strips[n]: (s, e) for n, (_c, s, e) in out.items() if n not in going})
    clips.apply(scene, {strips[n]: (out[n][1], out[n][2]) for n in going})
    for n in going:
        strips[n].channel = out[n][0]
    return True
