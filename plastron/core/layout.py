"""Builds each mode's workspace from config/layout.py.

Used by tools/build_startup.py (needs a real window, so it runs under the
UI, not in background mode). The result is saved into plastron/startup.blend.
"""

import hashlib
import math
import os

import bpy
from mathutils import Euler

from ..config import layout as cfg
from .util import set_path

HASH_KEY = "plastron_build"

# Files whose content shapes startup.blend. If any changes, rebuild.
_SOURCES = [
    "config/layout.py", "config/project_defaults.py",
    "core/layout.py", "core/project.py",
]


def build_hash():
    root = os.path.dirname(os.path.dirname(__file__))
    digest = hashlib.sha256()
    for rel in _SOURCES:
        with open(os.path.join(root, rel), "rb") as f:
            digest.update(f.read().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]


def _override(window, area):
    return bpy.context.temp_override(window=window, screen=window.screen, area=area,
                                     region=area.regions[-1])


def reduce_to_one_area(window):
    """Close areas until the screen has a single one."""
    screen = window.screen
    while len(screen.areas) > 1:
        smallest = min(screen.areas, key=lambda a: a.width * a.height)
        with _override(window, smallest):
            bpy.ops.screen.area_close()
    return screen.areas[0]


def _split(window, area, direction, first_fraction, out):
    """Generator: split area; after the UI refresh, out = [first, second]
    = (top, bottom) or (left, right). Geometry is only valid after a refresh."""
    before = set(a.as_pointer() for a in window.screen.areas)
    # Blender's factor is the fraction given to the bottom / left part.
    factor = (1.0 - first_fraction) if direction == 'HORIZONTAL' else first_fraction
    with _override(window, area):
        bpy.ops.screen.area_split(direction=direction, factor=factor)
    yield
    new = next(a for a in window.screen.areas if a.as_pointer() not in before)
    key = (lambda a: -a.y) if direction == 'HORIZONTAL' else (lambda a: a.x)
    out[:] = sorted((area, new), key=key)


def _build_tree(window, area, node, placed):
    """Generator: divide area according to a rows/columns node."""
    if "area" in node:
        placed[node["area"]] = area
        return
    kind = "rows" if "rows" in node else "columns"
    children = node[kind]
    direction = 'HORIZONTAL' if kind == "rows" else 'VERTICAL'
    remaining = sum(c["size"] for c in children)
    for i, child in enumerate(children):
        if i == len(children) - 1:
            yield from _build_tree(window, area, child, placed)
            break
        pair = []
        yield from _split(window, area, direction, child["size"] / remaining, pair)
        remaining -= child["size"]
        first, area = pair
        yield from _build_tree(window, first, child, placed)


def configure_area(area, spec):
    """Set an area's visible parts and settings.

    Call only after the UI has refreshed following set_editor_types();
    touching a brand-new editor's regions straight away crashes Blender.
    """
    space = area.spaces.active
    flags = {
        "header": "show_region_header", "footer": "show_region_footer",
        "tool_header": "show_region_tool_header", "toolbar": "show_region_toolbar",
        "sidebar": "show_region_ui", "channels": "show_region_channels",
        "hud": "show_region_hud",
    }
    for key, attr in flags.items():
        if key in spec and hasattr(space, attr):
            setattr(space, attr, spec[key])
    for path, value in spec.get("settings", {}).items():
        if path == "view_type":          # (set_view_types, a refresh earlier)
            continue
        set_path(space, path, value)
    if area.type == 'VIEW_3D':
        if spec.get("scene_view"):
            _setup_scene_view(space)
        else:
            _setup_canvas_view(space)
    if area.type == 'PROPERTIES':
        _properties_as_panel_holder(space)
    if area.type == 'FILE_BROWSER' and spec.get("media_browser"):
        setup_media_browser(space)


def _properties_as_panel_holder(space):
    """Hide every Properties tab except the chosen one: the area then just
    holds Plastron's panels (Blender's own are hidden by hidden_ui)."""
    for prop in space.bl_rna.properties:
        name = prop.identifier
        if name.startswith("show_properties_"):
            setattr(space, name, name == "show_properties_" + space.context.lower())


MEDIA_FILTERS = ("use_filter_movie", "use_filter_sound", "use_filter_image", "use_filter_folder")


def setup_media_browser(space):
    """The media bin: thumbnails of video, sound and pictures (and folders)."""
    params = space.params
    if params is None:              # (made when the area first draws)
        return False
    params.display_type = 'THUMBNAIL'
    params.use_filter = True
    for prop in params.bl_rna.properties:
        name = prop.identifier
        if name.startswith("use_filter_") and prop.type == 'BOOLEAN' and name != "use_filter":
            if name in ("use_filter_blender", "use_filter_backup", "use_filter_blendid"):
                setattr(params, name, False)
            else:
                setattr(params, name, name in MEDIA_FILTERS)
    return True


