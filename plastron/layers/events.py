"""Layer stack events: listeners hear when a stack's look changed (e.g. the
storyboard refreshes a panel's cached image)."""

_listeners = []


def listen(func):
    """func(material) is called after any change to that material's stack."""
    _listeners.append(func)


def changed(mat):
    for func in _listeners:
        func(mat)


def clear():
    _listeners.clear()
