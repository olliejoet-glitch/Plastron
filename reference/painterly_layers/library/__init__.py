"""Texture library (Phase 5, ARCHITECTURE §27): scan folders for texture sets, thumbnails, and
import a set onto a Fill layer (downscaled to 2048 and packed; the originals are never touched).
"""
import os
import re
import tempfile

import bpy
import bpy.utils.previews

ROOT_PKG = __package__.rpartition(".")[0]
DEFAULT_FOLDER = r"C:\Art\Tools\My_Textures"
MAX_RES = 2048
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr", ".webp", ".bmp"}

COLOR_TOKENS = {"albedo", "basecolor", "basecolour", "base", "color", "colour", "diffuse", "diff", "col",
                "alb", "bc"}
HEIGHT_TOKENS = {"height", "displacement", "displace", "disp", "heightmap"}
OTHER_TOKENS = {"normal", "nrm", "nor", "norm", "normalgl", "normaldx", "roughness", "rough", "rgh",
                "ao", "ambientocclusion", "occlusion", "metallic", "metalness", "metal", "met", "spec",
                "specular", "gloss", "glossiness", "opacity", "alpha", "mask", "emissive", "emission",
                "bump", "cavity", "curvature", "translucency", "sss", "arm", "orm", "id", "preview",
                "thumb", "thumbnail", "sphere", "cube"}
NOISE_TOKENS = re.compile(r"^(\d+k|\d{3,5}(px)?|\d+x\d+|v\d+|lod\d+|var\d+|gl|dx|png|jpg)$")
KEYWORDS = [  # filename keyword -> category, first match wins (when there's no subfolder)
    ("Rock", ("rock", "stone", "cliff", "boulder", "pebble", "gravel", "granite", "marble", "slate")),
    ("Soil", ("soil", "dirt", "mud", "earth", "clay", "dust")),
    ("Sand", ("sand", "beach", "dune")),
    ("Bark", ("bark", "trunk")),
    ("Wood", ("wood", "plank", "timber")),
    ("Moss", ("moss", "lichen")),
    ("Ground", ("ground", "forest", "floor", "terrain")),
    ("Plants", ("grass", "leaf", "leaves", "foliage", "plant")),
    ("Skin", ("skin", "scale", "scales", "leather", "hide", "reptile", "shell")),
    ("Fabric", ("fabric", "cloth", "textile")),
    ("Metal", ("metal", "rust", "iron", "steel")),
    ("Snow & Ice", ("snow", "ice", "frost")),
    ("Concrete", ("concrete", "plaster", "brick", "asphalt", "tile")),
]

TEST_FOLDERS = []          # tests point the library here (the add-on isn't enabled as an add-on there)
_index = {"key": None, "sets": []}
_previews = None


class TexSet:
    __slots__ = ("key", "name", "category", "color", "height", "folder")

    def __init__(self, key, name, category, color, height, folder):
        self.key, self.name, self.category = key, name, category
        self.color, self.height, self.folder = color, height, folder


# ----------------------------------------------------------------------------- folders & scan

def prefs():
    addon = bpy.context.preferences.addons.get(ROOT_PKG)
    return addon.preferences if addon is not None else None


def folders():
    if TEST_FOLDERS:
        return list(TEST_FOLDERS)
    p = prefs()
    out = [f.path for f in p.library_folders if f.path.strip()] if p is not None else []
    if not out and os.path.isdir(DEFAULT_FOLDER):
        out = [DEFAULT_FOLDER]
    return [bpy.path.abspath(f) for f in out]


def _tokens(stem):
    return [t for t in re.split(r"[\s_\-.()\[\]]+", stem.lower()) if t]


def _map_type(tokens):
    """COLOR / HEIGHT / OTHER from the last meaningful token (suffix), or None (no map suffix)."""
    for t in reversed(tokens):
        if NOISE_TOKENS.match(t):
            continue
        if t in COLOR_TOKENS:
            return "COLOR"
        if t in HEIGHT_TOKENS:
            return "HEIGHT"
        if t in OTHER_TOKENS:
            return "OTHER"
        return None
    return None


def _set_name(tokens):
    """The name with map and resolution suffixes removed."""
    keep = list(tokens)
    while keep and (NOISE_TOKENS.match(keep[-1]) or keep[-1] in COLOR_TOKENS | HEIGHT_TOKENS | OTHER_TOKENS):
        keep.pop()
    return " ".join(keep) or " ".join(tokens)


