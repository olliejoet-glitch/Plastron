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


def content_snapshot(scene):
    """Current {strip: content_start}: where each clip's content sits."""
    return {s: s.content_start for s in clips.top_clips(scene)}


def resolve(plan, content):
    """A plan's content slides (start, end, slide) -> absolute content_start."""
    return {s: (t[0], t[1], content[s] + t[2]) if len(t) > 2 else t for s, t in plan.items()}


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
    moved = []
    for strip, (s, e) in orig.items():
        if strip in exclude or strip.channel not in channels or s < frame:
            continue
        cs, ce = changes.get(strip, (s, e))
        changes[strip] = (cs + delta, ce + delta)
        moved.append(strip)
    # A moved clip's linked clips (its sound on a track without ripple) go along.
    for strip in moved:
        for other in clips.linked(strip, orig):
            if other in changes or other in exclude or _locked(scene, other):
                continue
            s, e = orig[other]
            changes[other] = (s + delta, e + delta)


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


def plan_trim(scene, orig, strip, side, frame, content=None):
    """Drag one edge ('LEFT' / 'RIGHT') of strip to frame. A ripple trim of
    the start keeps the clip in place and slides what it shows: its entry is
    (start, end, slide), resolve() turns slide into a content position.
    content (content_snapshot) lets a video / sound clip's start go back only
    as far as its media does."""
    if _locked(scene, strip):
        return {}
    s, e = orig[strip]
    changes = {}
    # Linked clips with the same span (a video and its sound) trim with it.
    partners = [o for o in clips.linked(strip, orig) if orig[o] == (s, e) and not _locked(scene, o)]
    exclude = {strip, *partners}
    if _ripples(scene, strip):
        if side == 'RIGHT':
            new_end = max(frame, s + MIN_LENGTH)
            changes[strip] = (s, new_end)
            _shift_after(scene, orig, e, new_end - e, changes, exclude=exclude)
        else:
            # Ripple trim of the start: the clip keeps its place, its length
            # changes by the drag, and everything after closes up / makes room.
            new_length = max(e - frame, MIN_LENGTH)
            if content is not None and strip.type in {'MOVIE', 'SOUND'}:
                new_length = min(new_length, e - content[strip])   # (no media before its start)
            delta = new_length - (e - s)
            # The cut-off start of the media is gone: what showed at e - new_length now shows at s.
            changes[strip] = (s, s + new_length, -((e - new_length) - s))
            _shift_after(scene, orig, e, delta, changes, exclude=exclude)
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
    for other in partners:
        changes[other] = changes[strip]
    return changes


def trim(scene, strip, side, frame, orig=None):
    orig = orig or snapshot(scene)
    content = content_snapshot(scene)
    clips.apply(scene, resolve(plan_trim(scene, orig, strip, side, frame, content), content))
    events.clips_changed(scene)


def delete(scene, strips):
    """Delete clips; ripple tracks close the gap."""
    sed = clips.editor(scene)
    strips = [s for s in clips.with_linked(strips, clips.top_clips(scene)) if not _locked(scene, s)]
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
    """Make room for a new clip of `length` starting exactly at frame.

    A clip the playhead is inside is cut short at frame (a clip starting
    exactly at frame stays whole: the new clip goes in front of it). On a
    ripple track later clips move along just enough to fit the new clip;
    otherwise it shrinks to fit the gap. Returns (start, length), or None
    if there's no room (no ripple and a clip starts right at frame).
    """
    inside = clips.at(scene, channel, frame)
    cut = inside if inside is not None and clips.start(inside) < frame else None
    nxt = clips.next_after(scene, channel, frame, exclude=cut)
    track = tracks.track_of_channel(scene, channel)
    ripples = bool(track and track.ripple)
    if nxt is not None and clips.start(nxt) < frame + length and not ripples:
        length = clips.start(nxt) - frame
        if length < MIN_LENGTH:
            return None
    if cut is not None:
        clips.apply(scene, {cut: (clips.start(cut), frame)})
    if ripples and nxt is not None and clips.start(nxt) < frame + length:
        orig = snapshot(scene)
        changes = {}
        _shift_after(scene, orig, frame, frame + length - clips.start(nxt), changes)
        clips.apply(scene, changes)
    return frame, length


