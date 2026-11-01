"""The dot graph (shared component): a curve with points you add and drag.

Easing for camera and layer motion uses it now; audio pitch / volume and
clip speed will use the same graph later. Each graph is a Float Curve node in
one hidden node group (".PLASTRON Graphs"), named by its id, so it's saved
with the project, undoable, and drawn with Blender's own curve editor (click
to add a point, drag to move it).

    draw(layout, graph_id)       the editor
    evaluate(graph_id, t)        value at t (0..1); straight line if missing
    set_points(graph_id, pts)    e.g. from a preset; pts = [(x, y), ...]
    points(graph_id)             the current points
"""

import uuid

import bpy

TREE = ".PLASTRON Graphs"


def _tree(create=True):
    tree = bpy.data.node_groups.get(TREE)
    if tree is None and create:
        tree = bpy.data.node_groups.new(TREE, 'ShaderNodeTree')
        tree.use_fake_user = True
    return tree


def node(graph_id, create=True):
    """The Float Curve node holding a graph (made straight 0->1 if new)."""
    tree = _tree(create)
    if tree is None:
        return None
    n = tree.nodes.get(graph_id)
    if n is None and create:
        n = tree.nodes.new('ShaderNodeFloatCurve')
        n.name = n.label = graph_id
        mapping = n.mapping
        mapping.use_clip = False             # overshoot goes above 1
        mapping.clip_min_y, mapping.clip_max_y = -1.0, 2.0
        mapping.initialize()
    return n


def evaluate(graph_id, t):
    t = min(1.0, max(0.0, t))
    n = node(graph_id, create=False) if graph_id else None
    if n is None:
        return t
    return n.mapping.evaluate(n.mapping.curves[0], t)


def points(graph_id):
    n = node(graph_id, create=False)
    if n is None:
        return [(0.0, 0.0), (1.0, 1.0)]
    return [tuple(p.location) for p in n.mapping.curves[0].points]


def set_points(graph_id, pts, handle='AUTO'):
    """Replace a graph's points (at least two). handle: one handle type for
    every point ('AUTO', 'AUTO_CLAMPED', 'VECTOR') or one per point."""
    n = node(graph_id)
    curve = n.mapping.curves[0]
    pts = sorted((float(x), float(y)) for x, y in pts)
    while len(curve.points) > 2:
        curve.points.remove(curve.points[1])
    curve.points[0].location = pts[0]
    curve.points[-1].location = pts[-1]
    for x, y in pts[1:-1]:
        curve.points.new(x, y)
    kinds = [handle] * len(curve.points) if isinstance(handle, str) else list(handle)
    for p, kind in zip(curve.points, kinds):
        p.handle_type = kind
    n.mapping.update()


def remove(graph_id):
    tree = _tree(False)
    if tree is not None and graph_id in tree.nodes:
        tree.nodes.remove(tree.nodes[graph_id])


def new_id(prefix="graph"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def copy(src_id, dst_id=None):
    """Copy a graph (points and handle types); returns the copy's id."""
    dst_id = dst_id or new_id(src_id.split("_", 1)[0])
    src = node(src_id, create=False)
    if src is None:
        return dst_id
    set_points(dst_id, points(src_id))
    dst = node(dst_id).mapping.curves[0]
    for a, b in zip(src.mapping.curves[0].points, dst.points):
        b.handle_type = a.handle_type
    node(dst_id).mapping.update()
    return dst_id


def handles(graph_id):
    n = node(graph_id, create=False)
    return [p.handle_type for p in n.mapping.curves[0].points] if n else ['AUTO', 'AUTO']


def draw(layout, graph_id):
    """The editor: Blender's curve widget (add / drag points)."""
    n = node(graph_id, create=False)
    if n is None:
        layout.label(text="(straight line)")
        return
    layout.template_curve_mapping(n, "mapping", type='NONE')