def use_project_scene(window):
    """Blender 5 timelines show the workspace's sequencer scene: use the project's."""
    for workspace in bpy.data.workspaces:
        if workspace.sequencer_scene != window.scene:
            workspace.sequencer_scene = window.scene


def widen_channel_columns(window, placed):
    """Generator: drag each timeline's track-header column edge to its configured
    width (Blender has no setting for it). Needs --enable-event-simulate.
    Retries from a few positions around the edge until the width changes."""
    def channels(area):
        return next((r for r in area.regions if r.type == 'CHANNELS'), None)

    for name, area in placed.items():
        want = cfg.AREAS[name].get("channels_width")
        if not want or channels(area) is None:
            continue
        want *= bpy.context.preferences.system.ui_scale
        for offset in (-1, -3, 0, -2, 1):
            region = channels(area)
            if abs(region.width - want) < 4:
                break
            x = region.x + region.width + offset
            y = region.y + region.height // 2
            target = int(x + want - region.width)
            # Hover first (Blender must notice the mouse is over the edge), then drag.
            for dy in (-2, 0):
                window.event_simulate('MOUSEMOVE', 'NOTHING', x=x, y=y + dy)
                yield
            window.event_simulate('LEFTMOUSE', 'PRESS', x=x, y=y)
            yield
            for i in range(1, 6):
                window.event_simulate('MOUSEMOVE', 'NOTHING', x=int(x + (target - x) * i / 5), y=y)
                yield
            window.event_simulate('LEFTMOUSE', 'RELEASE', x=target, y=y)
            yield
            yield
        print("Plastron layout: track header column", channels(area).width, "px (wanted", int(want), ")")


def hide_navigation_bars(window, placed):
    """Properties editors: hide the tab column (needs a UI refresh first)."""
    for area in placed.values():
        if area.type != 'PROPERTIES':
            continue
        nav = next((r for r in area.regions if r.type == 'NAVIGATION_BAR'), None)
        if nav and nav.width > 1:
            with bpy.context.temp_override(window=window, area=area, region=nav):
                bpy.ops.screen.region_toggle(region_type='NAVIGATION_BAR')


def _setup_scene_view(space):
    from ..config import scene3d
    r3d = space.region_3d
    r3d.view_perspective = 'PERSP'
    r3d.view_rotation = Euler([math.radians(a) for a in scene3d.VIEW_ANGLES]).to_quaternion()
    r3d.view_location = scene3d.ORIGIN
    r3d.view_distance = scene3d.VIEW_DISTANCE
    r3d.lock_rotation = False


def _setup_canvas_view(space):
    r3d = space.region_3d
    r3d.view_perspective = 'ORTHO'
    r3d.view_rotation = Euler((math.radians(90), 0.0, 0.0)).to_quaternion()  # front
    r3d.view_location = (0.0, 0.0, 0.0)
    r3d.view_distance = 12.0
    r3d.lock_rotation = True


def split_mode(window, mode_name, placed):
    """Generator, phase 1: divide the window's screen into the mode's areas.

    Fills placed = {area name: area} and sets each area's editor type.
    Yields wherever Blender must refresh its UI before continuing.
    """
    first = reduce_to_one_area(window)
    yield
    yield from _build_tree(window, first, cfg.MODES[mode_name], placed)
    for name, area in placed.items():
        area.type = cfg.AREAS[name]["editor"]
    window.screen.show_statusbar = cfg.WINDOW["status_bar"]


def set_view_types(placed):
    """Phase 1b: a Sequencer area's view (timeline / preview). Like an editor
    type, it needs a UI refresh before the area's other settings."""
    for name, area in placed.items():
        view_type = cfg.AREAS[name].get("settings", {}).get("view_type")
        if view_type and area.spaces.active.view_type != view_type:
            area.spaces.active.view_type = view_type


def configure_mode(placed):
    """Phase 2 (after a UI refresh): configure each area."""
    for name, area in placed.items():
        configure_area(area, cfg.AREAS[name])
        if cfg.AREAS[name].get("tool"):
            set_tool(bpy.context.window, area, cfg.AREAS[name]["tool"])


def set_tool(window, area, tool_id):
    """An area's active tool (saved with its workspace)."""
    region = next((r for r in area.regions if r.type == 'PREVIEW'), None) or \
        next((r for r in area.regions if r.type == 'WINDOW'), None)
    try:
        with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
            bpy.ops.wm.tool_set_by_id(name=tool_id, space_type=area.type)
    except (RuntimeError, TypeError) as err:
        print("Plastron layout: couldn't set the tool", tool_id, err)
