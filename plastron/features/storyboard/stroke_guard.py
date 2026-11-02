"""Is a brush stroke running? Background jobs (the painting growing to fit
the camera, the canvas following a moved layer) must not swap images or
change the canvas sheet under a stroke: that crashed Blender (Ollie).

A stroke starts with a press on the canvas (motion's camera box sees every
press first and calls began()); it ends when Blender reports the painted
image (panel_cache's stroke hook calls ended()). A forgotten start times out.
"""

import time

TIMEOUT = 60.0
_state = {"since": None}


def began():
    _state["since"] = time.monotonic()


def ended():
    _state["since"] = None


def busy():
    since = _state["since"]
    if since is None:
        return False
    if time.monotonic() - since > TIMEOUT:
        _state["since"] = None
        return False
    return True
