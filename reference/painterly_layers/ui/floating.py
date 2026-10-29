"""Floating CaraPainter windows (§57): any section of the sidebar in its own window, to move
anywhere (another monitor too) and close at will. Saved with the file like any Blender window.

Blender can't float panels over a viewport, so a floating section is a small separate window
holding one Image Editor (no image: nearly free to redraw) whose sidebar shows copies of our
panels. The window's screen is tagged screen["pl_float"] = section; the copies only show there.
"""
import bpy

from . import panel

FLOAT_KEY = "pl_float"
SPACE = 'IMAGE_EDITOR'

# section id, label, root panel, include the root's child panels
SECTIONS = (
    ("ALL", "Everything", "PL_PT_layers", True),
    ("LAYERS", "Layers", "PL_PT_layers", False),
    ("LIGHT", "Light", None, False),
    ("LAYER", "Layer Settings", "PL_PT_layer_props", True),
    ("MASKS", "Masks", "PL_PT_masks", True),
    ("BRUSHES", "Brushes", "PL_PT_brushes", True),
    ("OUTLINE", "Outline", "PL_PT_outline", True),
    ("BLEND_IF", "Blend If", "PL_PT_blend_if", True),
    ("SELECTION", "Selection", "PL_PT_selection", True),
    ("LIGHTING", "Lighting & Bake", "PL_PT_lighting", True),
    ("STACK", "Stack Settings", "PL_PT_stack_settings", True),
)
SECTION_OF_PANEL = {root: sid for sid, _l, root, kids in SECTIONS if root and sid not in ("ALL", "LAYERS")}
SECTION_OF_PANEL["PL_PT_layers"] = "LAYERS"
SECTION_ITEMS = [(sid, label, f"Open {label} in its own window") for sid, label, _r, _k in SECTIONS]


def _pid(c):
    return getattr(c, "bl_idname", c.__name__)


def _panels():
    return {_pid(c): c for c in panel.classes if issubclass(c, bpy.types.Panel)
            and getattr(c, "bl_region_type", "") == 'UI'}


def _own(cls, name):
    """The function `name` defined by the panel class itself (not bpy.types.Panel's)."""
    for k in cls.__mro__:
        if k is bpy.types.Panel:
            return None
        if name in k.__dict__:
            return k.__dict__[name]
    return None


def is_float(context, section=None):
    sc = getattr(context, "screen", None)
    tag = sc.get(FLOAT_KEY) if sc is not None else None
    return tag is not None if section is None else tag == section


def _copy(orig, idname, parent, section, top):
    ns = {"bl_space_type": SPACE, "bl_region_type": 'UI', "bl_category": "CaraPainter",
          "bl_label": orig.bl_label, "bl_idname": idname, "bl_order": -100}
    if parent:
        ns["bl_parent_id"] = parent
    opts = set(getattr(orig, "bl_options", set()))
    if top:
        opts.discard('DEFAULT_CLOSED')   # (the window shows this section: start it open)
    ns["bl_options"] = opts
    own_poll = _own(orig, "poll")

    def poll(cls, context):   # (Blender checks the argument count: no default-arg captures)
        if not is_float(context, section):
            return False
        return own_poll.__get__(None, orig)(context) if own_poll is not None else True
    ns["poll"] = classmethod(poll)
    for name in ("draw", "draw_header"):
        fn = _own(orig, name)
        if fn is not None:
            ns[name] = fn
    return type(idname, (bpy.types.Panel,), ns)


def _light_draw(self, context):
    panel.draw_light_sphere(self.layout, context)


def _build_classes():
    by_id = _panels()
    kids = {}
    for c in by_id.values():
        p = getattr(c, "bl_parent_id", "")
        if p:
            kids.setdefault(p, []).append(c)
    out = []

    def add(orig, section, parent, top, recurse):
        idname = f"PL_PT_float_{section.lower()}_{_pid(orig)[6:]}"
        out.append(_copy(orig, idname, parent, section, top))
        if recurse:
            for k in kids.get(_pid(orig), ()):
                add(k, section, idname, False, True)

    for sid, _label, root, recurse in SECTIONS:
        if root is None:
            out.append(type("PL_PT_float_light", (bpy.types.Panel,), {
                "bl_space_type": SPACE, "bl_region_type": 'UI', "bl_category": "CaraPainter",
                "bl_label": "Light", "bl_idname": "PL_PT_float_light", "bl_order": -100,
                "poll": classmethod(lambda cls, context: is_float(context, "LIGHT")
                                    and panel.get_stack(context)[1] is not None),
                "draw": _light_draw}))
        else:
            add(by_id[root], sid, None, True, recurse)
    return out


# --- opening a window ---------------------------------------------------------------------------
def _area_size(a):
    return a.width * a.height


