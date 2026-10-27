"""``pixelmatic`` 命令行入口。

子命令：

- ``convert``  图片 -> 方块清单 -> .litematic（主流程）
- ``debug``    网格叠加图 / 每格平均色预览（诊断用）
- ``tool``     方向转换与方块替换的网页前端
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import AppConfig, load_config

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


# --------------------------------------------------------------------------- #
# 参数
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pixelmatic",
        description="把图片转换成 Minecraft 方块投影。",
    )
    parser.add_argument("--config", default=None, help="配置文件路径（默认 config.json）。")
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="图片 -> 方块清单 -> .litematic")
    convert.add_argument("--mode", default=None, help="匹配模式，会覆盖配置文件。")
    convert.add_argument("--skip-litematic", action="store_true", help="跳过 .litematic 生成。")
    convert.add_argument("--skip-postprocess", action="store_true", help="跳过背景黑色后处理。")
    convert.add_argument("--block-size", type=int, default=None, help="方块大小（像素）。")
    convert.add_argument("--grid-cells", default=None, help="目标网格格子数，如 '64' 或 '64x48'。")
    convert.add_argument("--input", default=None, help="输入图片目录，覆盖配置。")
    convert.add_argument("--output", default=None, help="输出目录，覆盖配置。")

    debug = sub.add_parser("debug", help="诊断视图")
    debug.add_argument(
        "view", choices=["grid", "color"], help="grid=网格叠加图，color=每格平均色预览"
    )
    debug.add_argument("--block-size", type=int, default=None, help="方块大小（像素）。")
    debug.add_argument("--input", default=None, help="输入图片目录，覆盖配置。")

    # tool 子命令的参数定义只有一份，在 tool/cli.py 里维护
    from .tool.cli import build_parser as build_tool_parser

    sub.add_parser(
        "tool",
        help="方向转换与方块替换工具",
        parents=[build_tool_parser(add_help=False)],
    )

    return parser


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #


def list_images(input_dir: Path) -> list[Path]:
    """输入目录里的图片，按文件名排序。"""
    if not input_dir.is_dir():
        return []
    return sorted(
        p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def resolve_block_size(config: AppConfig, block_size: int | None = None) -> int:
    """决定用多大的方块。

    ``--block-size`` > 配置文件 > ``auto``（按图片尺寸和目标格子数估算）。
    """
    from .pipeline.grid import auto_blocksize, crop_like_original, parse_grid_cells, read_image

    if block_size is not None:
        return block_size
    if config.block_size != "auto":
        return int(config.block_size)

    images = list_images(config.paths.input_dir)
    if not images:
        return 30

    img = read_image(str(images[0]))
    if img is None:
        return 30

    orig_h, orig_w = img.shape[:2]
    crop = crop_like_original(img)
    if crop is not None:
        crop_h, crop_w = crop.shape[:2]
    else:
        crop_w, crop_h = orig_w, orig_h

    cells_x, cells_y = parse_grid_cells(config.grid_cells)
    size = auto_blocksize(crop_w, crop_h, cells_x, cells_y, config.grid.min_block, default_size=30)
    print(f"自动计算方块大小: {size}（裁剪后图像 {crop_w}x{crop_h}，目标网格 {config.grid_cells}）")
    return size


def _apply_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    """把命令行参数覆盖到配置上。"""
    if getattr(args, "mode", None):
        config.mode = args.mode
    if getattr(args, "skip_litematic", False):
        config.skip_litematic = True
    if getattr(args, "skip_postprocess", False):
        config.skip_postprocess = True
    if getattr(args, "grid_cells", None):
        config.grid_cells = args.grid_cells
    if getattr(args, "input", None):
        config.paths.input_dir = Path(args.input)
    if getattr(args, "output", None):
        base = Path(args.output)
        config.paths.output_csv = base / "csv"
        config.paths.output_preview = base / "preview"
        config.paths.output_litematic = base / "litematic"
    return config


# --------------------------------------------------------------------------- #
# convert
# --------------------------------------------------------------------------- #


def run_convert(args: argparse.Namespace, config: AppConfig) -> int:
    import numpy as np

    from .matching.energy import build_palette_index
    from .matching.modes import describe_mode, get_match_mode
    from .matching.palette import palette_names, palette_rgb
    from .pipeline.debug import render_color_preview, render_grid_overlay
    from .pipeline.export import csv_to_litematic
    from .pipeline.match import process_image
    from .pipeline.postprocess import process_csv

    config = _apply_overrides(config, args)

    try:
        params = get_match_mode(config.mode)
    except ValueError as exc:
        print(f"[ERR] {exc}")
        return 1

    print(f"Pipeline mode: {config.mode} - {describe_mode(config.mode)}")

    input_dir = config.paths.input_dir
    images = list_images(input_dir)
    if not images:
        print(f"[ERR] 输入目录里没有图片: {input_dir}")
        return 1

    block_size = resolve_block_size(config, args.block_size)
    print(f"方块大小: {block_size} 像素")

    # 调色板预计算只做一次，所有图共用
    palette = build_palette_index(palette_names(), np.array(palette_rgb()))

    failures = 0
    for index, image_path in enumerate(images, 1):
        print(f"[{index}/{len(images)}] 处理 {image_path.name}")

        # 诊断视图（网格叠加图 + 每格平均色）
        render_grid_overlay(config, image_path, block_size)
        render_color_preview(config, image_path, block_size)

        result = process_image(config, image_path, block_size, params, palette)
        if result.error:
            print(f"  [ERR] {image_path.name}: {result.error}")
            failures += 1
            continue
        print(f"  [OK] {result.cells} 个方块 -> {result.csv_path}")

    # 后处理：把背景黑色换成空气
    if not config.skip_postprocess:
        for csv_path in sorted(config.paths.output_csv.glob("*.csv")):
            if process_csv(csv_path):
                print(f"  [OK] 后处理: {csv_path.name}")
    else:
        print("跳过背景黑色后处理")

    # 导出 .litematic
    if not config.skip_litematic:
        for csv_path in sorted(config.paths.output_csv.glob("*.csv")):
            out_path = config.paths.output_litematic / f"{csv_path.stem}.litematic"
            try:
                csv_to_litematic(csv_path, out_path)
                print(f"  [OK] 生成投影: {out_path.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [ERR] 生成投影失败 {csv_path.name}: {exc}")
                failures += 1
    else:
        print("跳过 .litematic 生成")

    if failures:
        print(f"[ERR] 有 {failures} 张图片处理失败")
        return 1
    print("[OK] 全流程完成")
    return 0


# --------------------------------------------------------------------------- #
# debug
# --------------------------------------------------------------------------- #


def run_debug(args: argparse.Namespace, config: AppConfig) -> int:
    from .pipeline.debug import render_color_preview, render_grid_overlay

    config = _apply_overrides(config, args)
    input_dir = config.paths.input_dir
    images = list_images(input_dir)
    if not images:
        print(f"[ERR] 输入目录里没有图片: {input_dir}")
        return 1

    block_size = resolve_block_size(config, args.block_size)
    renderer = render_grid_overlay if args.view == "grid" else render_color_preview
    for index, image_path in enumerate(images, 1):
        print(f"[{index}/{len(images)}] {image_path.name}")
        out = renderer(config, image_path, block_size)
        if out is None:
            print(f"  [ERR] {image_path.name} 处理失败")
        else:
            print(f"  [OK] {out}")
    return 0


# --------------------------------------------------------------------------- #
# tool
# --------------------------------------------------------------------------- #


def run_tool(args: argparse.Namespace, config: AppConfig) -> int:
    # 参数已经在同一套解析器里解析好了（tool/cli.py 的 build_parser 作为父解析器），
    # 直接分派即可 —— 顶层 --config 也不会再丢
    from .tool.cli import run as tool_run

    return tool_run(args)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    # 库层的诊断日志走 stderr；CLI 自己的进度/摘要输出仍是 print（stdout）
    logging.basicConfig(level=logging.WARNING)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] 配置文件有问题: {exc}")
        return 1

    if args.command == "convert":
        return run_convert(args, config)
    if args.command == "debug":
        return run_debug(args, config)
    if args.command == "tool":
        return run_tool(args, config)
    parser.error(f"未知命令: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
