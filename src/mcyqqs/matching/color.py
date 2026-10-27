"""颜色科学工具：调色板 -> Lab，以及 CIEDE2000 色差。

调色板里存的是 sRGB，匹配时统一转到 CIELAB 再算色差（CIEDE2000）。
"""

from __future__ import annotations

import numpy as np
from skimage import color
from skimage.color import deltaE_ciede2000


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB（0..255 或 0..1 的浮点数组）-> CIELAB。"""
    values = np.asarray(rgb, dtype=np.float64)
    if values.max(initial=0.0) > 1.0:
        values = values / 255.0
    return color.rgb2lab(values.reshape(-1, 1, 3)).reshape(-1, 3)


def palette_lab(palette_rgb: np.ndarray) -> np.ndarray:
    """整个调色板的 Lab，形状 (N, 3)。"""
    return rgb_to_lab(palette_rgb)


def chroma_of(lab: np.ndarray) -> np.ndarray:
    """Lab 的彩度 C = sqrt(a^2 + b^2)。"""
    return np.sqrt(lab[..., 1] ** 2 + lab[..., 2] ** 2)


def delta_e(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 色差。

    ``lab1`` / ``lab2`` 是 (..., 3) 的 Lab，输出形状为 (...,)。
    """
    a = np.asarray(lab1)
    b = np.asarray(lab2)
    if a.ndim == 2 and b.ndim == 2:
        return deltaE_ciede2000(a, b)
    return deltaE_ciede2000(a, b, channel_axis=-1)
