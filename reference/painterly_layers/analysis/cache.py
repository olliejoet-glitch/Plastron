"""Cache of normal-derived images, one pair per normal map, recomputed when the normal map changes.

The heavy numpy work runs on a worker thread (bpy is only touched on the main thread, before and
after), so Blender stays usable during the ~30-60 s analysis of a 2K map. Results are packed float
images, tagged with a fingerprint of the normal map's pixels.
"""
import hashlib
import threading
import traceback

import bpy
import numpy as np

from . import compute_derived

HEIGHT_PREFIX = "PL Height · "
CURVE_PREFIX = "PL Curvature · "
FORMS_A_PREFIX = "PL Forms A · "
FORMS_B_PREFIX = "PL Forms B · "
FORMS_C_PREFIX = "PL Forms C · "
JOBS = {}        # normal image name -> job dict
_PENDING = set()  # normal image names waiting for a debounced re-check


def names(normal_img):
    n = normal_img.name
    return HEIGHT_PREFIX + n, CURVE_PREFIX + n, FORMS_A_PREFIX + n, FORMS_B_PREFIX + n, FORMS_C_PREFIX + n


def _pixels(img):
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def fingerprint(img, px=None):
    px = _pixels(img) if px is None else px
    sample = np.round(px.reshape(-1)[::4099] * 1000).astype(np.int32)
    return f"{img.size[0]}x{img.size[1]}:" + hashlib.md5(sample.tobytes()).hexdigest()


def mesh_inputs(mat, uv_name):
    """UV layout of the first mesh object using this material."""
    users = [o for o in bpy.data.objects if o.type == 'MESH' and o.data is not None
             and any(s.material == mat for s in o.material_slots)]
    if not users:
        raise ValueError(f"no mesh uses material '{mat.name}'")
    act = getattr(bpy.context, "active_object", None)
    # the active object first, then any other user that HAS a UV map (another object sharing the
    # material may have none)
    users.sort(key=lambda o: (o != act, not len(o.data.uv_layers)))
    ob = users[0]
    me = ob.data
    if not len(me.uv_layers):
        raise ValueError(f"'{ob.name}' has no UV map: unwrap it (UV > Unwrap) and try again")
    me.calc_loop_triangles()
    tris = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tris)
    layer = (me.uv_layers.get(uv_name) if uv_name else None) or me.uv_layers.active or me.uv_layers[0]
    uv = np.empty(len(me.loops) * 2, np.float32)
    layer.data.foreach_get("uv", uv)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    starts = np.empty(len(me.polygons), np.int32)
    totals = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    within = np.arange(totals.sum()) - np.repeat(np.cumsum(totals) - totals, totals)
    lp = np.empty(len(me.loops), np.int32)  # polygon index of every loop
    lp[np.repeat(starts, totals) + within] = np.repeat(np.arange(len(me.polygons)), totals)
    return tris.reshape(-1, 3), uv.reshape(-1, 2), lv, lp


def _write(name, arr, fp):
    h, w = arr.shape[:2]
    img = bpy.data.images.get(name)
    if img is None or tuple(img.size) != (w, h):
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    # four independent data channels: without this, the packed EXR reloads as premultiplied and
    # Blender divides RGB by A when sampling (the render then differs after save/reload)
    img.alpha_mode = 'CHANNEL_PACKED'
    img.pixels.foreach_set(np.ascontiguousarray(arr, np.float32).reshape(-1))
    img.update()
    from ..imgpack import pack_float
    pack_float(img)   # compressed half-float EXR, not Blender's 67 MB 32-bit default (§60)
    img["pl_src_fingerprint"] = fp
    return img


def _link(normal_name, imgs):
    from .. import props
    from ..compiler import compile_stack
    for mat in bpy.data.materials:
        st = mat.pl_stack
        if st.enabled and st.normal_image is not None and st.normal_image.name == normal_name:
            with props.suspended():
                st.height_image, st.curvature_image, st.forms_a, st.forms_b, st.forms_c = imgs
            compile_stack(mat)


