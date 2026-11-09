"""Values view: the picture reduced to the value groups.

One compositor node group ("Plastron Values": brightness -> the groups'
greys, stepped) is used two ways: the canvas shows it live (the viewport
compositor, the scene's compositing node group while it's on), and the
video preview through a "Values" adjustment clip on its own track over the
whole project (a Compositor modifier). Off: both are taken away again, so
renders and exports never see it.
"""

import bpy

from ...config import values as cfg
from ...timeline import clips, events, tracks
from . import groups

CLIP_GROUP = "Plastron Values"
VIEW_GROUP = "Plastron Values (canvas)"
CLIP_KEY = "plastron_values_view"


def _ramp_into(tree, src, out_socket_owner):
    bw = tree.nodes.new("CompositorNodeRGBToBW")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.name = "Groups"
    ramp.color_ramp.interpolation = 'CONSTANT'
    tree.links.new(src, bw.inputs[0])
    tree.links.new(bw.outputs[0], ramp.inputs[0])
    tree.links.new(ramp.outputs[0], out_socket_owner)
    return ramp


def _set_ramp(ramp, gs):
    """Constant steps: below the first threshold the first grey, and so on
    (the ramp works on linear brightness)."""
    cr = ramp.color_ramp
    lin = groups.linear(gs)
    cuts = [0.0] + [float(c) for c in groups.linear(groups.thresholds(gs))]
    while len(cr.elements) < len(cuts):
        cr.elements.new(0.5)
    while len(cr.elements) > len(cuts):
        cr.elements.remove(cr.elements[-1])
    for el, pos, v in zip(cr.elements, cuts, lin):
        el.position = pos
        el.color = (float(v), float(v), float(v), 1.0)


def node_group(kind):
    """The Values node group: kind 'CLIP' (Group Input -> output) or 'VIEW'
    (Render Layers -> output, for the canvas)."""
    name = CLIP_GROUP if kind == 'CLIP' else VIEW_GROUP
    tree = bpy.data.node_groups.get(name)
    if tree is None:
        tree = bpy.data.node_groups.new(name, "CompositorNodeTree")
        tree.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
        out = tree.nodes.new("NodeGroupOutput")
        if kind == 'CLIP':
            tree.interface.new_socket("Image", in_out='INPUT', socket_type='NodeSocketColor')
            src = tree.nodes.new("NodeGroupInput").outputs[0]
        else:
            src = tree.nodes.new("CompositorNodeRLayers").outputs["Image"]
        _ramp_into(tree, src, out.inputs[0])
    _set_ramp(tree.nodes["Groups"], groups.get())
    return tree


def _canvas_spaces():
    from ...core.views import is_canvas
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else []):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D' and is_canvas(area.spaces.active):
                yield area, area.spaces.active


def values_clip(scene):
    return next((s for s in clips.top_clips(scene) if s.get(CLIP_KEY)), None)


def _values_track(scene):
    for t in tracks.all_tracks(scene):
        if t.kind == 'VIDEO' and tracks.name(scene, t) == cfg.VALUES_TRACK:
            return t
    return tracks.add(scene, 'VIDEO', track_name=cfg.VALUES_TRACK)


def show(scene, on):
    """Values view on / off (canvas + preview)."""
    if on:
        scene.compositing_node_group = node_group('VIEW')
        for area, space in _canvas_spaces():
            space.shading.use_compositor = 'ALWAYS'
            area.tag_redraw()
        clip = values_clip(scene)
        if clip is None:
            ch = tracks.channel_of(scene, _values_track(scene))
            end = max([clips.end(s) for s in clips.top_clips(scene)] + [scene.frame_start + 1])
            clip = clips.editor(scene).strips.new_effect("Values View", 'ADJUSTMENT', ch, scene.frame_start,
                                                         length=end - scene.frame_start)
            clip[CLIP_KEY] = True
            mod = clip.modifiers.new("Plastron Values", 'COMPOSITOR')
            mod.node_group = node_group('CLIP')
            clip.lock = True
    else:
        if scene.compositing_node_group is not None and scene.compositing_node_group.name == VIEW_GROUP:
            scene.compositing_node_group = None
        for area, space in _canvas_spaces():
            space.shading.use_compositor = 'DISABLED'
            area.tag_redraw()
        clip = values_clip(scene)
        if clip is not None:
            clips.editor(scene).strips.remove(clip)
            track = next((t for t in tracks.all_tracks(scene) if tracks.name(scene, t) == cfg.VALUES_TRACK), None)
            if track is not None and not clips.on_channel(scene, tracks.channel_of(scene, track)):
                pass                                            # (the empty track stays; harmless)
    events.clips_changed(scene)


def _follow(scene, **_info):
    clip = values_clip(scene)
    if clip is None:
        return
    others = [s for s in clips.top_clips(scene) if s != clip]
    if others:
        start = min(scene.frame_start, min(clips.start(s) for s in others))
        end = max(clips.end(s) for s in others)
        if (clips.start(clip), clips.end(clip)) != (start, end):
            clip.lock = False
            clips._set(clip, start, end)
            clip.lock = True


def _groups_changed(gs):
    for kind, name in (('CLIP', CLIP_GROUP), ('VIEW', VIEW_GROUP)):
        if bpy.data.node_groups.get(name) is not None:
            node_group(kind)


def register():
    events.listen("clips_changed", _follow)
    groups.CHANGED.append(_groups_changed)


def unregister():
    if _groups_changed in groups.CHANGED:
        groups.CHANGED.remove(_groups_changed)
