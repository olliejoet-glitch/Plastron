"""The Script lane (Ollie): the script's lines as blocks on a "Script" track
that sits between the audio and video tracks. A block's start and end are
when its line happens; drag a block's edge to retime a line (ripple on the
lane). The blocks are text clips, fully see-through: never in a render.

Panels are their own things; each panel made from the script remembers its
block (plastron_panel.script_block). The script bar's "Panels follow script"
switch (scene.plastron_script_follow, off at first) makes them match: with
it on, every change to the blocks (an edge dragged, Retime, a line split or
added in the script) moves / resizes the panels too, and a new line gets a
new (blank) panel.

Script edits (script_panels watches the text) sync the blocks:
- a line split in two shares the old line's time (by reading time);
- lines added at the end get their reading time after the last block
  (the timeline gets longer);
- a removed line's block goes and later blocks close up.

Retime re-times every block from its reading time (+ the pause).
"""

import difflib
import uuid

import bpy

from ...timeline import clips, events, ripple, tracks
from ...timeline.placement import SCRIPT_BLOCK
from . import panels

LANE_NAME = "Script"
INDEX = "plastron_line_index"      # which script line (index in the text) a block is
FOLLOW = "plastron_script_follow"
_spans = {}                        # scene name -> blocks' (uid, start, end) last seen


# --- The lane and its blocks ------------------------------------------------------------------

def lane(scene, create=False):
    track = tracks.script_track(scene)
    if track is None and create:
        track = tracks.add(scene, 'SCRIPT', LANE_NAME, ripple=True)
    return track


def blocks(scene):
    """The line blocks, in time order."""
    track = lane(scene)
    if track is None:
        return []
    out = [s for s in clips.on_channel(scene, tracks.channel_of(scene, track)) if s.get(SCRIPT_BLOCK)]
    return sorted(out, key=clips.start)


def block_by_uid(scene, uid):
    return next((b for b in blocks(scene) if b[SCRIPT_BLOCK] == uid), None) if uid else None


def _label(text):
    return (text or "-")[:60]


def new_block(scene, start, end, line_index, text):
    track = lane(scene, create=True)
    sed = clips.editor(scene)
    strip = sed.strips.new_effect(_label(text), 'TEXT', tracks.channel_of(scene, track),
                                  frame_start=start, length=max(1, end - start))
    strip.text = text
    strip.blend_alpha = 0.0                  # (never seen in a render: Ollie: hidden for now)
    strip[SCRIPT_BLOCK] = uuid.uuid4().hex[:10]
    strip[INDEX] = line_index
    return strip


def _set_text(block, line_index, text):
    if block.text != text:
        block.text = text
        block.name = _label(text)
    block[INDEX] = line_index


def following(scene):
    return bool(getattr(scene, FOLLOW, False))


# --- Keeping the blocks in step with the script -------------------------------------------------

def _merge_inserts(ops, n_old):
    """difflib opcodes with each inserted line joined to the line it was
    split from (the one before; at the top, the one after), so it shares that
    line's time. Inserts after the last line stay inserts (the lane grows)."""
    ops = [list(o) for o in ops]
    out = []
    i = 0
    while i < len(ops):
        tag, a0, a1, b0, b1 = ops[i]
        if tag == 'insert' and a0 < n_old:
            if out and out[-1][0] in ('equal', 'replace'):
                prev = out[-1]
                if prev[0] == 'equal':
                    prev[2] -= 1
                    prev[4] -= 1
                    if prev[2] == prev[1]:
                        out.pop()
                    out.append(['replace', a0 - 1, a0, b0 - 1, b1])
                else:
                    prev[4] = b1
            elif i + 1 < len(ops) and ops[i + 1][0] in ('equal', 'replace'):
                nxt = ops[i + 1]
                if nxt[0] == 'equal':
                    out.append(['replace', nxt[1], nxt[1] + 1, b0, nxt[3] + 1])
                    nxt[1] += 1
                    nxt[3] += 1
                    if nxt[1] == nxt[2]:
                        i += 1
                else:
                    nxt[3] = b0
            else:
                out.append(['insert', a0, a1, b0, b1])
        else:
            out.append([tag, a0, a1, b0, b1])
        i += 1
    return out


