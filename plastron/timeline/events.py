"""Timeline events, so features can react without the timeline knowing them.

    from ...timeline import events
    events.listen("clips_changed", my_function)    # my_function(scene, **info)

Events:
    clips_changed        clips were added, removed, moved or resized
    tracks_changed       tracks were added / reordered
    tracks_moved         info: moved {old index: new index} (a track was dragged)
    mix_changed          a volume or solo changed (audio mix must be rewritten)
    active_track_changed
    clip_split           info: original, new (the right half)
    clip_duplicated      info: original, new (an Alt+drag copy: make it its own)
    clip_removing        info: strip (about to be deleted)
"""

from contextlib import contextmanager

_listeners = {}
_held = None          # [(event, scene)] while batch() runs
HOLDABLE = {"clips_changed", "tracks_changed", "mix_changed"}


def listen(event, func):
    _listeners.setdefault(event, []).append(func)


def emit(event, scene, **info):
    if _held is not None and event in HOLDABLE:
        if (event, scene) not in _held:
            _held.append((event, scene))
        return
    for func in _listeners.get(event, ()):
        func(scene, **info)


def clips_changed(scene):
    emit("clips_changed", scene)


def tracks_changed(scene):
    emit("tracks_changed", scene)


def mix_changed(scene):
    emit("mix_changed", scene)


def active_track_changed(scene):
    emit("active_track_changed", scene)


@contextmanager
def batch():
    """Hold clips_changed / tracks_changed / mix_changed until the end, then
    send each once (many edits in a row, e.g. hundreds of um cuts: every
    listener ran after every cut, slower as the clips grew)."""
    global _held
    if _held is not None:
        yield
        return
    _held = []
    try:
        yield
    finally:
        held, _held = _held, None
        for event, scene in held:
            emit(event, scene)


def clear():
    _listeners.clear()
