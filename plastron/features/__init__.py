"""Features, each in its own package with register()/unregister().

To add a feature: create its package and add its name here.
To remove one: delete its name. Order = registration order.
"""

import importlib

FEATURES = [
    "storyboard",
]

_loaded = []


def register():
    for name in FEATURES:
        module = importlib.import_module(f".{name}", __name__)
        module.register()
        _loaded.append(module)


def unregister():
    for module in reversed(_loaded):
        module.unregister()
    _loaded.clear()