def plan_sync(old, new, lengths_for):
    """Pure. old: [(start, end, text)] the blocks in order; new: [text] the
    script's lines. lengths_for(text) -> frames. Returns [(old index or None,
    start, end)] one per new line: equal lines keep their block; lines that
    replace others (a line split, reworded, or put in next to it) share
    their time by reading time; lines added after the last block get their
    reading time after it (the lane grows); removed lines' time closes up."""
    out = [None] * len(new)
    shift = 0
    ops = _merge_inserts(difflib.SequenceMatcher(None, [t for _s, _e, t in old], new,
                                                 autojunk=False).get_opcodes(), len(old))
    for tag, a0, a1, b0, b1 in ops:
        if tag == 'equal':
            for k in range(a1 - a0):
                s, e, _t = old[a0 + k]
                out[b0 + k] = (a0 + k, s + shift, e + shift)
        elif tag == 'delete':
            shift -= sum(old[k][1] - old[k][0] for k in range(a0, a1))
        elif tag == 'replace':
            s, e = old[a0][0] + shift, old[a1 - 1][1] + shift
            weights = [max(1, lengths_for(new[k])) for k in range(b0, b1)]
            total, span, at = sum(weights), max(e - s, b1 - b0), s
            # Which old block each line keeps: the one with its exact words,
            # else the rest in order (a split line's first part keeps the block).
            reuse, free = {}, list(range(a0, a1))
            for k in range(b0, b1):
                same = next((a for a in free if old[a][2] == new[k]), None)
                if same is not None:
                    reuse[k] = same
                    free.remove(same)
            for k in range(b0, b1):
                if k not in reuse and free:
                    reuse[k] = free.pop(0)
            for i, k in enumerate(range(b0, b1)):
                end = e if i == len(weights) - 1 else max(at + 1, at + round(span * weights[i] / total))
                out[k] = (reuse.get(k), at, end)
                at = end
            if b1 - b0 == 0:
                shift -= e - s
        elif tag == 'insert':                    # after the last block
            at = (old[-1][1] + shift) if old else 0
            for k in range(b0, b1):
                n = lengths_for(new[k])
                out[k] = (None, at, at + n)
                at += n
    return out


def sync_from_text(scene, text):
    """Blocks follow the script (see plan_sync). Returns True if anything changed."""
    from .script_panels import frames_for, script_lines
    lines = script_lines(text)
    current = blocks(scene)
    old = [(clips.start(b), clips.end(b), b.text) for b in current]
    if [t for _s, _e, t in old] == [line for _i, line in lines] and \
            all(b.get(INDEX) == i for b, (i, _l) in zip(current, lines)):
        return False
    if not current:
        return False                             # (no lane yet: Make Panels starts it)
    plan = plan_sync(old, [line for _i, line in lines], lambda t: frames_for(scene, t))
    used = {p[0] for p in plan if p[0] is not None}
    for i, b in enumerate(current):              # removed lines' blocks go
        if i not in used:
            events.emit("clip_removing", scene, strip=b)
            ripple.remove(scene, b)
    keep = {i: current[i] for i in used}
    clips.apply(scene, {keep[p[0]]: (p[1], p[2]) for p in plan if p[0] is not None})
    for (index, line), p in zip(lines, plan):
        if p[0] is not None:
            _set_text(keep[p[0]], index, line)
        else:
            new_block(scene, p[1], p[2], index, line)
    if following(scene):
        panels_follow(scene)
    else:
        _refresh_panel_text(scene)
    events.clips_changed(scene)
    return True


def lay_out(scene, lengths):
    """Blocks get new lengths (list, in order); the gaps between them stay."""
    current = blocks(scene)
    shift, changes = 0, {}
    for b, n in zip(current, lengths):
        s = clips.start(b) + shift
        changes[b] = (s, s + n)
        shift += n - clips.length(b)
    # (from the end when growing, so nothing overlaps on the way)
    clips.apply(scene, changes)
    if following(scene):
        panels_follow(scene)
    events.clips_changed(scene)


def retime(scene, pause_s=None, fit_panels=False):
    """Every block as long as its line takes (+ the pause); fit_panels: the
    panels linked to lines take their new spans too (the Retime button)."""
    from .script_panels import frames_for
    current = blocks(scene)
    lengths = [frames_for(scene, b.text, pause_s) for b in current]
    changed = sum(1 for b, n in zip(current, lengths) if n != clips.length(b))
    lay_out(scene, lengths)
    if fit_panels and not following(scene):         # (following: lay_out did it)
        _fit_for_retime(scene)
        events.clips_changed(scene)
    return changed


