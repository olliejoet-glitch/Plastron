"""Your layout, kept (Ollie: "I want whatever layout I've made to be saved as
the default when I reopen Plastron").

Every save (and autosave), each mode's screen is measured and kept in
Plastron's settings as a rows / columns tree, the same shape as
config/layout.py's MODES (areas named by what they are: canvas, script,
timeline...). When Plastron starts, each mode that differs from config's is rebuilt that
way (sizes, swapped areas, areas split / joined, other editors).
File > Reset Layout goes back to config/layout.py's.
"""

import bpy

from ..config import layout as cfg
from . import user_settings

KEY = "layouts"
TOL = 4                    # px: area edges this close count as one line
CHECK_EVERY = 10.0         # s: how often the layout is measured (and on every save)


# --- What an area is ----------------------------------------------------------------------------

def _signature(area):
    space = area.spaces.active
    sig = [area.type]
    if area.type == 'VIEW_3D':
        sig.append("canvas" if getattr(space, "show_region_tool_header", False) else "scene")
    if area.type == 'SEQUENCE_EDITOR':
        sig += [space.view_type, getattr(space, "display_mode", "")]
    return tuple(sig)


def _config_signature(name):
    a = cfg.AREAS[name]
    sig = [a["editor"]]
    if a["editor"] == 'VIEW_3D':
        sig.append("scene" if a.get("scene_view") else "canvas")
    if a["editor"] == 'SEQUENCE_EDITOR':
        s = a.get("settings", {})
        sig += [s.get("view_type", 'SEQUENCER'), s.get("display_mode", 'IMAGE')]
    return tuple(sig)


def _leaves(node):
    if "area" in node:
        return [node["area"]]
    return [x for c in node.get("rows", node.get("columns", [])) for x in _leaves(c)]


def names_for(screen, mode):
    """{area pointer: name}: config's names for this mode's kinds of area,
    "editor:<TYPE>" for others (a second of the same: "#2")."""
    by_sig = {}
    for name in _leaves(cfg.MODES[mode]):
        by_sig.setdefault(_config_signature(name), []).append(name)
    out, used = {}, {}
    for area in sorted(screen.areas, key=lambda a: (-a.y, a.x)):
        sig = _signature(area)
        options = [n for n in by_sig.get(sig, []) if n not in used]
        if options:
            name = options[0]
        else:
            base = by_sig.get(sig, ["editor:" + area.type])[0]
            n = 2
            while f"{base}#{n}" in used:
                n += 1
            name = f"{base}#{n}" if base in used else base
        used[name] = True
        out[area.as_pointer()] = name
    return out


# --- Measuring a screen into a tree -------------------------------------------------------------

def tree_of(rects):
    """rects: [(x0, y0, x1, y1, name)] covering a box -> rows / columns tree
    (sizes = fractions), or None if they can't be cut edge to edge."""
    if len(rects) == 1:
        return {"area": rects[0][4]}
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[2] for r in rects)
    y1 = max(r[3] for r in rects)
    for axis in ("rows", "columns"):
        lo, hi = (1, 3) if axis == "rows" else (0, 2)
        cuts = sorted({r[lo] for r in rects if r[lo] > (y0 if axis == "rows" else x0) + TOL})
        good = [c for c in cuts if all(r[hi] <= c + TOL or r[lo] >= c - TOL for r in rects)]
        if not good:
            continue
        edges = [(y0 if axis == "rows" else x0)] + good + [(y1 if axis == "rows" else x1)]
        groups = []
        for a, b in zip(edges, edges[1:]):
            groups.append([r for r in rects if r[lo] >= a - TOL and r[hi] <= b + TOL])
        total = edges[-1] - edges[0]
        children = []
        for (a, b), g in zip(zip(edges, edges[1:]), groups):
            sub = tree_of(g)
            if sub is None or not g:
                return None
            sub = dict(sub, size=round((b - a) / total, 4))
            children.append(sub)
        if axis == "rows":
            children.reverse()                 # (top to bottom)
        return {axis: children}
    return None


