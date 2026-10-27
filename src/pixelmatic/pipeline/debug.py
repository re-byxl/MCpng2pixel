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
from .grid import GridInfo, aligned_crop, grid_options, read_image, save_image


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

    # 取色逻辑与主流程共用 mean_colors，避免两处各维护一份逐格均值
    # （延迟导入：match.py 也 import 本模块的 write_grid_debug，模块级导入会成环）
    from .match import mean_colors

    mean_grid, _ = mean_colors(crop, block_size, config.cell.margin)
    rgb = color.lab2rgb(mean_grid)  # (ny, nx, 3)，逐像素独立变换；空格子 Lab=0 → 黑
    rgb = np.repeat(np.repeat(rgb, block_size, axis=0), block_size, axis=1)
    preview = np.zeros_like(crop)
    preview[: rgb.shape[0], : rgb.shape[1]] = rgb * 255

    out_bgr = cv2.cvtColor(preview, cv2.COLOR_RGB2BGR)
    out_path = config.paths.color_debug / img_path.name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path if save_image(str(out_path), out_bgr) else None
