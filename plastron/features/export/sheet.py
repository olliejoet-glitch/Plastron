"""Panel sheet export (the brief's "all panels as a printable grid or PDF,
with each panel's notes underneath"). A plain PDF written here (no extra
packages): pages of panel pictures (their cached images) in a grid, each
with its number, name, status and length, notes and script line under it.
Page size / grid: config/export.py.
"""

import os
import textwrap
import zlib

import bpy
import numpy as np
from bpy_extras.io_utils import ExportHelper

from ...config import export as cfg
from ...timeline import clips


def _pdf_text(s):
    """A PDF string literal (Latin-1; anything else becomes '?')."""
    s = s.encode("latin-1", "replace").decode("latin-1")
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def _picture(strip):
    """The panel's cached picture: (width, height, RGB bytes top row first) or None."""
    path = bpy.path.abspath(os.path.join(strip.directory, strip.elements[0].filename))
    if not os.path.exists(path):
        return None
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    rgb = (np.clip(px.reshape(h, w, 4)[::-1, :, :3], 0, 1) * 255 + 0.5).astype(np.uint8)
    return w, h, rgb.tobytes()


def write_pdf(path, cells, title=""):
    """cells: [(picture or None, [caption lines])] -> PDF of grids."""
    pw, ph = cfg.SHEET_PAGE
    m, gap, cols, rows = cfg.SHEET_MARGIN, cfg.SHEET_GAP, cfg.SHEET_COLUMNS, cfg.SHEET_ROWS
    fs = cfg.SHEET_FONT_SIZE
    cell_w = (pw - 2 * m - (cols - 1) * gap) / cols
    pic_h = cell_w * 9 / 16
    cell_h = (ph - 2 * m - 16 - (rows - 1) * gap) / rows
    per_page = cols * rows

    objects = []                      # PDF objects (bytes), numbered from 1

    def add(body):
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = add(b"")               # filled in at the end
    page_ids = []
    pages = [cells[i:i + per_page] for i in range(0, len(cells), per_page)] or [[]]
    for pi, page in enumerate(pages):
        ops, xobjects = [], []
        if title:
            ops.append(f"BT /F1 11 Tf {m} {ph - m - 4} Td {_pdf_text(title)} Tj ET")
        ops.append(f"BT /F1 8 Tf {pw - m - 60} {m - 16} Td {_pdf_text(f'Page {pi + 1} of {len(pages)}')} Tj ET")
        for k, (picture, lines) in enumerate(page):
            r, c = divmod(k, cols)
            x = m + c * (cell_w + gap)
            top = ph - m - 16 - r * (cell_h + gap)
            y_pic = top - pic_h
            if picture is not None:
                w, h, data = picture
                stream = zlib.compress(data)
                img = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                          b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (w, h, len(stream))
                          + stream + b"\nendstream")
                name = f"Im{len(xobjects)}"
                xobjects.append((name, img))
                ops.append(f"q {cell_w:.2f} 0 0 {pic_h:.2f} {x:.2f} {y_pic:.2f} cm /{name} Do Q")
            ops.append(f"0.6 G {x:.2f} {y_pic:.2f} {cell_w:.2f} {pic_h:.2f} re S 0 G")
            y = y_pic - fs - 3
            for i, line in enumerate(lines):
                size = fs + 1 if i == 0 else fs
                ops.append(f"BT /F1 {size} Tf {x:.2f} {y:.2f} Td {_pdf_text(line)} Tj ET")
                y -= size + 2
                if y < top - cell_h:
                    break
        content = "\n".join(ops).encode("latin-1", "replace")
        content_id = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        res = b"<< /Font << /F1 %d 0 R >> /XObject << %s >> >>" % (
            font, b" ".join(b"/%s %d 0 R" % (n.encode(), i) for n, i in xobjects))
        page_ids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Resources %s /Contents %d 0 R >>"
                            % (pages_id, pw, ph, res, content_id)))
    objects[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % i for i in page_ids), len(page_ids))
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    with open(path, "wb") as f:
        f.write(out)
    return len(page_ids)


def captions(scene, strip, number):
    from . import status_label
    fps = scene.render.fps / scene.render.fps_base
    info = strip.plastron_panel
    head = f"{number}. {strip.name}   {status_label(strip)}   {clips.length(strip) / fps:.1f} s"
    lines = [head]
    note = getattr(info, "note", "")
    for chunk in (note, info.script_text):
        if chunk:
            lines += textwrap.wrap(chunk, 52)[:3]
    return lines


def export(scene, path):
    from . import panels_in_order
    from ..storyboard import panel_cache
    panel_cache.flush_now()                     # pictures up to date
    cells = [(_picture(s), captions(scene, s, i)) for i, s in enumerate(panels_in_order(scene), 1)]
    name = os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else "Storyboard"
    return write_pdf(path, cells, title=name)


class PLASTRON_OT_export_panel_sheet(bpy.types.Operator, ExportHelper):
    """Export every panel as a printable sheet (PDF), with its notes underneath"""
    bl_idname = "plastron.export_panel_sheet"
    bl_label = "Export Panel Sheet"
    filename_ext = ".pdf"
    filter_glob: bpy.props.StringProperty(default="*.pdf", options={'HIDDEN'})

    def execute(self, context):
        pages = export(context.scene, self.filepath)
        self.report({'INFO'}, f"Panel sheet saved ({pages} page{'s' if pages != 1 else ''}): {self.filepath}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(PLASTRON_OT_export_panel_sheet)


def unregister():
    bpy.utils.unregister_class(PLASTRON_OT_export_panel_sheet)