# --- Panels ------------------------------------------------------------------------------------

def panel_of(scene, block, among=None):
    uid = block[SCRIPT_BLOCK]
    return next((p for p in (among if among is not None else panels.all_panels(scene))
                 if p.plastron_panel.script_block == uid), None)


def _panel_track(scene):
    linked = [p for p in panels.all_panels(scene) if p.plastron_panel.script_block]
    if linked:
        return tracks.track_of_clip(scene, linked[0])
    active = tracks.active(scene)
    if active is not None and active.kind == 'VIDEO':
        return active
    videos = tracks.video_tracks(scene)
    return videos[-1] if videos else None


def _link(strip, block):
    strip.plastron_panel.script_block = block[SCRIPT_BLOCK]
    strip.plastron_panel.script_line = block.get(INDEX, -1)
    strip.plastron_panel.script_text = block.text[:500]


def _refresh_panel_text(scene):
    by_uid = {b[SCRIPT_BLOCK]: b for b in blocks(scene)}
    for p in panels.all_panels(scene):
        b = by_uid.get(p.plastron_panel.script_block)
        if b is not None and (p.plastron_panel.script_text != b.text[:500]
                              or p.plastron_panel.script_line != b.get(INDEX, -1)):
            _link(p, b)


def _free(scene, channel, start, end, ignore=()):
    return all(o in ignore or not (clips.start(o) < end and start < clips.end(o))
               for o in clips.on_channel(scene, channel))


def make_missing_panels(scene):
    """Every block without a panel gets one, where its line is (if that's free).
    Returns how many were made."""
    track = _panel_track(scene)
    if track is None:
        return 0
    ch = tracks.channel_of(scene, track)
    all_p = panels.all_panels(scene)
    made = 0
    for b in blocks(scene):
        if panel_of(scene, b, all_p) is not None:
            continue
        s, e = clips.start(b), clips.end(b)
        if not _free(scene, ch, s, e):
            continue
        p = panels.create(scene, ch, s, e - s)
        _link(p, b)
        all_p.append(p)
        made += 1
    return made


def panels_follow(scene):
    """Panels match their lines: each linked panel takes its block's span;
    blocks without a panel get a new (blank) one; a panel whose line was
    removed goes (if never drawn on) or moves to the end (kept)."""
    from .script_panels import _untouched_drawing
    current = blocks(scene)
    by_uid = {b[SCRIPT_BLOCK]: b for b in current}
    track = _panel_track(scene)
    if track is None:
        return
    ch = tracks.channel_of(scene, track)
    all_p = panels.all_panels(scene)
    orphans = [p for p in all_p if p.plastron_panel.script_block and p.plastron_panel.script_block not in by_uid]
    kept = []
    for p in orphans:
        p.plastron_panel.script_block = ""
        p.plastron_panel.script_line = -1
        if _untouched_drawing(p):
            events.emit("clip_removing", scene, strip=p)
            ripple.remove(scene, p)              # (never touch p again: Blender freed it; crash Ollie hit)
        else:
            kept.append(p)
    fit_linked_panels(scene, track)
    end_all = max([clips.end(s) for s in clips.top_clips(scene)] + [scene.frame_start])
    for p in kept:                               # drawn on: kept, at the very end
        n = clips.length(p)
        clips.apply(scene, {p: (end_all, end_all + n)})
        end_all += n
    make_missing_panels(scene)
    _refresh_panel_text(scene)


def _fit_for_retime(scene):
    """Retime with panels not following: linked panels fit their lines; a
    panel whose line was deleted would be in the way, so it's unlinked and
    goes to the end of the track (drawing kept, never deleted)."""
    track = _panel_track(scene)
    if track is None:
        return
    ch = tracks.channel_of(scene, track)
    by_uid = {b[SCRIPT_BLOCK] for b in blocks(scene)}
    orphans = [p for p in panels.all_panels(scene)
               if p.plastron_panel.script_block and p.plastron_panel.script_block not in by_uid]
    sed = clips.editor(scene)
    spare = max([x.channel for x in sed.strips_all] + [len(tracks.all_tracks(scene))]) + 1
    for p in orphans:
        p.plastron_panel.script_block = ""
        p.plastron_panel.script_line = -1
        p.channel = spare
        spare += 1
    fit_linked_panels(scene, track)
    end = max([clips.end(x) for x in clips.on_channel(scene, ch)] + [scene.frame_start])
    for p in sorted(orphans, key=clips.start):
        n = clips.length(p)
        clips.apply(scene, {p: (end, end + n)})
        p.channel = ch
        end += n


