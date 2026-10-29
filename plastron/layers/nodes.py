"""Tiny node-graph builder so compiler code reads like maths.

Copied unchanged from Ollie's CaraPainter (compiler/nodes.py)."""
import bpy

EPS = 1e-6


def iface(tree, io, name, typ, default=None, lo=None, hi=None):
    s = tree.interface.new_socket(name, in_out=io, socket_type=typ)
    if default is not None:
        s.default_value = default
    if lo is not None:
        s.min_value, s.max_value = lo, hi
    return s


def new_tree(name):
    """Fresh (or emptied) shader node group with this exact name."""
    tree = bpy.data.node_groups.get(name)
    if tree is None:
        tree = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    tree.nodes.clear()
    tree.interface.clear()
    return tree


class NotSynced(Exception):
    """A new group node's sockets weren't synced yet: Blender's node-tree update can't run while
    its material preview thread is updating (§55). The rebuild is abandoned and retried."""


class NB:
    def __init__(self, tree):
        self.tree = tree
        self.links = tree.links
        self._n = 0

    # -- basics
    def node(self, typ, name=None, label=None, **props):
        n = self.tree.nodes.new(typ)
        if name:
            n.name = name
        if label:
            n.label = label
        for k, v in props.items():
            setattr(n, k, v)
        n.location = ((self._n % 12) * 200, -(self._n // 12) * 300)
        self._n += 1
        return n

    def feed(self, dst, src):
        if src is None:
            return
        if isinstance(src, bpy.types.NodeSocket):
            self.links.new(src, dst)
            return
        dv = dst.default_value
        if hasattr(dv, "__len__"):
            n = len(dv)
            if isinstance(src, (int, float)):
                src = (float(src),) * n if n == 3 else (float(src),) * 3 + (1.0,)
            elif len(src) == 3 and n == 4:
                src = (*src, 1.0)
        dst.default_value = src

    def group(self, tree, name=None, **inputs):
        n = self.node('ShaderNodeGroup', name=name, node_tree=tree)
        for k, v in inputs.items():
            sock = n.inputs.get(k)
            if sock is None:
                raise NotSynced(f"{tree.name}: {k}")
            self.feed(sock, v)
        return n

    # -- scalar maths
    def m(self, op, a, b=None, c=None, clamp=False):
        n = self.node('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, s in enumerate((a, b, c)):
            self.feed(n.inputs[i], s)
        return n.outputs[0]

    def add(self, a, b): return self.m('ADD', a, b)
    def sub(self, a, b): return self.m('SUBTRACT', a, b)
    def mul(self, a, b): return self.m('MULTIPLY', a, b)
    def div(self, a, b): return self.m('DIVIDE', a, self.m('MAXIMUM', b, EPS))
    def mn(self, a, b): return self.m('MINIMUM', a, b)
    def mx(self, a, b): return self.m('MAXIMUM', a, b)
    def clamp(self, a): return self.m('ADD', a, 0.0, clamp=True)
    def lt(self, a, b): return self.m('LESS_THAN', a, b)
    def gt(self, a, b): return self.m('GREATER_THAN', a, b)

    def sel(self, cond, t, f):
        """cond (0/1) ? t : f  (floats)."""
        return self.mixf(cond, f, t)

    # -- vector maths (colours link into vectors implicitly)
    def v(self, op, a, b=None, c=None, scale=None):
        n = self.node('ShaderNodeVectorMath', operation=op)
        for i, s in enumerate((a, b, c)):
            self.feed(n.inputs[i], s)
        if scale is not None:
            self.feed(n.inputs['Scale'], scale)
        return n.outputs['Value'] if op in ('DOT_PRODUCT', 'LENGTH', 'DISTANCE') else n.outputs['Vector']

    def vscale(self, a, s): return self.v('SCALE', a, scale=s)
    def dot(self, a, b): return self.v('DOT_PRODUCT', a, b)

    def sel_v(self, cond, t, f):
        return self.mixc(cond, f, t)

    def min3(self, c):
        x, y, z = self.sepxyz(c)
        return self.mn(self.mn(x, y), z)

    def max3(self, c):
        x, y, z = self.sepxyz(c)
        return self.mx(self.mx(x, y), z)

    # -- mixing / (de)composition
    def mixf(self, fac, a, b):
        n = self.node('ShaderNodeMix', data_type='FLOAT', clamp_factor=True)
        self.feed(n.inputs[0], fac)
        self.feed(n.inputs[2], a)
        self.feed(n.inputs[3], b)
        return n.outputs[0]

    def mixc(self, fac, a, b, blend='MIX'):
        n = self.node('ShaderNodeMix', data_type='RGBA', blend_type=blend, clamp_factor=True)
        self.feed(n.inputs[0], fac)
        self.feed(n.inputs[6], a)
        self.feed(n.inputs[7], b)
        return n.outputs[2]

    def mixv(self, fac, a, b):
        n = self.node('ShaderNodeMix', data_type='VECTOR', clamp_factor=True)
        self.feed(n.inputs[0], fac)
        self.feed(n.inputs[4], a)
        self.feed(n.inputs[5], b)
        return n.outputs[1]

    def sep(self, c):
        n = self.node('ShaderNodeSeparateColor')
        self.feed(n.inputs[0], c)
        return tuple(n.outputs[:3])

    def comb(self, r, g, b):
        n = self.node('ShaderNodeCombineColor')
        for i, s in enumerate((r, g, b)):
            self.feed(n.inputs[i], s)
        return n.outputs[0]

    def sepxyz(self, v):
        n = self.node('ShaderNodeSeparateXYZ')
        self.feed(n.inputs[0], v)
        return tuple(n.outputs[:3])

    def per_channel(self, fn, *colours):
        """Apply scalar fn(nb, *channel_sockets) to each RGB channel."""
        chans = [self.sep(c) for c in colours]
        return self.comb(*[fn(self, *[ch[i] for ch in chans]) for i in range(3)])
