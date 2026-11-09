"""The value groups: four greys, remembered in Plastron's settings; set by
hand, or sampled from a picture / the panel being drawn (its brightness
split into four groups, k-means)."""

import numpy as np

from ...config import values as cfg
from ...core import user_settings

KEY = "value_groups"


def get():
    raw = user_settings.get(KEY)
    if not raw or len(raw) != cfg.COUNT:
        return list(cfg.DEFAULT_GROUPS)
    return [float(v) for v in raw]


def put(groups):
    groups = sorted(max(0.0, min(1.0, float(v))) for v in groups)
    user_settings.set(KEY, groups)
    for func in CHANGED:
        func(groups)
    return groups


CHANGED = []          # func(groups) when they change (the Values view follows)


def luminance(rgb):
    """Brightness as seen (sRGB values in, 0-1 out)."""
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def k_groups(values, k=cfg.COUNT, iterations=40):
    """k 1-D cluster centres of values (sorted)."""
    v = np.asarray(values, np.float64).ravel()
    if v.size == 0:
        return list(cfg.DEFAULT_GROUPS)
    centres = np.quantile(v, (np.arange(k) + 0.5) / k)
    for _ in range(iterations):
        nearest = np.argmin(np.abs(v[:, None] - centres[None, :]), axis=1)
        new = np.array([v[nearest == i].mean() if np.any(nearest == i) else centres[i] for i in range(k)])
        if np.allclose(new, centres, atol=1e-5):
            break
        centres = new
    return sorted(float(c) for c in centres)


def srgb(linear):
    linear = np.clip(linear, 0, 1)
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)


def linear(s):
    s = np.clip(np.asarray(s, np.float64), 0, 1)
    return np.where(s <= 0.04045, s / 12.92, np.power((s + 0.055) / 1.055, 2.4))


def from_pixels(rgba, is_linear=False):
    """Value groups of a picture's pixels (RGBA, any shape ...×4). 8-bit
    pictures' pixels come as shown (sRGB); float ones linear (is_linear)."""
    px = np.asarray(rgba, np.float32).reshape(-1, 4)
    px = px[px[:, 3] > 0.5]                       # (see-through parts don't count)
    rgb = srgb(px[:, :3]) if is_linear else px[:, :3]
    return k_groups(luminance(rgb))


def thresholds(groups):
    """Where one group ends and the next begins (midway, as seen)."""
    return [(a + b) / 2 for a, b in zip(groups, groups[1:])]
