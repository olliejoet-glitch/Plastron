"""Timeline events, so features can react without the timeline knowing them.

    from ...timeline import events
    events.listen("clips_changed", my_function)    # my_function(scene, **info)

Events:
    clips_changed        clips were added, removed, moved or resized
    tracks_changed       tracks were added / reordered
    mix_changed          a volume or solo changed (audio mix must be rewritten)
    active_track_changed
    clip_split           info: original, new (the right half)
    clip_removing        info: strip (about to be deleted)
"""

_listeners = {}


def listen(event, func):
    _listeners.setdefault(event, []).append(func)


def emit(event, scene, **info):
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


def clear():
    _listeners.clear()
