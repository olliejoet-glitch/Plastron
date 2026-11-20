"""Search the script (Ollie: "I need a search function in the script").

The script bar has a search field: as you type, every match is tinted and
the first from where you are is selected and scrolled into view; the arrows
next to it step to the next / previous match (wrapping round), with "n/m"
showing which one you're on. Ctrl+F over the script opens the same field in
a box, ready to type. Case doesn't matter. Look: SCRIPT_SEARCH in
config/voice.py.
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ...config import project_defaults as defaults, voice as cfg
from ...core.theme import _color

PROP = "plastron_script_find"
_handles = []


def matches(lines, query):
    """Pure: [(line, start, end)] of every case-blind match of query in
    lines (strings), in order (matches don't overlap)."""
    q = query.lower()
    if not q:
        return []
    out = []
    for i, body in enumerate(lines):
        low = body.lower()
        at = low.find(q)
        while at >= 0:
            out.append((i, at, at + len(q)))
            at = low.find(q, at + len(q))
    return out


def _text():
    return bpy.data.texts.get(defaults.SCRIPT_TEXT_NAME)


def _found(text, query):
    return matches([line.body for line in text.lines], query) if text else []


def _selection(text):
    """((line, char), (line, char)) of the selection, first end first."""
    a = (text.current_line_index, text.current_character)
    b = (text.select_end_line_index, text.select_end_character)
    return (a, b) if a <= b else (b, a)


def current(text, found):
    """Index of the match that is selected now, else None."""
    lo, hi = _selection(text)
    for k, (i, s, e) in enumerate(found):
        if (i, s) == lo and (i, e) == hi:
            return k
    return None


def pick(found, where, step):
    """Pure: which match to go to. step 0: the first at / after where (the
    selection's start); 1 / -1: the next / previous after / before it
    (wrapping round). None when nothing matches."""
    if not found:
        return None
    if step >= 0:
        for k, (i, s, _e) in enumerate(found):
            if (i, s) > where or (step == 0 and (i, s) == where):
                return k
        return 0
    for k in range(len(found) - 1, -1, -1):
        i, s, _e = found[k]
        if (i, s) < where:
            return k
    return len(found) - 1


def go(step):
    """Select the match step away (0: the first from the cursor) and bring
    it into view. Returns its index or None."""
    text = _text()
    found = _found(text, getattr(bpy.context.window_manager, PROP, ""))
    k = pick(found, _selection(text)[0], step) if text else None
    if k is None:
        return None
    i, s, e = found[k]
    text.cursor_set(i, character=s)
    text.cursor_set(i, character=e, select=True)
    from ..voice import script_follow
    for area in script_follow._script_areas():
        script_follow.scroll_to(area, i)
        area.tag_redraw()
    return k


def _on_query(wm, _context):
    go(0)
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'TEXT_EDITOR':
                area.tag_redraw()


class PLASTRON_OT_script_find_step(bpy.types.Operator):
    """Go to the next / previous match in the script"""
    bl_idname = "plastron.script_find_step"
    bl_label = "Find Next"
    bl_options = {'INTERNAL'}

    step: bpy.props.IntProperty(default=1)

    @classmethod
    def description(cls, _context, props):
        return "Previous match in the script" if props.step < 0 else "Next match in the script"

    def execute(self, context):
        if go(self.step) is None:
            self.report({'INFO'}, "Not found in the script")
        return {'FINISHED'}


def draw_field(layout, context, focus=False):
    """The search field, the count and the arrows."""
    wm = context.window_manager
    row = layout.row(align=True)
    field = row.row(align=True)
    field.ui_units_x = cfg.SCRIPT_SEARCH["field_width"]
    if focus:
        field.activate_init = True
    field.prop(wm, PROP, text="", icon='VIEWZOOM')
    query = getattr(wm, PROP, "")
    if query:
        text = _text()
        found = _found(text, query)
        k = current(text, found) if found else None
        sub = row.row(align=True)
        sub.alert = not found
        sub.label(text=f"{'-' if k is None else k + 1}/{len(found)}" if found else "0")
    row.operator("plastron.script_find_step", text="", icon='TRIA_UP').step = -1
    row.operator("plastron.script_find_step", text="", icon='TRIA_DOWN').step = 1


class PLASTRON_OT_script_find(bpy.types.Operator):
    """Find in the script: a search box, ready to type"""
    bl_idname = "plastron.script_find"
    bl_label = "Find in Script"
    bl_options = {'INTERNAL'}

    def invoke(self, context, _event):
        return context.window_manager.invoke_popup(self, width=round(14 * 20 * context.preferences.system.ui_scale))

    def draw(self, context):
        draw_field(self.layout, context, focus=True)

    def execute(self, _context):
        return {'FINISHED'}


class PLASTRON_PT_script_find(bpy.types.Panel):
    """The search field in a box (popover)."""
    bl_idname = "PLASTRON_PT_script_find"
    bl_label = "Find in Script"
    bl_space_type = 'TEXT_EDITOR'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 14

    def draw(self, context):
        draw_field(self.layout, context, focus=True)


def draw_button(layout, context):
    """The script bar's small search field (the bar scrolls when it's narrow)."""
    draw_field(layout, context)


def draw():
    """Tint every match on screen (the selected one stronger)."""
    context = bpy.context
    space, region = context.space_data, context.region
    text = space.text if space else None
    if text is None or text.name != defaults.SCRIPT_TEXT_NAME or region is None:
        return
    query = getattr(context.window_manager, PROP, "")
    if not query:
        return
    from ..voice import script_link
    if script_link.scrolling(context):
        return
    found = _found(text, query)
    if not found:
        return
    look = cfg.SCRIPT_SEARCH
    row_h = space.font_size * context.preferences.system.ui_scale * cfg.SCRIPT_FOLLOW["row"]
    now = current(text, found)
    tris = {False: [], True: []}
    for k, (i, s, e) in enumerate(found):
        segs = []                                   # (wrapped text: a match can run onto the next row)
        for c in range(s, e + 1):
            x, y = space.region_location_from_cursor(i, c)
            if segs and abs(segs[-1][2] - y) < 1:
                segs[-1][1] = x
            elif c < e:
                segs.append([x, x, y])
        for x0, x1, y in segs:
            if x1 <= x0:
                x1 = x0 + row_h * 0.4                # (the row's last letter: its width unknown)
            y0, y1 = y - row_h * 0.25, y + row_h * 0.7
            if y1 < 0 or y0 > region.height:
                continue
            tris[k == now] += [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    rgb = _color(look["color"])[:3]
    for is_now, pts in tris.items():
        if pts:
            shader.uniform_float("color", (*rgb, look["current_alpha" if is_now else "alpha"]))
            batch_for_shader(shader, 'TRIS', {"pos": pts}).draw(shader)
    gpu.state.blend_set('NONE')


classes = (PLASTRON_OT_script_find_step, PLASTRON_OT_script_find, PLASTRON_PT_script_find)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    setattr(bpy.types.WindowManager, PROP, bpy.props.StringProperty(
        name="Find", description="Find in the script (every match is lit; the arrows step through them)",
        options={'TEXTEDIT_UPDATE'}, update=_on_query))
    _handles.append(bpy.types.SpaceTextEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handles:
        bpy.types.SpaceTextEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
    delattr(bpy.types.WindowManager, PROP)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
