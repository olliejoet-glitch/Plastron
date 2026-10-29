"""Shadow Data (§50, removed in 0.19.2 - §51): 0.19.1 added a "CaraPainter Shadow Data" Geometry
Nodes modifier to creatures so the terminator band could reach past the true terminator. The
band now works like a colour ramp on the light value, which needs no geometry data; this only
takes the modifier (and its node group) back out of files that have it.
"""
import bpy

GROUP = "CaraPainter Shadow Data"
MOD = "CaraPainter Shadow Data"


def cleanup(sc):
    for ob in sc.objects:
        if ob.type == 'MESH':
            mod = ob.modifiers.get(MOD)
            if mod is not None:
                ob.modifiers.remove(mod)
    g = bpy.data.node_groups.get(GROUP)
    if g is not None and g.users == 0:
        bpy.data.node_groups.remove(g)


def remove(mat):
    """Detach: objects wearing this material lose the old modifier."""
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and any(s.material == mat for s in ob.material_slots):
            mod = ob.modifiers.get(MOD)
            if mod is not None:
                ob.modifiers.remove(mod)
