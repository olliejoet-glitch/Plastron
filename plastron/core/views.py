"""Which 3D view is which: the canvas (painting; it has Plastron's options
bar, the tool header) or the 3D scene view (features/scene3d; no tool
header). Both look through the 3D Camera when the canvas is linked to it."""


def is_canvas(space):
    return space is not None and getattr(space, "type", "") == 'VIEW_3D' and \
        bool(getattr(space, "show_region_tool_header", False))


def is_scene_view(space):
    return space is not None and getattr(space, "type", "") == 'VIEW_3D' and not is_canvas(space)


def is_canvas_area(area):
    return area is not None and area.type == 'VIEW_3D' and is_canvas(area.spaces.active)


def through_camera(space):
    """Is this canvas looking through the 3D Camera?"""
    r3d = getattr(space, "region_3d", None)
    return is_canvas(space) and r3d is not None and r3d.view_perspective == 'CAMERA'
