"""Reads the brush tips in Photoshop brush files (.abr).

Supports versions 1, 2 (old) and 6+ (sampled tips in the "samp" section),
following GIMP's reader. Computed (round) brushes and tool presets are
skipped: only sampled tips have a shape worth importing.

read(path) -> [(name, width, height, bytes)] with 8-bit grey rows, top row
first, 255 = full paint.
"""

import os
import struct


class AbrError(Exception):
    pass


class _Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise AbrError("file ends early")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self):
        return self.take(1)[0]

    def i16(self):
        return struct.unpack(">h", self.take(2))[0]

    def i32(self):
        return struct.unpack(">i", self.take(4))[0]

    def utf16(self):
        n = self.i32()
        return self.take(2 * n).decode("utf-16-be", "replace").rstrip("\0")


def _rle(r, height):
    """PackBits rows (each row's byte count listed first)."""
    lengths = [r.i16() & 0xFFFF for _ in range(height)]
    out = bytearray()
    for length in lengths:
        end = r.pos + length
        while r.pos < end:
            n = r.u8()
            if n >= 128:
                n -= 256
            if n < 0:
                if n == -128:
                    continue
                out += bytes([r.u8()]) * (1 - n)
            else:
                out += r.take(n + 1)
    return bytes(out)


def _sample(r, depth, compressed, width, height):
    if width <= 0 or height <= 0 or width * height > 1 << 26:
        raise AbrError(f"odd brush size {width}x{height}")
    step = max(1, depth // 8)
    size = width * height * step
    data = _rle(r, height * step) if compressed else r.take(size)
    if len(data) < size:
        raise AbrError("brush data too short")
    if step > 1:
        data = data[0:size:step]        # 16-bit: keep the high byte
    return data[:width * height]


def _v12(r, version, stem):
    count = r.i16()
    tips = []
    for _ in range(count):
        kind = r.i16()
        size = r.i32()
        nxt = r.pos + size
        if kind == 2:
            r.i32()                      # misc
            r.i16()                      # spacing
            name = r.utf16() if version == 2 else ""
            r.u8()                       # antialias
            r.take(8)                    # short bounds
            top, left, bottom, right = (r.i32() for _ in range(4))
            depth = r.i16()
            compressed = r.u8()
            w, h = right - left, bottom - top
            tips.append((name or f"{stem} {len(tips) + 1}", w, h, _sample(r, depth, compressed, w, h)))
        r.pos = nxt
    return tips


def _find_section(r, key):
    while r.pos + 12 <= len(r.data):
        sig, name = r.take(4), r.take(4)
        if sig != b"8BIM":
            raise AbrError("not a Photoshop brush file")
        size = r.i32()
        if name == key:
            return size
        r.pos += size + (size % 2)
    return None


def _v6(r, subversion, stem):
    size = _find_section(r, b"samp")
    if size is None:
        return []
    end = r.pos + size
    tips = []
    while r.pos < end:
        length = r.i32()
        nxt = r.pos + length + (-length % 4)
        r.pos += 47 if subversion == 1 else 301
        top, left, bottom, right = (r.i32() for _ in range(4))
        depth = r.i16()
        compressed = r.u8()
        w, h = right - left, bottom - top
        tips.append((f"{stem} {len(tips) + 1}", w, h, _sample(r, depth, compressed, w, h)))
        r.pos = nxt
    return tips


def read(path):
    with open(path, "rb") as f:
        r = _Reader(f.read())
    stem = os.path.splitext(os.path.basename(path))[0]
    version = r.i16()
    if version in (1, 2):
        return _v12(r, version, stem)
    if version >= 6:
        return _v6(r, r.i16(), stem)
    raise AbrError(f"unknown brush file version {version}")


def _packbits_row(row):
    out, i = bytearray(), 0
    while i < len(row):
        run = 1
        while i + run < len(row) and run < 128 and row[i + run] == row[i]:
            run += 1
        if run > 2:
            out += bytes([257 - run, row[i]])
            i += run
        else:
            chunk = row[i:i + 128]
            out += bytes([len(chunk) - 1]) + chunk
            i += len(chunk)
    return bytes(out)


def write_v6(path, tips, compressed=False):
    """A minimal version 6 file: used by the tests."""
    body = bytearray()
    for _name, w, h, data in tips:
        if compressed:
            rows = [_packbits_row(data[y * w:(y + 1) * w]) for y in range(h)]
            pixels = b"".join(struct.pack(">h", len(row)) for row in rows) + b"".join(rows)
        else:
            pixels = data
        brush = bytearray(47) + struct.pack(">iiii", 0, 0, h, w) + \
            struct.pack(">hB", 8, 1 if compressed else 0) + pixels
        body += struct.pack(">i", len(brush)) + brush + bytes(-len(brush) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack(">hh", 6, 1) + b"8BIMsamp" + struct.pack(">i", len(body)) + body)
