"""诊断视图：网格叠加图、每格平均色预览、网格参数日志。

这几个视图**不参与**主流程的产出，只是用来肉眼检查
"网格切得对不对" 和 "取色取得准不准"。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from skimage import color

from ..config import AppConfig
from .grid import GridInfo, GridOptions, aligned_crop, iter_cells, read_image, save_image


def write_grid_debug(debug_dir: Path, info: GridInfo) -> Path:
    """把一次网格检测的数追加到 ``grid_debug.txt``。"""
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / "grid_debug.txt"
    original = info.original_size or (0, 0)
    cropped = info.cropped_size or (0, 0)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"图片: {info.img_name}\n")
        f.write(f"{'=' * 60}\n")
        f.write(f"  原始图像: {original[0]}x{original[1]}\n")
        f.write(f"  Canny裁剪后: {cropped[0]}x{cropped[1]}\n")
        f.write(f"  方块大小: {info.block_size} 像素\n")
        f.write(f"  网格锚点偏移: anchor_x={info.anchor_x}, anchor_y={info.anchor_y}\n")
        f.write(f"  网格覆盖范围: {info.grid_cells_x}x{info.grid_cells_y} 格\n")
        f.write(
            f"  丢弃像素: 左{info.discarded_left} 右{info.discarded_right} "
            f"上{info.discarded_top} 下{info.discarded_bottom}\n"
        )
    return path


def grid_options(config: AppConfig, block_size: int) -> GridOptions:
    """从配置拼出网格检测参数。"""
    return GridOptions(
        block_size=block_size,
        min_block=config.grid.min_block,
        center_ratio=config.grid.center_ratio,
        smooth_window=config.grid.smooth_window,
        shift_radius=config.grid.shift_radius,
    )


def draw_grid(img: np.ndarray, block: int) -> np.ndarray:
    """在图上画出网格线。"""
    vis = img.copy()
    h, w = vis.shape[:2]

    for x in range(0, w + 1, block):
        xx = min(x, w - 1)
        cv2.line(vis, (xx, 0), (xx, h - 1), (0, 255, 0), 1)
    for y in range(0, h + 1, block):
        yy = min(y, h - 1)
        cv2.line(vis, (0, yy), (w - 1, yy), (0, 255, 0), 1)

    return vis


def annotate(vis: np.ndarray, block: int) -> np.ndarray:
    """在图上标出方块大小和格子数。"""
    cells_x = vis.shape[1] // block
    cells_y = vis.shape[0] // block
    label = f"block={block}, cells={cells_x}x{cells_y}"
    cv2.putText(
        vis,
        label,
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return vis


def render_grid_overlay(config: AppConfig, img_path: Path, block_size: int) -> Path | None:
    """网格叠加图。"""
    img = read_image(str(img_path))
    if img is None:
        return None

    crop, info = aligned_crop(img, grid_options(config, block_size), img_name=img_path.name)
    write_grid_debug(config.paths.debug_dir, info)
    if crop is None:
        return None

    vis = annotate(draw_grid(crop, block_size), block_size)
    out_path = config.paths.grid_output_dir / img_path.name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path if save_image(str(out_path), vis) else None


def render_color_preview(config: AppConfig, img_path: Path, block_size: int) -> Path | None:
    """每格平均色预览（方块匹配之前的"参考图"）。"""
    img = read_image(str(img_path))
    if img is None:
        return None

    crop, info = aligned_crop(img, grid_options(config, block_size), img_name=img_path.name)
    write_grid_debug(config.paths.debug_dir, info)
    if crop is None:
        return None

    margin = config.cell.margin
    lab = color.rgb2lab(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) / 255.0)
    preview = np.zeros_like(crop)

    for _, _, x0, y0, x1, y1 in iter_cells(crop, block_size):
        inner = lab[y0 + margin : y1 - margin, x0 + margin : x1 - margin]
        if inner.size == 0:
            continue
        mean_lab = inner.mean(axis=(0, 1))
        rgb_mean = color.lab2rgb(mean_lab.reshape(1, 1, 3))[0, 0] * 255
        preview[y0:y1, x0:x1] = rgb_mean

    out_bgr = cv2.cvtColor(preview, cv2.COLOR_RGB2BGR)
    out_path = config.paths.color_debug / img_path.name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path if save_image(str(out_path), out_bgr) else None