def category_for(rel_dir, name):
    """Subfolder first (the top folder under the library root), filename keywords as fallback."""
    parts = [p for p in rel_dir.replace("\\", "/").split("/") if p and p != "."]
    if parts:
        return parts[0].replace("_", " ").title()
    words = set(_tokens(name))
    for cat, keys in KEYWORDS:
        if any(k in words or any(w.startswith(k) for w in words) for k in keys):
            return cat
    return "Other"


def scan(force=False):
    """Index every texture set in the library folders (cached until the folders change)."""
    roots = folders()
    stamp = tuple((r, _tree_mtime(r)) for r in roots)
    if not force and _index["key"] == stamp:
        return _index["sets"]
    sets, explicit = {}, set()
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            rel = os.path.relpath(dirpath, root)
            for f in sorted(files):
                stem, ext = os.path.splitext(f)
                if ext.lower() not in IMAGE_EXT:
                    continue
                toks = _tokens(stem)
                kind = _map_type(toks)
                if kind == "OTHER":
                    continue
                name = _set_name(toks)
                key = os.path.join(dirpath, name).lower()
                s = sets.get(key)
                if s is None:
                    s = sets[key] = TexSet(key, name.title(), category_for(rel, name), None, None, dirpath)
                path = os.path.join(dirpath, f)
                if kind == "HEIGHT":
                    s.height = s.height or path
                elif kind == "COLOR":                 # an explicit colour map wins ...
                    if key not in explicit:
                        s.color = path
                        explicit.add(key)
                elif s.color is None:                 # ... over an unsuffixed image
                    s.color = path
    out = sorted((s for s in sets.values() if s.color), key=lambda s: (s.category, s.name))
    _index["key"], _index["sets"] = stamp, out
    return out


def _tree_mtime(root):
    try:
        m = os.path.getmtime(root)
        for dirpath, dirs, _files in os.walk(root):
            for d in dirs:
                m = max(m, os.path.getmtime(os.path.join(dirpath, d)))
        return m
    except OSError:
        return 0


def find(key):
    return next((s for s in scan() if s.key == key), None)


def categories():
    return sorted({s.category for s in scan()})


def filtered(search="", category="ALL"):
    words = _tokens(search)
    out = []
    for s in scan():
        if category not in ("ALL", "") and s.category != category:
            continue
        hay = f"{s.name} {s.category}".lower()
        if all(w in hay for w in words):
            out.append(s)
    return out


# ----------------------------------------------------------------------------- thumbnails

def icon(s):
    return icon_for_path(s.color, s.key)


def icon_for_path(path, key=None):
    """Thumbnail icon of an image file (generated lazily by Blender; 0 in background mode)."""
    global _previews
    if bpy.app.background:
        return 0
    if _previews is None:
        _previews = bpy.utils.previews.new()
    key = key or path
    item = _previews.get(key) or _previews.load(key, path, 'IMAGE')
    return item.icon_id


def free_previews():
    global _previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None


# ----------------------------------------------------------------------------- import

def load_image(path, non_color=False, label=None):
    """The library image as a packed datablock, downscaled to MAX_RES (largest side). Reused if the
    same file (and modification time) was imported before."""
    mtime = os.path.getmtime(path)
    for img in bpy.data.images:
        if img.get("pl_lib_src") == path and abs(img.get("pl_lib_mtime", -1) - mtime) < 1e-3:
            return img
    src = bpy.data.images.load(path, check_existing=False)
    if non_color:
        src.colorspace_settings.name = "Non-Color"
    w, h = src.size
    img = src
    tmp = None
    if max(w, h) > MAX_RES:
        k = MAX_RES / max(w, h)
        src.scale(max(1, round(w * k)), max(1, round(h * k)))
        # packing a loaded image packs the FILE (full size): save the scaled pixels and pack those
        tmp = os.path.join(tempfile.gettempdir(), "pl_lib_" + os.path.basename(path).rsplit(".", 1)[0] + ".png")
        src.save(filepath=tmp)
        bpy.data.images.remove(src)
        img = bpy.data.images.load(tmp, check_existing=False)
        if non_color:
            img.colorspace_settings.name = "Non-Color"
    img.pack()
    if tmp is not None:
        try:
            os.remove(tmp)
        except OSError:
            pass
    base = os.path.basename(path)
    # unpacking writes next to the .blend, never over the original texture
    img.filepath = "//pl_library/" + (base if tmp is None else base.rsplit(".", 1)[0] + ".png")
    img.name = label or base
    img["pl_lib_src"] = path
    img["pl_lib_mtime"] = mtime
    img["pl_owned"] = True
    return img