def capture(screen, mode):
    names = names_for(screen, mode)
    rects = [(a.x, a.y, a.x + a.width, a.y + a.height, names[a.as_pointer()]) for a in screen.areas]
    return tree_of(rects)


def _shape(node):
    if "area" in node:
        return node["area"]
    kind = "rows" if "rows" in node else "columns"
    return (kind, tuple(_shape(c) for c in node[kind]))


def same_layout(a, b, tol=0.01):
    if _shape(a) != _shape(b):
        return False
    if "area" in a:
        return True
    kind = "rows" if "rows" in a else "columns"
    return all(abs(x.get("size", 1) - y.get("size", 1)) <= tol and same_layout(x, y, tol)
               for x, y in zip(a[kind], b[kind]))


def usable(mode, tree):
    """A kept layout still has the mode's must-have areas (a layout left half
    rebuilt, every area a copy of the canvas, was kept and came back at
    every start)."""
    if not tree or mode not in cfg.MODES:
        return False
    names = _leaves(tree)
    needs = cfg.KEPT_NEEDS.get(mode, ())
    return all(n in names for n in needs) and \
        not any(n.split("#", 1)[0] in needs for n in names if "#" in n)    # (no second canvas...)


def built_right(placed):
    """Every area rebuilt ({name: area}) is the editor (and kind) it should be."""
    from . import layout as builder
    for name, area in placed.items():
        want = builder.spec(name)
        if not want.get("editor"):
            return False
        base = name.split("#", 1)[0]
        if base in cfg.AREAS:
            if _signature(area)[:2] != _config_signature(base)[:2]:
                return False
        elif area.type != want["editor"]:
            return False
    return True


def _mode_screen(mode):
    ws = bpy.data.workspaces.get(mode)
    return ws.screens[0] if ws and ws.screens else None


_busy = [False]           # (while a layout is being put back: don't measure it)


def save():
    """Measure every mode's screen; keep the ones that differ from config's
    (a mode with an area maximised (Ctrl+Space) keeps what was kept)."""
    if _busy[0]:
        return
    before = user_settings.get(KEY) or {}
    out = {}
    for mode in cfg.MODES:
        screen = _mode_screen(mode)
        if screen is None or screen.show_fullscreen or any(a.width < 2 for a in screen.areas):
            if mode in before:
                out[mode] = before[mode]
            continue
        tree = capture(screen, mode)
        if tree is None:
            if mode in before:
                out[mode] = before[mode]
        elif not same_layout(tree, cfg.MODES[mode]) and usable(mode, tree):
            out[mode] = tree
    if out != before:
        user_settings.set(KEY, out)


# --- Putting a screen back ----------------------------------------------------------------------

def _timeline_area(screen):
    return next((a for a in screen.areas if a.type == 'SEQUENCE_EDITOR'
                 and a.spaces.active.view_type == 'SEQUENCER'), None)


def _leave_paint_mode(window):
    """Object mode (the pen over the canvas puts Texture Paint back)."""
    obj = bpy.context.view_layer.objects.active
    if obj is None or obj.mode == 'OBJECT':
        return
    area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
        bpy.ops.object.mode_set(mode='OBJECT')


def _rebuild(window, mode, tree):
    from . import layout as builder
    _leave_paint_mode(window)       # (closing the canvas mid-Texture Paint crashed Blender)
    yield
    placed = {}
    yield from builder.split_mode(window, mode, placed, tree)
    yield
    builder.set_view_types(placed)
    yield
    yield
    builder.configure_mode(placed)
    yield
    builder.hide_navigation_bars(window, placed)
    yield
    return placed


