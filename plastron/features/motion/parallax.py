"""3D parallax (Ollie: "emerging over a fallen tree to see a creature"):
each layer can sit at a depth, and the panel's camera move becomes a real
3D one. Nothing changes for layers at depth 1 (the picture plane).

    depth 1      the picture plane: moves exactly as the 2D camera does
    depth < 1    nearer: slides further and grows faster as the camera moves
    depth > 1    further: slides less, barely grows

The camera's zoom acts as moving the camera forward (zoom z puts the camera
1 - 1/z of the way to the picture plane), so a push-in makes the near tree
fill the frame while the creature behind grows slowly.

Maths (canvas px, from the middle): a layer at depth d, with the camera at
pan X and forward C, is drawn scaled by s = d / ((d - C) z) and shifted by
t = X (1 - 1 / (z (d - C))). Layers the camera would pass through are
held just in front of it.
"""

from ..storyboard import canvas_sync

NEAREST = 0.05     # a layer never gets nearer than this share of its depth


def effective_depth(layer, stack):
    """The layer's depth, or its group's, or 1 (the picture plane)."""
    l, guard = layer, 0
    while l is not None and guard < 64:
        if l.depth > 0:
            return l.depth
        l = stack.by_uid(l.parent_uid) if l.parent_uid else None
        guard += 1
    return 1.0


def para_for(depth, state, frame_w):
    """(tx, ty, scale) for a layer at depth with the camera in state."""
    if abs(depth - 1.0) < 1e-6:
        return (0.0, 0.0, 1.0)
    x, y, zoom, _rot = state
    forward = 1.0 - 1.0 / zoom
    dist = max(depth - forward, NEAREST * depth)
    scale = depth / (dist * zoom)
    k = 1.0 - 1.0 / (zoom * dist)
    return (x / 100 * frame_w * k, y / 100 * frame_w * k, scale)


def has_depth(layer, stack):
    return abs(effective_depth(layer, stack) - 1.0) > 1e-6


def stack_para(stack, state):
    """{uid: (tx, ty, scale)} for every layer of a painting."""
    fw = canvas_sync.frame_px(stack)[0]
    return {l.uid: para_for(effective_depth(l, stack), state, fw) for l in stack.layers}