def is_current(normal_img):
    imgs = [bpy.data.images.get(n) for n in names(normal_img)]
    if any(i is None for i in imgs):
        return False
    return imgs[0].get("pl_src_fingerprint") == fingerprint(normal_img)


def status(mat):
    """(state, progress 0..1, message): state in NONE / RUNNING / READY / ERROR."""
    img = mat.pl_stack.normal_image
    if img is None:
        return "NONE", 0.0, "no normal map"
    job = JOBS.get(img.name)
    if job is not None:
        if job.get("error"):
            return "ERROR", 0.0, job["error"]
        return "RUNNING", job["progress"], job["msg"]
    if mat.pl_stack.height_image is not None:
        return "READY", 1.0, "ready"
    return "NONE", 0.0, "not analysed yet"


def _gather(mat):
    st = mat.pl_stack
    img = st.normal_image
    px = _pixels(img)
    return img.name, fingerprint(img, px), px[..., :3].copy(), mesh_inputs(mat, st.uv_map)


def analyse_now(mat):
    """Synchronous (tests, background mode)."""
    name, fp, normal, (tris, uv, lv, lp) = _gather(mat)
    *arrays, conv = compute_derived(normal, tris, uv, lv, lp)
    imgs = [_write(n, a, fp) for n, a in zip(names(mat.pl_stack.normal_image), arrays)]
    imgs[0]["pl_convention"] = conv
    _link(name, imgs)
    return conv


def start(mat, force=False):
    """Begin (re)analysis on a worker thread if the cached data is missing or stale."""
    st = mat.pl_stack
    img = st.normal_image
    if img is None or img.name in JOBS:
        return False
    all_names = names(img)
    if not force and is_current(img):
        imgs = [bpy.data.images[n] for n in all_names]
        if [st.height_image, st.curvature_image, st.forms_a, st.forms_b, st.forms_c] != imgs:
            _link(img.name, imgs)
        return False
    try:
        name, fp, normal, (tris, uv, lv, lp) = _gather(mat)
    except Exception as e:
        JOBS[img.name] = {"progress": 0.0, "msg": "", "error": str(e), "thread": None}
        return False
    job = {"progress": 0.0, "msg": "starting", "result": None, "error": None, "fp": fp, "names": all_names}

    def work():
        try:
            def prog(f, msg):
                job["progress"], job["msg"] = f, msg
            job["result"] = compute_derived(normal, tris, uv, lv, lp, prog)
        except Exception as e:
            traceback.print_exc()
            job["error"] = str(e)

    job["thread"] = threading.Thread(target=work, daemon=True)
    JOBS[name] = job
    job["thread"].start()
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.5)
    return True


def _poll():
    for name, job in list(JOBS.items()):
        t = job.get("thread")
        if t is not None and t.is_alive():
            continue
        if job.get("result") is not None:
            *arrays, conv = job["result"]
            imgs = [_write(n, a, job["fp"]) for n, a in zip(job["names"], arrays)]
            imgs[0]["pl_convention"] = conv
            _link(name, imgs)
            del JOBS[name]
        elif t is not None:  # finished with an error: keep it visible, stop polling it
            job["thread"] = None
    _redraw()
    running = any(j.get("thread") is not None for j in JOBS.values())
    return 0.5 if running else None


def _redraw():
    wm = bpy.context.window_manager
    for win in wm.windows if wm else ():
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def normal_image_changed(image_name):
    """Called from the depsgraph handler: re-check (debounced) when a normal map is edited."""
    _PENDING.add(image_name)
    if not bpy.app.timers.is_registered(_check_pending):
        bpy.app.timers.register(_check_pending, first_interval=2.0)


def _check_pending():
    names_ = set(_PENDING)
    _PENDING.clear()
    for mat in bpy.data.materials:
        st = mat.pl_stack
        if st.enabled and st.normal_image is not None and st.normal_image.name in names_:
            start(mat)
    return None