def restore_steps(window, layouts):
    """Generator: each mode to the layouts given ({mode: tree}), rebuilt
    by splitting, as tools/build_startup.py does (Blender's edge move and
    area swap can't run from Python while the pointer is over an area). The
    timeline keeps its track-header width through it. A layout that can't
    be kept (lost its must-have areas) or doesn't build right: Plastron's
    own, and it's no longer kept."""
    _busy[0] = True
    try:
        start = window.workspace
        failed = []
        for mode, tree in layouts.items():
            ws = bpy.data.workspaces.get(mode)
            if ws is None:
                continue
            if not usable(mode, tree):
                failed.append(mode)
                tree = cfg.MODES[mode]
            window.workspace = ws
            yield
            yield
            own = cfg.MODES[mode]
            for attempt in ([tree] if tree is own else [tree, own]):    # (didn't work: Plastron's own)
                current = capture(window.screen, mode)
                if current is not None and same_layout(current, attempt, tol=0.005):
                    break                           # (same kinds of area in the same places)
                try:
                    placed = yield from _rebuild(window, mode, attempt)
                    ok = built_right(placed)
                except Exception as err:            # (never leave a mode half built)
                    print(f"Plastron layout: couldn't rebuild {mode}:", err)
                    ok = False
                if ok:
                    break
                if mode not in failed:
                    failed.append(mode)
            yield
        window.workspace = start
        if failed:                      # (not kept: Plastron's own comes back next time too)
            kept = dict(user_settings.get(KEY) or {})
            if any(kept.pop(m, None) is not None for m in failed):
                user_settings.set(KEY, kept)
        yield 0.6                       # (new areas settle before they're set up / framed)
    finally:
        _busy[0] = False
    from . import handlers                                     # (features set their areas up again)
    handlers.run_on_load()


_running = [False]       # (a layout being put back from a timer: tests wait for it)


def running():
    return _running[0]


def _run(steps, first_interval):
    def tick():
        try:
            wait = next(steps)
        except StopIteration:
            _running[0] = False
            return None
        except Exception as err:            # never leave Plastron broken over a layout
            _busy[0] = _running[0] = False
            print("Plastron layout: couldn't put the layout back:", err)
            return None
        return wait or 0.05
    _running[0] = True
    bpy.app.timers.register(tick, first_interval=first_interval)


def restore():
    """At start: put the kept layouts back (from a timer: needs the UI)."""
    layouts = user_settings.get(KEY) or {}
    if layouts:
        _run(restore_steps(bpy.context.window_manager.windows[0], dict(layouts)), 0.3)


def reset():
    """File > Reset Layout: config/layout.py's layouts again (rebuilt now)."""
    user_settings.set(KEY, {})
    layouts = {mode: cfg.MODES[mode] for mode in cfg.MODES
               if (s := _mode_screen(mode)) is None or capture(s, mode) is None
               or not same_layout(capture(s, mode), cfg.MODES[mode])}
    _run(restore_steps(bpy.context.window_manager.windows[0], layouts), 0.1)


def _tick():
    """Measure the layout now and then too (not only on save: Plastron may be
    closed without saving). A few areas' sizes: nothing to speak of."""
    try:
        save()
    except Exception as err:
        print("Plastron layout: couldn't measure the layout:", err)
    return CHECK_EVERY


_started = [False]


def _on_load(_scene):
    if not _started[0]:
        _started[0] = True
        if not bpy.data.filepath:                # (Plastron starting, not a project opening)
            restore()


def _on_save(*_args):
    save()


class PLASTRON_OT_layout_reset(bpy.types.Operator):
    """Put every mode's layout back to Plastron's own"""
    bl_idname = "plastron.layout_reset"
    bl_label = "Reset Layout"

    def execute(self, context):
        reset()
        return {'FINISHED'}


def register():
    from . import handlers
    bpy.utils.register_class(PLASTRON_OT_layout_reset)
    handlers.on_load(_on_load)
    handlers.add("save_post", _on_save)
    bpy.app.timers.register(_tick, first_interval=CHECK_EVERY, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    bpy.utils.unregister_class(PLASTRON_OT_layout_reset)
