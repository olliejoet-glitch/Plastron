"""Editor-time handlers. Nothing here is needed to RENDER (SheepIt runs without the add-on)."""
import bpy
from bpy.app.handlers import persistent

from .compiler.layers import TREE_PREFIX, bi_is_default, normalise_blend_if_ramp

_busy = False


@persistent
def depsgraph_post(scene, depsgraph):
    """Keep Blend-If ramps meaning black/white/white/black whichever stop the user dragged."""
    global _busy
    if _busy:
        return
    from .ops import unique
    unique.materials_changed()   # (a duplicated material gets its own layers, §58)
    for u in depsgraph.updates:
        if isinstance(u.id, bpy.types.Image) and not u.id.name.startswith(("PL Height", "PL Curvature", "PL Forms")):
            from .analysis import cache
            if any(m.pl_stack.enabled and m.pl_stack.normal_image is not None
                   and m.pl_stack.normal_image.name == u.id.original.name for m in bpy.data.materials):
                cache.normal_image_changed(u.id.original.name)  # re-analyse (debounced)
    if any(isinstance(u.id, bpy.types.Object) and (u.is_updated_geometry or u.is_updated_transform)
           and not u.id.get("pl_outline") and not u.id.get("pl_outline_data") for u in depsgraph.updates):
        from .ui import outline
        outline.invalidate()  # mesh moved / deformed: rebuild the outline geometry
    trees = [u.id.original for u in depsgraph.updates
             if isinstance(u.id, bpy.types.ShaderNodeTree) and u.id.name.startswith(TREE_PREFIX)]
    if not trees:
        return
    _busy = True
    edited = set()
    try:
        for tree in trees:
            for n in tree.nodes:
                if n.type == 'VALTORGB' and n.name.startswith("BI."):
                    normalise_blend_if_ramp(n.color_ramp)
                    if not bi_is_default(n):
                        edited.add(tree.name)
    finally:
        _busy = False
    if edited:
        _blend_if_on_soon(edited)


_bi_pending = set()


def _blend_if_on_soon(tree_names):
    """A Blend If stop was dragged on a layer whose Blend If is off (§59): turn it on (wires the
    ramps in). From a timer: changing props inside the depsgraph handler isn't safe."""
    _bi_pending.update(tree_names)
    if not bpy.app.timers.is_registered(_blend_if_on):
        bpy.app.timers.register(_blend_if_on, first_interval=0.05)


def _blend_if_on():
    names = set(_bi_pending)
    _bi_pending.clear()
    for mat in bpy.data.materials:
        if not mat.pl_stack.enabled:
            continue
        for layer in mat.pl_stack.layers:
            if layer.node_tree_name in names and not layer.blend_if:
                layer.blend_if = True     # (structural: rebuilds with the edited stops kept)
    return None


@persistent
def save_post(*_):
    from .ops.formview import views_back_after_save
    views_back_after_save(bpy.context.scene)


@persistent
def save_pre(*_):
    """Pack paint images so the .blend is self-contained for SheepIt (and the live selection), and
    never save in the flat / form view (SheepIt would render that)."""
    from .ops.formview import views_off_for_save
    views_off_for_save(bpy.context.scene)
    ip = bpy.context.scene.tool_settings.image_paint if bpy.context.scene else None
    sel = ip.stencil_image if ip is not None else None
    if sel is not None and sel.get("pl_selection") and (sel.is_dirty or sel.packed_file is None):
        try:
            sel.pack()
        except RuntimeError:
            pass
    from .imgpack import is_bloated, ours, pack_float
    for img in bpy.data.images:
        if not ours(img):
            continue
        # painted / re-made since the last save, or packed by an older version as a 67 MB
        # uncompressed 32-bit EXR: (re)pack, floats as compressed half-float EXRs (§60)
        if (img.get("pl_owned") and (img.is_dirty or img.packed_file is None)) or is_bloated(img):
            try:
                pack_float(img)
            except RuntimeError as e:
                print(f"CaraPainter: could not pack {img.name}: {e}")


@persistent
def load_post_brushes(*_):
    from .ops import brushes
    brushes.subscribe()      # msgbus subscriptions are cleared when a file loads
    brushes.sync_jitter()
    brushes.refresh_previews()


@persistent
def load_post(*_):
    """Heal material<->stack links in files saved with 0.1.0; drop a selection whose image
    didn't survive (a blank stencil would block all painting)."""
    for sc in bpy.data.scenes:
        ip = sc.tool_settings.image_paint
        img = ip.stencil_image
        if ip.use_stencil_layer and img is not None and img.get("pl_selection") and not img.has_data                 and img.packed_file is None:
            ip.use_stencil_layer = False
    from .props import migrate_tree_pointers
    migrate_tree_pointers()   # (before anything compiles: the trees are found by name now)
    from .ops import unique
    try:   # materials duplicated before 0.22: separate them from their originals (§58)
        unique.separate_all()
    except Exception as e:
        print(f"CaraPainter: couldn't separate duplicated materials: {e}")
    unique._count[0] = len(bpy.data.materials)
    from .ops.attach import repair_links
    from .ops.formview import upgrade_bsdf
    for mat in bpy.data.materials:
        if mat.pl_stack.enabled:
            upgrade_bsdf(mat)   # Form View: Principled -> Diffuse (~1 s less compiling, §59)
        if mat.pl_stack.enabled and repair_links(mat):
            print(f"CaraPainter: repaired stack links in '{mat.name}'")
    from .compiler import compile_stack
    for mat in bpy.data.materials:   # layers built by an older version: rebuild (signature-driven)
        if mat.pl_stack.enabled:
            try:
                compile_stack(mat)
            except Exception as e:  # never block opening a file
                print(f"CaraPainter: couldn't update '{mat.name}': {e}")
    from .ops import outline, shadowdata
    for sc in bpy.data.scenes:   # outlines from older versions: current ink material + values
        if outline.is_enabled(sc):
            outline.apply(sc)
        shadowdata.cleanup(sc)
    if not bpy.app.background:  # files from older versions: bring the normal-map analysis up to date
        from .analysis import cache
        for mat in bpy.data.materials:
            st = mat.pl_stack
            if st.enabled and st.normal_image is not None and not cache.is_current(st.normal_image):
                cache.start(mat)


def register():
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_post)
    bpy.app.handlers.save_pre.append(save_pre)
    bpy.app.handlers.save_post.append(save_post)
    bpy.app.handlers.load_post.append(load_post)
    bpy.app.handlers.load_post.append(load_post_brushes)


def unregister():
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, depsgraph_post),
                    (bpy.app.handlers.save_pre, save_pre),
                    (bpy.app.handlers.save_post, save_post),
                    (bpy.app.handlers.load_post, load_post),
                    (bpy.app.handlers.load_post, load_post_brushes)):
        if fn in lst:
            lst.remove(fn)
