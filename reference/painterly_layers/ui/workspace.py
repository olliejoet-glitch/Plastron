"""The "CaraPainter" workspace. Hotkeys are only live in workspaces flagged pl_painterly."""
import bpy


class PL_OT_workspace_setup(bpy.types.Operator):
    bl_idname = "pl.workspace_setup"
    bl_label = "Create CaraPainter Workspace"
    bl_description = ("Duplicate the current workspace as 'CaraPainter': Texture Paint mode, "
                      "Material Preview, Layers sidebar, and the left-hand painting hotkeys")

    def execute(self, context):
        # workspaces made before the rename are still called "Painterly"
        existing = next((w for n in ("CaraPainter", "Painterly") for w in bpy.data.workspaces
                         if w.name == n and w.get("pl_painterly")), None)
        if existing is not None:
            context.window.workspace = existing
            return {'FINISHED'}
        before = set(bpy.data.workspaces)
        bpy.ops.workspace.duplicate()
        # the window switches workspace later, so find the copy instead of using context
        new = [w for w in bpy.data.workspaces if w not in before]
        if not new:
            self.report({'ERROR'}, "Could not duplicate the workspace")
            return {'CANCELLED'}
        ws = new[0]
        ws.name = "CaraPainter"
        ws["pl_painterly"] = True
        ws.object_mode = 'TEXTURE_PAINT'
        context.window.workspace = ws
        for screen in ws.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    space = area.spaces.active
                    space.shading.type = 'MATERIAL'
                    # light the preview with the scene's lights: toon shaders and the Cast Shadow
                    # mask need the key light (Material Preview otherwise uses a studio HDRI)
                    space.shading.use_scene_lights = True
                    space.shading.use_scene_world = True
                    space.show_region_ui = True
        self.report({'INFO'}, "CaraPainter workspace created: Q/W size, E eraser, Z pick, C flat view")
        return {'FINISHED'}


class PL_OT_workspace_flag(bpy.types.Operator):
    bl_idname = "pl.workspace_flag"
    bl_label = "Use CaraPainter Hotkeys Here"
    bl_description = "Turn the painting hotkeys on/off in the current workspace"

    def execute(self, context):
        ws = context.workspace
        ws["pl_painterly"] = not bool(ws.get("pl_painterly"))
        return {'FINISHED'}


classes = (PL_OT_workspace_setup, PL_OT_workspace_flag)
