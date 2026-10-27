"""网格检测与图像对齐。

以前这些散在 ``grid_utils.py`` 里，靠模块级全局变量（``_block_size`` /
``_config`` / ``_grid_info``）传递状态；现在全部改成显式参数。

算法本身保持原样 —— 这是行为保持式重构，任何数值改动都会让黄金样本失效。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

#: Canny 边缘检测阈值（沿用原实现）
CANNY_LOW = 50
CANNY_HIGH = 150

#: 网格线的打分权重：线上亮度减去 0.35 倍的填充区亮度
LINE_PENALTY = 0.35


@dataclass(frozen=True)
class GridOptions:
    """网格检测的参数。"""

    block_size: int
    min_block: int = 6
    center_ratio: float = 0.45
    smooth_window: int = 9
    shift_radius: int = 4


@dataclass
class GridInfo:
    """一次网格检测的结果，用于诊断输出。"""

    img_name: str = "unknown"
    block_size: int = 0
    original_size: tuple[int, int] | None = None
    cropped_size: tuple[int, int] | None = None
    anchor_x: int = 0
    anchor_y: int = 0
    grid_cells_x: int = 0
    grid_cells_y: int = 0
    discarded_left: int = 0
    discarded_right: int = 0
    discarded_top: int = 0
    discarded_bottom: int = 0


# --------------------------------------------------------------------------- #
# 图像读写
# --------------------------------------------------------------------------- #


def read_image(path: str) -> np.ndarray | None:
    """读图片；带 alpha 的会把透明区域合成成黑色。"""
    try:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.shape[2] == 4:
            alpha = img[:, :, 3]
            mask = alpha > 10
            img = img[:, :, :3]
            if not mask.any():
                return None
            img = cv2.bitwise_and(img, img, mask=mask.astype(np.uint8) * 255)
        return img
    except Exception as exc:  # noqa: BLE001
        print(f"  [ERR] 读取异常: {path}, 错误: {exc}")
        return None


def save_image(path: str, img: np.ndarray) -> bool:
    """按扩展名存图。"""
    return _encode(path, img)


def save_png(path: str, img: np.ndarray) -> bool:
    """存 PNG。"""
    return _encode(path, img, ext=".png")


def _encode(path: str, img: np.ndarray, ext: str | None = None) -> bool:
    try:
        suffix = ext or (path[path.rfind(".") :] if "." in path else ".png")
        ok, encoded = cv2.imencode(suffix, img)
        if ok:
            encoded.tofile(path)
            return True
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  [ERR] 保存失败: {path}, 错误: {exc}")
        return False


# --------------------------------------------------------------------------- #
# 网格对齐
# --------------------------------------------------------------------------- #


def crop_like_original(img: np.ndarray) -> np.ndarray | None:
    """按 Canny 边缘的包围盒裁掉图片外围。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)

    coords = cv2.findNonZero(edges)
    if coords is None:
        return None

    x, y, w, h = cv2.boundingRect(coords)
    return img[y : y + h, x : x + w]


def smooth_signal(signal: np.ndarray, window: int = 9) -> np.ndarray:
    """滑动平均（保持峰值位置不变）。"""
    if signal.size == 0:
        return signal
    window = min(window, signal.size)
    if window < 3:
        return signal.astype(np.float32)
    if window % 2 == 0:
        window += 1
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(signal, kernel, mode="same")


def gradient_signal(gray: np.ndarray, axis: int, window: int = 9) -> np.ndarray:
    """沿某个轴求梯度的平均强度，归一化到 0..1。"""
    dx = 1 if axis == 1 else 0
    dy = 1 if axis == 0 else 0
    grad = cv2.Sobel(gray, cv2.CV_32F, dx, dy, ksize=3)
    signal = np.mean(np.abs(grad), axis=1 - axis)
    signal = smooth_signal(signal, window)
    signal -= signal.min()
    peak = signal.max()
    if peak > 0:
        signal /= peak
    return signal