def fit_linked_panels(scene, track=None):
    """Each panel linked to a line takes its block's span (Retime does this
    even when panels don't follow the script: Ollie wanted the panels to fit
    the retimed lines). Nothing is made or removed here."""
    by_uid = {b[SCRIPT_BLOCK]: b for b in blocks(scene)}
    track = track or _panel_track(scene)
    if track is None:
        return
    ch = tracks.channel_of(scene, track)
    linked = {p.plastron_panel.script_block: p for p in panels.all_panels(scene)
              if p.plastron_panel.script_block in by_uid}
    sed = clips.editor(scene)
    spare = max([s.channel for s in sed.strips_all] + [len(tracks.all_tracks(scene))]) + 1
    moving = [p for uid, p in linked.items() if (clips.start(p), clips.end(p)) !=
              (clips.start(by_uid[uid]), clips.end(by_uid[uid])) or p.channel != ch]
    was = {p: (clips.start(p), clips.end(p), p.channel) for p in moving}
    for p in moving:                             # out of the way, then into place
        p.channel = spare
        spare += 1
    clips.apply(scene, {p: (clips.start(by_uid[p.plastron_panel.script_block]),
                            clips.end(by_uid[p.plastron_panel.script_block])) for p in moving})
    stuck = []
    for p in moving:
        b = by_uid[p.plastron_panel.script_block]
        if _free(scene, ch, clips.start(b), clips.end(b), ignore=(p,)):
            p.channel = ch
        else:
            stuck.append(p)
    for p in stuck:                              # (another clip is there: left where it was)
        s0, e0, c0 = was[p]
        clips.apply(scene, {p: (s0, e0)})
        if _free(scene, c0, s0, e0, ignore=(p,)):
            p.channel = c0


def _on_clips_changed(scene, **_info):
    """A block's edge dragged (or any lane change): panels follow, if on."""
    if scene is None or not hasattr(scene, "plastron_timeline"):
        return
    now = tuple((b[SCRIPT_BLOCK], clips.start(b), clips.end(b)) for b in blocks(scene))
    if _spans.get(scene.name) == now:
        return
    _spans[scene.name] = now
    if following(scene) and now:
        panels_follow(scene)


# --- Older projects: script panels become blocks where they are --------------------------------

def migrate(scene):
    """A project from before the Script lane: each panel made from the script
    gets a block at its own span (nothing moves), linked to it."""
    if blocks(scene):
        return
    old = [p for p in panels.all_panels(scene) if p.plastron_panel.script_line >= 0
           and not p.plastron_panel.script_block]
    if not old:
        return
    from .script_panels import script_lines, script_text
    text = script_text()
    lines = script_lines(text) if text else []
    old.sort(key=lambda p: (clips.start(p), p.channel))
    lane(scene, create=True)
    for k, p in enumerate(old):
        index, line = lines[k] if k < len(lines) else (p.plastron_panel.script_line, p.plastron_panel.script_text)
        b = new_block(scene, clips.start(p), clips.end(p), index, line)
        _link(p, b)
    events.clips_changed(scene)


def _on_load(scene):
    _spans.clear()
    if scene is None or not hasattr(scene, "plastron_timeline") or not tracks.all_tracks(scene):
        return
    lane(scene, create=True)                     # (always there, between audio and video)
    migrate(scene)


def _follow_changed(self, context):
    if following(context.scene):
        panels_follow(context.scene)
        events.clips_changed(context.scene)


def register():
    setattr(bpy.types.Scene, FOLLOW, bpy.props.BoolProperty(
        name="Panels Follow Script",
        description="On: panels match their script lines (dragging a line, Retime, splitting or adding "
                    "lines move / make panels too). Off: the panels are left as they are",
        default=False, update=_follow_changed))
    from ...core import handlers
    handlers.on_load(_on_load)
    events.listen("clips_changed", _on_clips_changed)
    events.listen("project_created", _on_load)


def unregister():
    delattr(bpy.types.Scene, FOLLOW)
