"""Timeline edits with per-track ripple.

The rules (from the brief):
- Ripple ON for the edited clip's track: the edit shifts everything after it
  on that track AND on every other track with ripple on (locked tracks never
  move).
- Ripple OFF: other clips stay put; clips leave gaps, or stop at the next clip.

Planning functions are pure: they take the clips' original positions and
return {strip: (start, end)}; clips.apply() then moves them safely. This lets
a mouse drag re-plan from the originals on every mouse move.
"""

from . import clips, events, tracks

MIN_LENGTH = 1


def snapshot(scene):
    """Current {strip: (start, end)} of every top-level clip."""
    return {s: (clips.start(s), clips.end(s)) for s in clips.top_clips(scene)}


def _ripples(scene, strip):
    track = tracks.track_of_clip(scene, strip)
    return bool(track and track.ripple)


def _locked(scene, strip):
    return clips.editor(scene).channels[strip.channel].lock


def _shift_after(scene, orig, frame, delta, changes, exclude=()):
    """Shift clips on ripple channels starting at/after frame by delta."""
    if not delta:
        return
    channels = tracks.ripple_channels(scene)
    for strip, (s, e) in orig.items():
        if strip in exclude or strip.channel not in channels or s < frame:
            continue
        cs, ce = changes.get(strip, (s, e))
        changes[strip] = (cs + delta, ce + delta)


def _neighbours(orig, strip):
    """(end of the previous clip, start of the next clip) on strip's channel."""
    s, e = orig[strip]
    prev_end, next_start = None, None
    for other, (os_, oe) in orig.items():
        if other == strip or other.channel != strip.channel:
            continue
        if oe <= s and (prev_end is None or oe > prev_end):
            prev_end = oe
        if os_ >= e and (next_start is None or os_ < next_start):
            next_start = os_
    return prev_end, next_start


def plan_trim(scene, orig, strip, side, frame):
    """Drag one edge ('LEFT' / 'RIGHT') of strip to frame."""
    if _locked(scene, strip):
        return {}
    s, e = orig[strip]
    changes = {}
    if _ripples(scene, strip):
        if side == 'RIGHT':
            new_end = max(frame, s + MIN_LENGTH)
            changes[strip] = (s, new_end)
            _shift_after(scene, orig, e, new_end - e, changes, exclude={strip})
        else:
            # Ripple trim of the start: the clip keeps its place, its length
            # changes by the drag, and everything after closes up / makes room.
            new_length = max(e - frame, MIN_LENGTH)
            delta = new_length - (e - s)
            changes[strip] = (s, s + new_length)
            _shift_after(scene, orig, e, delta, changes, exclude={strip})
    else:
        prev_end, next_start = _neighbours(orig, strip)
        if side == 'RIGHT':
            new_end = max(frame, s + MIN_LENGTH)
            if next_start is not None:
                new_end = min(new_end, next_start)
            changes[strip] = (s, new_end)
        else:
            new_start = min(frame, e - MIN_LENGTH)
            if prev_end is not None:
                new_start = max(new_start, prev_end)
            changes[strip] = (new_start, e)
    return changes


def trim(scene, strip, side, frame, orig=None):
    orig = orig or snapshot(scene)
    clips.apply(scene, plan_trim(scene, orig, strip, side, frame))
    events.clips_changed(scene)


def delete(scene, strips):
    """Delete clips; ripple tracks close the gap."""
    sed = clips.editor(scene)
    strips = [s for s in strips if not _locked(scene, s)]
    for strip in sorted(strips, key=clips.start, reverse=True):
        s, e = clips.start(strip), clips.end(strip)
        ripples = _ripples(scene, strip)
        events.emit("clip_removing", scene, strip=strip)
        sed.strips.remove(strip)
        if ripples:
            orig = snapshot(scene)
            changes = {}
            _shift_after(scene, orig, e, -(e - s), changes)
            clips.apply(scene, changes)
    events.clips_changed(scene)
    return len(strips)


def make_room(scene, channel, frame, length):
    """Where to put a new clip of `length` on channel at frame.

    If frame is inside a clip, the new clip goes right after it. On a ripple
    track later clips move along to make room; otherwise the new clip is
    shortened to fit the gap. Returns (start, length) or None if no room.
    """
    inside = clips.at(scene, channel, frame)
    start = clips.end(inside) if inside else frame
    nxt = clips.next_after(scene, channel, start)
    if nxt is None or clips.start(nxt) >= start + length:
        return start, length
    track = tracks.track_of_channel(scene, channel)
    if track and track.ripple:
        orig = snapshot(scene)
        changes = {}
        _shift_after(scene, orig, start, start + length - clips.start(nxt), changes)
        clips.apply(scene, changes)
        return start, length
    room = clips.start(nxt) - start
    return (start, room) if room >= MIN_LENGTH else None


def split(scene, strips, frame):
    """Cut each clip covering frame in two. Returns the new right halves."""
    new = []
    for strip in strips:
        if _locked(scene, strip) or not (clips.start(strip) < frame < clips.end(strip)):
            continue
        right = strip.split(frame=frame, split_method='SOFT')
        if right:
            events.emit("clip_split", scene, original=strip, new=right)
            new.append(right)
    if new:
        events.clips_changed(scene)
    return new