def split(scene, strips, frame):
    """Cut each clip covering frame in two (linked clips too). Returns the
    new right halves."""
    before = set(clips.top_clips(scene))
    pairs = []
    for strip in clips.with_linked(strips, before):
        if _locked(scene, strip) or not (clips.start(strip) < frame < clips.end(strip)):
            continue                     # (Blender may have cut it already: connected to one cut)
        right = strip.split(frame=frame, split_method='SOFT')
        if right:
            pairs.append((strip, right))
    # Blender cuts a clip's connected clips with it: those right halves too.
    rights = {r for _o, r in pairs}
    for new in clips.top_clips(scene):
        if new in before or new in rights:
            continue
        original = next((o for o in before if o.channel == new.channel and clips.end(o) == frame), None)
        if original is not None:
            pairs.append((original, new))
    relink = {}            # the right halves of linked clips are linked to each other
    new = []
    for original, right in pairs:
        if right.get(clips.LINK):
            relink.setdefault(right[clips.LINK], []).append(right)
        events.emit("clip_split", scene, original=original, new=right)
        new.append(right)
    for group in relink.values():
        if len(group) > 1:
            clips.link(group)
        else:
            clips.unlink(group[0])
    if new:
        events.clips_changed(scene)
    return new


# --- Speed ----------------------------------------------------------------------

def _speed_of(strip):
    return float(strip.get("plastron_speed", 1.0))


def _timeline_override():
    import bpy
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR' and area.spaces.active.view_type == 'SEQUENCER':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                return dict(window=window, area=area, region=region)
    return None


def _retime(scene, strip, speed):
    """Blender's own speed change (its retiming): strip plays at speed; it
    keeps its start."""
    import bpy
    where = _timeline_override()
    if where is None:
        return False
    s = clips.start(strip)
    sed = clips.editor(scene)
    was = {x: x.select for x in sed.strips_all}
    active = sed.active_strip
    for x in was:
        x.select = x == strip
    sed.active_strip = strip
    try:
        with bpy.context.temp_override(scene=scene, **where):
            bpy.ops.sequencer.retiming_segment_speed_set(speed=speed * 100.0)
    except RuntimeError as err:
        print("Plastron: couldn't change the speed:", err)
        return False
    finally:
        for x, sel in was.items():
            x.select = sel
        sed.active_strip = active
    if clips.start(strip) != s:                  # (keep its start: a pure move)
        strip.content_start += s - clips.start(strip)
    if hasattr(strip, "pitch_correction"):
        strip.pitch_correction = True            # (a voice keeps its pitch)
    return True


def set_speed(scene, strip, speed):
    """Change a clip's speed (1 = normal, 2 = twice as fast); its linked clips
    too. The clip keeps its start; ripple tracks close up / make room, else
    a slower clip stops at the next one."""
    speed = max(0.05, float(speed))
    group = [s for s in clips.with_linked([strip], clips.top_clips(scene)) if not _locked(scene, s)]
    if not group or abs(speed - _speed_of(strip)) < 1e-6:
        return False
    ratio = speed / _speed_of(strip)
    orig = snapshot(scene)
    s, e = orig[strip]
    wanted = s + max(MIN_LENGTH, round((e - s) / ratio))
    plan = plan_trim(scene, orig, strip, 'RIGHT', wanted)
    allowed_end = plan.get(strip, (s, e))[1]
    others = {o: t for o, t in plan.items() if o not in group}
    clips.apply(scene, others)                       # make room / close up first
    spare = max([x.channel for x in clips.editor(scene).strips_all] + [len(tracks.all_tracks(scene))]) + 1
    home = {}
    for i, g in enumerate(group):                    # retimed out of the way, then back
        home[g] = g.channel
        g.channel = spare + i
        _retime(scene, g, speed)
        if clips.end(g) > allowed_end:
            g.right_handle = allowed_end
        g["plastron_speed"] = speed
    for g in group:
        g.channel = home[g]
    events.clips_changed(scene)
    return True
