"""Litematic 方向转换工具的命令行 / 网页入口。

网页前端（默认）::

    python -m mcyqqs.tool

命令行批量转换::

    python -m mcyqqs.tool --cli
    python -m mcyqqs.tool --cli --target y --rotation 90
    python -m mcyqqs.tool --cli --replace red_concrete=red_terracotta
"""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser

from ..litematic.core import (
    TransformPlan,
    list_input_files,
    resolve_output_path,
    transform_file,
)
from . import PROJECT_ROOT, SETTINGS_FILENAME, resolve_path
from .server import _load_tool_settings, serve

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="mcyqqs.tool",
        description="Litematic 方向转换与方块替换工具。",
    )
    parser.add_argument("--cli", action="store_true", help="不启动网页，直接命令行批量转换。")
    parser.add_argument("--host", default=DEFAULT_HOST, help="网页监听地址。")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="网页监听端口。")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器。")
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径（默认 config.json 的 tool 节；也可以指向旧版的 litematic_tool.json）。",
    )

    parser.add_argument("--input", help="输入目录，覆盖配置。")
    parser.add_argument("--output", help="输出目录，覆盖配置。")
    parser.add_argument(
        "--target",
        choices=["keep", "x", "y", "z"],
        help="目标朝向：keep 保持 / x 侧面 / y 地面 / z 立面。",
    )
    parser.add_argument(
        "--source", choices=["auto", "x", "y", "z"], help="原图案所在平面，默认自动识别。"
    )
    parser.add_argument("--rotation", type=int, choices=[0, 90, 180, 270], help="平面内旋转角度。")
    parser.add_argument("--flip", action="store_true", help="水平镜像。")
    parser.add_argument("--flip-v", action="store_true", help="垂直镜像。")
    parser.add_argument("--rotate-x", type=int, choices=[0, 90, 180, 270], help="额外绕 X 旋转。")
    parser.add_argument("--rotate-y", type=int, choices=[0, 90, 180, 270], help="额外绕 Y 旋转。")
    parser.add_argument("--rotate-z", type=int, choices=[0, 90, 180, 270], help="额外绕 Z 旋转。")
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="旧=新",
        help="方块替换规则，可重复使用，例如 red_concrete=red_terracotta。",
    )
    parser.add_argument("--suffix", help="输出文件名后缀。")
    parser.add_argument("--keep-properties", action="store_true", help="替换时保留方块属性。")
    return parser.parse_args(argv)


def build_plan(args, base: dict) -> TransformPlan:
    """用命令行参数覆盖配置里的方向参数。"""
    plan = TransformPlan.from_dict(base)
    if args.source:
        plan.source_normal = args.source
    if args.target:
        plan.target_normal = args.target
    if args.rotation is not None:
        plan.rotation = args.rotation
    if args.flip:
        plan.mirror_h = True
    if args.flip_v:
        plan.mirror_v = True
    if args.rotate_x is not None:
        plan.rotate_x = args.rotate_x
    if args.rotate_y is not None:
        plan.rotate_y = args.rotate_y
    if args.rotate_z is not None:
        plan.rotate_z = args.rotate_z
    return plan


def parse_replace_rules(items: list[str]) -> dict[str, str]:
    """把 ``旧=新`` 形式的命令行参数解析成替换规则表。"""
    rules: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"替换规则格式应为 旧方块=新方块，收到: {item}")
        old, new = item.split("=", 1)
        rules[old.strip()] = new.strip()
    return rules


def run_cli(args) -> int:
    """命令行批量转换输入目录里的全部投影文件。"""
    config_path = args.config or str(PROJECT_ROOT / SETTINGS_FILENAME)
    settings = _load_tool_settings(config_path)

    input_dir = resolve_path(args.input or settings.get("input_dir", ""))
    output_dir = resolve_path(args.output or settings.get("output_dir", ""))
    plan = build_plan(args, settings.get("plan") or {})
    rules = dict(settings.get("replacements") or {})
    if args.replace:
        rules.update(parse_replace_rules(args.replace))
    suffix = args.suffix if args.suffix is not None else settings.get("suffix", "_transformed")
    keep_properties = args.keep_properties or bool(settings.get("keep_properties"))

    files = list_input_files(input_dir)
    if not files:
        print(f"输入目录里没有可处理的文件: {input_dir}")
        return 1

    os.makedirs(output_dir, exist_ok=True)
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print(
        f"方向: {plan.source_normal} → {plan.target_normal}，旋转 {plan.rotation}°"
        f"{'，水平镜像' if plan.mirror_h else ''}{'，垂直镜像' if plan.mirror_v else ''}"
    )
    if rules:
        print(f"替换规则: {rules}")
    print()

    failed = 0
    used: set[str] = set()
    for entry in files:
        out_path = resolve_output_path(output_dir, entry["path"], suffix, used)
        try:
            summary = transform_file(entry["path"], out_path, plan, rules, keep_properties)
            dims = summary["regions"][0]["dims"] if summary["regions"] else [0, 0, 0]
            print(
                f"[OK] {entry['name']} → {os.path.basename(out_path)}"
                f"  {dims[0]}x{dims[1]}x{dims[2]}"
            )
        except Exception as exc:
            failed += 1
            print(f"[ERR] {entry['name']}: {exc}")

    print()
    print(f"完成，共 {len(files) - failed}/{len(files)} 个文件。")
    return 1 if failed else 0


def run_server(args) -> int:
    """启动本地网页前端。"""
    url = f"http://{args.host}:{args.port}/"
    print(f"Litematic 工具: {url}")
    print("按 Ctrl+C 结束。")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    serve(args.host, args.port, args.config)
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.cli:
        return run_cli(args)
    return run_server(args)
