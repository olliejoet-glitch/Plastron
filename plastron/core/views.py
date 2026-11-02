"""Which 3D view is which: the canvas (painting) or the 3D scene view
(features/scene3d). The scene view is the one with its own camera
(use_local_camera); the canvas never has one."""


def is_scene_view(space):
    return space is not None and getattr(space, "type", "") == 'VIEW_3D' and \
        bool(getattr(space, "use_local_camera", False))


def is_canvas(space):
    return space is not None and getattr(space, "type", "") == 'VIEW_3D' and not is_scene_view(space)


def is_canvas_area(area):
    return area is not None and area.type == 'VIEW_3D' and is_canvas(area.spaces.active)