def best_offset(signal: np.ndarray, block: int) -> int:
    """找出网格线相位：让每隔 block 取样到的都是强梯度。"""
    if signal.size < block * 2:
        return 0

    scores = []
    for offset in range(block):
        indices = np.arange(offset, len(signal), block)
        if len(indices) < 2:
            scores.append(-1.0)
            continue
        line_strength = float(signal[indices].mean())
        mask = np.ones(len(signal), dtype=bool)
        mask[indices] = False
        fill_strength = float(signal[mask].mean()) if mask.any() else 0.0
        scores.append(line_strength - LINE_PENALTY * fill_strength)
    return int(np.argmax(scores))


def grid_score(gray: np.ndarray, block: int, x_offset: int, y_offset: int) -> float:
    """给一个候选相位打分（沿用原实现：偏好更亮的网格线）。"""
    h, w = gray.shape
    if h < block * 2 or w < block * 2:
        return -1.0

    x_lines = np.arange(x_offset, w, block)
    y_lines = np.arange(y_offset, h, block)
    if len(x_lines) < 2 or len(y_lines) < 2:
        return -1.0

    x_strength = float(np.mean([gray[:, x].mean() for x in x_lines]))
    y_strength = float(np.mean([gray[y, :].mean() for y in y_lines]))

    x_fill_mask = np.ones(w, dtype=bool)
    y_fill_mask = np.ones(h, dtype=bool)
    x_fill_mask[x_lines] = False
    y_fill_mask[y_lines] = False

    x_fill = float(gray[:, x_fill_mask].mean()) if x_fill_mask.any() else 0.0
    y_fill = float(gray[y_fill_mask, :].mean()) if y_fill_mask.any() else 0.0
    return (x_strength - LINE_PENALTY * x_fill) + (y_strength - LINE_PENALTY * y_fill)


def refine_offsets(
    crop: np.ndarray, block: int, x_offset: int, y_offset: int, shift_radius: int
) -> tuple[int, int]:
    """在相位附近做 +/-shift_radius 的精细搜索。"""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    best = (x_offset, y_offset)
    best_score = -1.0
    for dx in range(-shift_radius, shift_radius + 1):
        for dy in range(-shift_radius, shift_radius + 1):
            trial_x = (x_offset + dx) % block
            trial_y = (y_offset + dy) % block
            score = grid_score(gray, block, trial_x, trial_y)
            if score > best_score:
                best_score = score
                best = (trial_x, trial_y)
    return best


def center_window(crop: np.ndarray, options: GridOptions) -> tuple[int, int, np.ndarray]:
    """取图片中央的一块区域，用来估计网格相位。"""
    h, w = crop.shape[:2]
    ch = max(options.min_block * 6, int(round(h * options.center_ratio)))
    cw = max(options.min_block * 6, int(round(w * options.center_ratio)))
    ch = min(ch, h)
    cw = min(cw, w)

    y0 = (h - ch) // 2
    x0 = (w - cw) // 2
    return x0, y0, crop[y0 : y0 + ch, x0 : x0 + cw]


def expand_lines(anchor: int, block: int, limit: int) -> list[int]:
    """从锚点向两侧铺开网格线。"""
    lines = [anchor]

    pos = anchor - block
    while pos > 0:
        lines.append(pos)
        pos -= block

    pos = anchor + block
    while pos < limit:
        lines.append(pos)
        pos += block

    lines = sorted(set(lines))

    if lines and lines[0] > 0:
        lines.insert(0, 0)
    if lines and lines[-1] < limit:
        lines.append(limit)

    return sorted(set(lines))


def aligned_bounds(lines: list[int], limit: int, block: int) -> tuple[int, int] | None:
    """把网格线换算成对齐后的裁剪范围。"""
    inner = [v for v in lines if 0 <= v <= limit]
    if len(inner) < 2:
        return None

    start = int(inner[0])
    end = int(inner[-1])
    usable = end - start
    cells = usable // block
    if cells <= 0:
        return None
    return start, start + cells * block


