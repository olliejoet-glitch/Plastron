"""Marching-ants outline of the selection, drawn on the model's surface.

Drawn per frame in the viewport (POST_VIEW, depth-tested against the scene) from the selection
texture: the line sits where the selection crosses 50 %, so it follows navigation, deformation
and feathering. A light timer animates the ants while a selection exists.
"""
import time

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .. import project as pj

_cache = {"key": None, "batch": None}
_shader_cache = {}
_handle = None


def invalidate():
    _cache["key"] = None


def _shader():
    if "s" in _shader_cache:
        return _shader_cache["s"]
    info = gpu.types.GPUShaderCreateInfo()
    info.vertex_in(0, 'VEC3', 'P')
    info.vertex_in(1, 'VEC2', 'uv')
    info.push_constant('MAT4', 'VP')
    info.push_constant('FLOAT', 'phase')
    info.sampler(0, 'FLOAT_2D', 'sel')
    iface = gpu.types.GPUStageInterfaceInfo("pl_outline")
    iface.smooth('VEC2', 'v_uv')
    info.vertex_out(iface)
    info.fragment_out(0, 'VEC4', 'FragColor')
    info.vertex_source(
        "void main(){ v_uv = uv; gl_Position = VP * vec4(P, 1.0);"
        " gl_Position.z -= 0.0004 * gl_Position.w; }")  # nudge toward the camera: no z-fighting
    info.fragment_source(
        "void main(){"
        " float s = texture(sel, v_uv).r;"
        " float w = max(fwidth(s), 1e-5);"
        " float a = 1.0 - smoothstep(0.6, 1.4, abs(s - 0.5) / w);"
        " if (a < 0.02) discard;"
        " float ants = mod(floor((gl_FragCoord.x + gl_FragCoord.y) / 5.0 - phase), 2.0);"
        " FragColor = vec4(vec3(ants), a); }")
    _shader_cache["s"] = gpu.shader.create_from_info(info)
    return _shader_cache["s"]


def _batch(context, ob, uv_name):
    key = (ob.name, uv_name)
    if _cache["key"] != key or _cache["batch"] is None:
        P, UV = pj.mesh_arrays(ob, context.evaluated_depsgraph_get(), uv_name)
        _cache["batch"] = batch_for_shader(_shader(), 'TRIS', {"P": P, "uv": UV})
        _cache["key"] = key
    return _cache["batch"]


def _active(context):
    from ..ops.select import selection_image
    from ..ops.view import in_painterly
    if context.mode != 'PAINT_TEXTURE' or not in_painterly(context):
        return None
    ob = context.object
    mat = ob.active_material if ob else None
    if mat is None or not mat.pl_stack.enabled:
        return None
    img = selection_image(context)
    return (ob, mat, img) if img is not None else None


def _draw():
    try:
        ctx = bpy.context
        found = _active(ctx)
        if found is None or ctx.region_data is None:
            return
        ob, mat, img = found
        sh = _shader()
        batch = _batch(ctx, ob, mat.pl_stack.uv_map)
        tex = gpu.texture.from_image(img)
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        sh.bind()
        sh.uniform_float("VP", ctx.region_data.perspective_matrix)
        sh.uniform_float("phase", (time.time() * 6.0) % 1000.0)
        sh.uniform_sampler("sel", tex)
        batch.draw(sh)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
    except Exception as e:  # never break the viewport
        print("CaraPainter outline:", e)


def _tick():
    """Animate the ants (only redraws while a selection is showing)."""
    try:
        wm = bpy.context.window_manager
        for win in wm.windows:
            ip = win.scene.tool_settings.image_paint
            img = ip.stencil_image
            if not (ip.use_stencil_layer and img is not None and img.get("pl_selection")):
                continue
            if not win.workspace.get("pl_painterly"):
                continue
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass
    return 0.12


def register():
    global _handle
    _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')
    bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)


def unregister():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _shader_cache.clear()
    invalidate()
