"""方块匹配阶段：把图片的每个格子匹配成一种方块，产出 CSV 清单和预览图。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from skimage import color

from ..config import AppConfig
from ..matching.energy import build_palette_index, optimize_assignments
from ..matching.palette import palette_names, palette_rgb
from .debug import write_grid_debug
from .grid import GridInfo, GridOptions, aligned_crop, iter_cells, read_image, save_png

#: CSV 的表头，读取和写入共用一个定义
CSV_HEADER = ("x", "y", "block")


@dataclass
class MatchResult:
    """一次匹配的结果。"""

    image: str
    csv_path: Path | None = None
    preview_path: Path | None = None
    cells: int = 0
    error: str | None = None
    info: GridInfo | None = None


def mean_colors(crop: np.ndarray, block: int, margin: int) -> tuple[np.ndarray, np.ndarray]:
    """每个格子的平均颜色，以及有效像素数。

    返回 ``(mean_grid, pixel_count_grid)``，两者都是 float32/int32。
    """
    h, w = crop.shape[:2]
    ny = h // block
    nx = w // block

    lab = color.rgb2lab(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) / 255.0)
    mean_grid = np.zeros((ny, nx, 3), dtype=np.float32)
    pixel_count_grid = np.zeros((ny, nx), dtype=np.int32)

    for ix, iy, x0, y0, x1, y1 in iter_cells(crop, block):
        inner = lab[y0 + margin : y1 - margin, x0 + margin : x1 - margin]
        if inner.size == 0:
            continue
        mean_grid[iy, ix] = inner.mean(axis=(0, 1))
        pixel_count_grid[iy, ix] = inner.shape[0] * inner.shape[1]

    return mean_grid, pixel_count_grid


def write_csv(path: Path, rows: list[tuple[int, int, str]]) -> None:
    """写方块清单（x, y, block）。

    换行固定用 ``\\n``，不跟随平台 —— 这样同一张图在任何系统上产出的文件都一样。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8-sig") as f:
        f.write(",".join(CSV_HEADER) + "\n")
        for x, y, block in rows:
            f.write(f"{x},{y},{block}\n")


def process_image(
    config: AppConfig,
    img_path: Path,
    block_size: int,
    params,
    palette=None,
) -> MatchResult:
    """匹配一张图片，产出 CSV 与预览图。"""
    result = MatchResult(image=img_path.name)
    img = read_image(str(img_path))
    if img is None:
        result.error = "图片读取失败"
        return result

    options = GridOptions(
        block_size=block_size,
        min_block=config.grid.min_block,
        center_ratio=config.grid.center_ratio,
        smooth_window=config.grid.smooth_window,
        shift_radius=config.grid.shift_radius,
    )
    crop, info = aligned_crop(img, options, img_name=img_path.name)
    write_grid_debug(config.paths.debug_dir, info)
    result.info = info
    if crop is None:
        result.error = "没能对齐出完整网格"
        return result

    mean_grid, pixel_count_grid = mean_colors(crop, block_size, config.cell.margin)

    if palette is None:
        palette = build_palette_index(palette_names(), np.array(palette_rgb()))
    names = palette.names

    chosen_idx = optimize_assignments(
        mean_grid,
        palette,
        params,
        config.blue_penalty,
        config.neutral_mask,
        pixel_count_grid > 0,
    )

    rgb_palette = np.array(palette_rgb()) / 255.0
    preview = np.zeros_like(crop)
    table: list[tuple[int, int, str]] = []

    for ix, iy, x0, y0, x1, y1 in iter_cells(crop, block_size):
        if pixel_count_grid[iy, ix] == 0:
            continue
        idx = int(chosen_idx[iy, ix])
        if idx < 0:
            continue
        name = names[idx]
        rgb = (rgb_palette[idx] * 255).astype(np.uint8)
        preview[y0:y1, x0:x1] = rgb[::-1]
        table.append((ix, iy, name))

    stem = img_path.stem
    preview_path = config.paths.output_preview / f"{stem}.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if not save_png(str(preview_path), preview):
        result.error = f"预览图保存失败: {preview_path}"

    csv_path = config.paths.output_csv / f"{stem}.csv"
    write_csv(csv_path, table)

    result.csv_path = csv_path
    result.preview_path = preview_path
    result.cells = len(table)
    return result
