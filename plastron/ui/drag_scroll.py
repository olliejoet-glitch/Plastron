"""Scroll the tools area and the script with the pen (Alt+Shift+drag, the
same drag that pans the canvas and timeline): a pen has no wheel, and
Blender's own panel scrolling wants a middle mouse button."""

import bpy


class PLASTRON_OT_drag_scroll(bpy.types.Operator):
    """Drag to scroll"""
    bl_idname = "plastron.drag_scroll"
    bl_label = "Scroll"
    bl_options = {'INTERNAL'}

    @staticmethod
    def _under(context, event):
        """(area, region) of the tools area / script under the pen. Found by
        hand: this runs before the area's buttons (Screen Editing keymap), so
        a drag that starts on a button still scrolls."""
        for area in context.window.screen.areas:
            if area.type not in {'PROPERTIES', 'TEXT_EDITOR'}:
                continue
            for region in area.regions:
                if region.type == 'WINDOW' and region.x <= event.mouse_x < region.x + region.width \
                        and region.y <= event.mouse_y < region.y + region.height:
                    return area, region
        return None

    def invoke(self, context, event):
        hit = self._under(context, event)
        if hit is None:
            return {'PASS_THROUGH'}
        self.area, self.region = hit
        self.last_y = event.mouse_y
        self.carry = 0.0
        context.window.cursor_modal_set('HAND')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _scroll(self, context, dy):
        if self.area.type == 'TEXT_EDITOR':
            st = self.area.spaces.active
            if st.text is None:
                return
            lines = self.carry + dy / max(1.0, 1.3 * st.font_size)
            whole = int(lines)
            self.carry = lines - whole
            if whole:
                st.top = max(0, st.top + whole)
        else:
            # view2d.pan moves exactly this many pixels (scroll_up / down
            # always jump 40 px, which raced away under the pen).
            self.carry += dy
            whole = int(self.carry)
            self.carry -= whole
            if whole:
                with context.temp_override(area=self.area, region=self.region):
                    bpy.ops.view2d.pan(deltax=0, deltay=-whole)
        self.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            dy = event.mouse_y - self.last_y       # hand moves up: content follows it up
            self.last_y = event.mouse_y
            if dy:
                self._scroll(context, dy)
            return {'RUNNING_MODAL'}
        if event.value == 'RELEASE' and event.type in {'LEFTMOUSE', 'MIDDLEMOUSE'} or event.type == 'ESC':
            context.window.cursor_modal_restore()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


classes = (PLASTRON_OT_drag_scroll,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
