"""Panel images (timeline thumbnails) show the panel where it starts: the
camera's start frame (rotation left out) and every layer at its start
position."""

from ..storyboard import panel_cache, panels
from . import camera, layer_motion


def view(strip, stack):
    """panel_cache hook: (crop, layer offsets) for a panel with motion."""
    moving = [l for l in stack.layers if layer_motion.has_motion(l)]
    if not moving and not camera.moves(strip):
        return None
    m = strip.plastron_motion
    start = camera.blend(camera.as_tuple(m.start), camera.as_tuple(m.end),
                         camera.dot_graph.evaluate(m.curve, 0.0))
    crop = camera.crop(start, panel_cache.frame_crop(stack))
    offsets = {l.uid: layer_motion.position(l, 0.0) for l in stack.layers}
    from . import parallax
    para = parallax.stack_para(stack, start) if camera.moves(strip) else None
    return crop, offsets, para


def camera_changed(state):
    """A camera position changed (PLASTRON_PG_camera_state): re-make that panel's image."""
    scene = state.id_data
    if not hasattr(scene, "sequence_editor") or scene.sequence_editor is None:
        return
    ptr = state.as_pointer()
    for strip in panels.all_panels(scene):
        m = strip.plastron_motion
        if ptr in (m.start.as_pointer(), m.end.as_pointer(), m.as_pointer()):
            panel_cache.request(strip.plastron_panel.material)
            from . import canvas_fit
            canvas_fit.request(strip)       # the painting grows if the move needs it
            return


def register():
    panel_cache.VIEW_PROVIDERS.append(view)


def unregister():
    if view in panel_cache.VIEW_PROVIDERS:
        panel_cache.VIEW_PROVIDERS.remove(view)