def open_float(context, section):
    """Open `section` in a new small window. Returns the new window or None."""
    wm = context.window_manager
    win = context.window
    screen = win.screen
    src = max((a for a in screen.areas if a.type == 'VIEW_3D'), key=_area_size, default=None) \
        or max(screen.areas, key=_area_size)
    before_windows = {w.as_pointer() for w in wm.windows}
    before_areas = {a.as_pointer() for a in screen.areas}
    # a narrow strip at the right of the viewport, sent off into its own window, then closed here
    with context.temp_override(window=win, screen=screen, area=src):
        bpy.ops.screen.area_split(direction='VERTICAL', factor=0.8)
    new_area = next((a for a in screen.areas if a.as_pointer() not in before_areas), None)
    if new_area is None:
        return None
    # (the split may hand back either half: send the narrow one off)
    strip = min((new_area, src), key=lambda a: a.width)
    old_type = strip.type
    strip.type = SPACE
    with context.temp_override(window=win, screen=screen, area=strip):
        bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
    with context.temp_override(window=win, screen=screen, area=strip):
        try:
            bpy.ops.screen.area_close()
        except RuntimeError:   # (can't close it: put it back as it was)
            strip.type = old_type
    new = next((w for w in wm.windows if w.as_pointer() not in before_windows), None)
    if new is None:
        return None
    new.screen[FLOAT_KEY] = section
    for a in new.screen.areas:
        if a.type == SPACE:
            sp = a.spaces.active
            sp.image = None
            sp.show_region_ui = True
            sp.show_region_toolbar = False
            sp.show_region_tool_header = False
            sp.show_region_header = False
            sp.show_gizmo = False
    _pending_tab.append(new.screen.name)
    if not bpy.app.timers.is_registered(_select_tab):
        bpy.app.timers.register(_select_tab, first_interval=0.05)
    return new


_pending_tab = []


def _select_tab(tries=[0]):
    """Show the CaraPainter tab in new floating windows' sidebars (only possible once drawn)."""
    wm = bpy.context.window_manager
    left = []
    for name in _pending_tab:
        done = False
        for win in wm.windows:
            if win.screen is None or win.screen.name != name:
                continue
            for a in win.screen.areas:
                if a.type == SPACE:   # (the tool header comes back with the first draw)
                    a.spaces.active.show_region_tool_header = False
                for r in a.regions:
                    if r.type == 'UI':
                        try:
                            r.active_panel_category = "CaraPainter"
                            done = r.active_panel_category == "CaraPainter"
                        except (TypeError, AttributeError):
                            pass
                        r.tag_redraw()
        if not done:
            left.append(name)
    _pending_tab[:] = left
    tries[0] = 0 if not left else tries[0] + 1
    if left and tries[0] < 40:
        return 0.05
    _pending_tab.clear()
    tries[0] = 0
    return None


class PL_OT_float_panel(bpy.types.Operator):
    bl_idname = "pl.float_panel"
    bl_label = "Open in Floating Window"
    bl_description = ("Open this CaraPainter section in its own small window: move it anywhere "
                      "(another monitor too), close it when you're done. It's saved with the file")
    bl_options = {'INTERNAL'}

    section: bpy.props.EnumProperty(items=SECTION_ITEMS, name="Section", options={'SKIP_SAVE'})

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        if open_float(context, self.section) is None:
            self.report({'ERROR'}, "Could not open a window here")
            return {'CANCELLED'}
        return {'FINISHED'}


class PL_MT_float(bpy.types.Menu):
    bl_label = "Floating Windows"
    bl_idname = "PL_MT_float"

    def draw(self, context):
        lay = self.layout
        lay.operator_context = 'EXEC_DEFAULT'
        for sid, label, _r, _k in SECTIONS:
            lay.operator("pl.float_panel", text=label, icon='WINDOW').section = sid


# --- the pop-out button on the sidebar panels ---------------------------------------------------
def _float_button(section):
    def draw_header_preset(self, context):
        if context.area is not None and context.area.type == 'VIEW_3D':
            op = self.layout.operator("pl.float_panel", text="", icon='WINDOW', emboss=False)
            op.section = section
    return draw_header_preset


def _layers_preset(self, context):
    if context.area is not None and context.area.type == 'VIEW_3D':
        self.layout.menu("PL_MT_float", text="", icon='WINDOW')


for _cls in panel.classes:
    _sid = SECTION_OF_PANEL.get(_pid(_cls))
    if _sid == "LAYERS":
        _cls.draw_header_preset = _layers_preset
    elif _sid:
        _cls.draw_header_preset = _float_button(_sid)


# --- keeping the floating windows current -------------------------------------------------------
_dirty = [False]


def _on_depsgraph(scene, depsgraph):
    _dirty[0] = True


def float_regions():
    wm = bpy.context.window_manager
    for win in (wm.windows if wm else ()):
        if win.screen is None or win.screen.get(FLOAT_KEY) is None:
            continue
        for a in win.screen.areas:
            for r in a.regions:
                if r.type == 'UI':
                    yield r


def redraw_floats(force=False):
    """Repaint the floating windows after any change (they don't listen to the 3D view's updates)."""
    if not (force or _dirty[0]):
        return
    _dirty[0] = False
    for r in float_regions():
        r.tag_redraw()


classes = (PL_OT_float_panel, PL_MT_float)
_panel_classes = []


def register():
    for c in classes:
        bpy.utils.register_class(c)
    _panel_classes[:] = _build_classes()
    for c in _panel_classes:
        bpy.utils.register_class(c)
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    for c in reversed(_panel_classes):
        bpy.utils.unregister_class(c)
    _panel_classes.clear()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
