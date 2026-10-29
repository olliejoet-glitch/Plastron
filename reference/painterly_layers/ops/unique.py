"""Duplicated materials get their own layers (§58).

Blender's material duplicate (the slot's New / copy button, or making a material single-user)
copies the material but NOT the images it paints into, and the copy's layer settings name the
same private node groups (".PL L <uid>", ".PL Stack ..."). So painting or editing the copy also
changed every object on the original.

Whenever a CaraPainter material appears that shares layers or paint images with another one, the
copy is separated: new layer ids, its own copies of the images CaraPainter made (paint layers,
painted masks, depth corrections, outline mask, bakes), fresh node groups. The original is left
exactly as it was. Your own textures (Base, fill images, normal map) stay shared: they're inputs.
"""
import uuid

import bpy
import numpy as np

from .. import props

# (the normal-map analysis caches - height, curvature, forms - are keyed by the normal map and
# stay shared on purpose)
_STACK_OWNED = ("baked_image", "bake_shadow_image", "thickness_image", "outline_mask")


def _owned(img):
    return img is not None and bool(img.get("pl_owned"))


def _image_slots(stack):
    """(owner, prop name, image) for every image this stack PAINTS INTO or made itself (not the
    textures it reads: Base / fill / library images may be shared by unrelated materials)."""
    for layer in stack.layers:
        if layer.layer_type == "PAINT" and _owned(layer.paint_image):
            yield layer, "paint_image", layer.paint_image
        for m in layer.masks:
            if m.source == "PAINT" and _owned(m.image):
                yield m, "image", m.image
            if _owned(m.correction):
                yield m, "correction", m.correction
    for p in _STACK_OWNED:
        img = getattr(stack, p, None)
        if _owned(img):
            yield stack, p, img


def _keys(mat):
    st = mat.pl_stack
    keys = {("uid", l.uid) for l in st.layers if l.uid}
    keys |= {("img", img.name) for _o, _p, img in _image_slots(st)}
    if st.node_tree_name:
        keys.add(("tree", st.node_tree_name))
    return keys


def find_copies():
    """CaraPainter materials that share layers / images with another one, originals excluded:
    of two that share, the one whose name sorts first ('X' before 'X.001') is the original."""
    claimed, copies = set(), []
    for mat in sorted((m for m in bpy.data.materials if m.pl_stack.enabled and m.library is None),
                      key=lambda m: m.name):
        k = _keys(mat)
        if k & claimed:
            copies.append(mat.name)
        else:
            claimed |= k
    return copies


def _copy_image(img, mat_name, old_mat_name):
    w, h = img.size
    name = img.name.replace(old_mat_name, mat_name) if old_mat_name and old_mat_name in img.name \
        else f"{mat_name} · {img.name}"
    new = bpy.data.images.new(name, w, h, alpha=True, float_buffer=img.is_float)
    new.colorspace_settings.name = img.colorspace_settings.name   # (BEFORE the pixels)
    new.alpha_mode = img.alpha_mode
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    new.pixels.foreach_set(px)
    new.update()
    for k in img.keys():
        try:
            new[k] = img[k]
        except (TypeError, KeyError):
            pass
    new["pl_owned"] = True
    from ..imgpack import pack_float
    pack_float(new)
    return new


def _original_name(mat):
    """The material this one was copied from (for naming its images), if it's still there."""
    base = mat.name.rsplit(".", 1)[0] if mat.name[-4:-3] == "." and mat.name[-3:].isdigit() else ""
    return base if base and base in bpy.data.materials else ""


def make_unique(mat):
    """Give `mat` its own layer ids, image copies and node groups. Returns True when done."""
    from ..compiler import compile_stack
    from .attach import repair_links
    from .layers import sync_paint_target
    st = mat.pl_stack
    old_stack_tree = st.node_tree
    src = _original_name(mat)
    copied = {}
    with props.suspended():
        remap = {l.uid: uuid.uuid4().hex[:10] for l in st.layers if l.uid}
        for l in st.layers:
            if l.uid:
                l.uid = remap[l.uid]
            if l.parent_uid:
                l.parent_uid = remap.get(l.parent_uid, l.parent_uid)
            l.node_tree_name = ""
        for owner, p, img in list(_image_slots(st)):
            if img.name not in copied:
                copied[img.name] = _copy_image(img, mat.name, src)
            setattr(owner, p, copied[img.name])
        st.node_tree_name = ""
    compile_stack(mat)
    new_tree = st.node_tree
    if new_tree is None:
        return False
    if old_stack_tree is not None and mat.node_tree is not None:
        for n in mat.node_tree.nodes:
            if n.type == 'GROUP' and n.node_tree == old_stack_tree:
                n.node_tree = new_tree
    repair_links(mat)
    try:
        sync_paint_target(bpy.context, mat)
    except Exception:
        pass
    print(f"CaraPainter: '{mat.name}' was a copy: it now has its own layers "
          f"({len(copied)} image(s) copied)")
    return True


# --- when to look -------------------------------------------------------------------------------
_count = [-1]


def check_soon():
    if not bpy.app.timers.is_registered(_check_timer):
        bpy.app.timers.register(_check_timer, first_interval=0.2)


def materials_changed():
    """Cheap test from the depsgraph handler: has the number of materials changed?"""
    n = len(bpy.data.materials)
    if n != _count[0]:
        _count[0] = n
        check_soon()


def separate_all():
    done = []
    for name in find_copies():
        mat = bpy.data.materials.get(name)
        if mat is not None and make_unique(mat):
            done.append(name)
    return done


def _check_timer():
    if bpy.app.is_job_running('RENDER_PREVIEW'):
        return 0.3
    try:
        done = separate_all()
        if done and not bpy.app.background:
            try:
                bpy.ops.ed.undo_push(message="CaraPainter: separate duplicated material")
            except RuntimeError:
                pass
    except Exception as e:   # (never let it break the session)
        print("CaraPainter: separating duplicated materials:", e)
    return None