def aligned_crop(
    img: np.ndarray, options: GridOptions, img_name: str = "unknown"
) -> tuple[np.ndarray | None, GridInfo]:
    """把图片裁剪并对齐到网格。

    返回 ``(对齐后的图片, 检测信息)``；失败时图片为 ``None``。
    """
    block = options.block_size
    info = GridInfo(img_name=img_name, block_size=block)

    orig_h, orig_w = img.shape[:2]
    info.original_size = (orig_w, orig_h)

    crop = crop_like_original(img)
    if crop is None or crop.size == 0:
        return None, info

    crop_h, crop_w = crop.shape[:2]
    info.cropped_size = (crop_w, crop_h)

    center_x, center_y, center_crop = center_window(crop, options)
    center_gray = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
    center_x_signal = gradient_signal(center_gray, axis=1, window=options.smooth_window)
    center_y_signal = gradient_signal(center_gray, axis=0, window=options.smooth_window)

    anchor_x = center_x + best_offset(center_x_signal, block)
    anchor_y = center_y + best_offset(center_y_signal, block)
    anchor_x, anchor_y = refine_offsets(
        crop, block, anchor_x % block, anchor_y % block, options.shift_radius
    )

    info.anchor_x = anchor_x
    info.anchor_y = anchor_y

    x_lines = expand_lines(anchor_x, block, crop_w)
    y_lines = expand_lines(anchor_y, block, crop_h)
    x_bounds = aligned_bounds(x_lines, crop_w, block)
    y_bounds = aligned_bounds(y_lines, crop_h, block)
    if x_bounds is None or y_bounds is None:
        return None, info

    x0, x1 = x_bounds
    y0, y1 = y_bounds
    aligned = crop[y0:y1, x0:x1]
    if aligned.size == 0:
        return None, info

    aligned_h, aligned_w = aligned.shape[:2]
    info.grid_cells_x = aligned_w // block
    info.grid_cells_y = aligned_h // block

    info.discarded_left = x0
    info.discarded_right = crop_w - x1
    info.discarded_top = y0
    info.discarded_bottom = crop_h - y1

    return aligned, info


def iter_cells(img: np.ndarray, block: int):
    """按行优先遍历格子，产出 (列, 行, x0, y0, x1, y1)。"""
    h, w = img.shape[:2]
    ny = h // block
    nx = w // block
    for iy in range(ny):
        for ix in range(nx):
            y0 = iy * block
            x0 = ix * block
            yield ix, iy, x0, y0, x0 + block, y0 + block


# --------------------------------------------------------------------------- #
# 方块大小
# --------------------------------------------------------------------------- #


def parse_grid_cells(grid_cells: str | int | None) -> tuple[int | None, int | None]:
    """解析 ``grid_cells`` 配置，返回 (目标列数, 目标行数)。"""
    if grid_cells in ("auto", None):
        return None, None
    if isinstance(grid_cells, int):
        return grid_cells, grid_cells

    parts = str(grid_cells).split("x")
    if len(parts) == 1:
        value = int(parts[0])
        return value, value
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    return None, None


def find_dividable_size(img_width: int, img_height: int, target_size: int, min_block: int) -> int:
    """从 target_size 往下找能同时整除宽高的最大值。"""
    size = target_size
    while size >= min_block:
        if img_width % size == 0 and img_height % size == 0:
            return size
        size -= 1
    return min_block


def auto_blocksize(
    img_width: int,
    img_height: int,
    grid_cells_x: int | None,
    grid_cells_y: int | None,
    min_block: int,
    default_size: int = 30,
) -> int:
    """按目标格子数估算方块大小。"""
    if img_width <= 0 or img_height <= 0:
        return default_size

    if grid_cells_x is None or grid_cells_y is None:
        grid_cells_x = 64
        grid_cells_y = 64

    cw = max(1, img_width // grid_cells_x)
    ch = max(1, img_height // grid_cells_y)
    size = max(min_block, min(cw, ch))

    return find_dividable_size(img_width, img_height, size, min_block)
