"""跑流水线的辅助代码。

黄金样本测试要能在重构前后跑出**同一个结果**，所以这里把"怎么跑流水线"
收敛到一个函数里 —— 重构改变了入口时，只需要改这一个地方。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

#: 黄金测试自带的配置（和仓库根目录的 config.json 解耦：
#: 用户本地改根配置不会影响基线能否复现）
GOLDEN_CONFIG = Path(__file__).resolve().parents[1] / "golden" / "config.json"

#: 流水线跑完后应该出现的产物
CSV_RELPATH = Path("output") / "csv"
LITEMATIC_RELPATH = Path("output") / "litematic"


def run_pipeline(workdir: Path, image_path: Path, config_path: Path | None = None) -> str:
    """在 ``workdir`` 里跑一遍完整流水线，返回子进程的标准输出。

    ``image_path`` 会被放进 ``workdir/input_images/``；配置默认复制
    ``tests/golden/config.json``，这样流水线用的是一份干净的、可复制的配置。
    """
    workdir = Path(workdir)
    (workdir / "input_images").mkdir(parents=True, exist_ok=True)

    config = Path(config_path) if config_path else GOLDEN_CONFIG
    shutil.copyfile(config, workdir / "config.json")
    shutil.copyfile(image_path, workdir / "input_images" / image_path.name)

    proc = subprocess.run(
        [sys.executable, "-m", "pixelmatic", "convert"],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"流水线退出码 {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc.stdout


def find_output(workdir: Path, suffix: str) -> Path:
    """在 ``workdir`` 的输出目录里找到唯一的一个指定后缀文件。"""
    folder = CSV_RELPATH if suffix == ".csv" else LITEMATIC_RELPATH
    matches = sorted((Path(workdir) / folder).glob(f"*{suffix}"))
    if not matches:
        raise AssertionError(f"没有在 {folder} 下找到 *{suffix}")
    if len(matches) > 1:
        raise AssertionError(f"{folder} 下有多个 {suffix} 文件: {matches}")
    return matches[0]


def dump_blocks(litematic_path: Path) -> str:
    """把 .litematic 规范化成文本，用于逐格比对。

    只取方块内容，不含时间戳等元信息 —— 这样比对的是"作品"而不是"文件字节"。
    """
    from litemapy import Schematic

    schem = Schematic.load(str(litematic_path))
    lines: list[str] = []
    for name, region in schem.regions.items():
        for x, y, z in region.block_positions():
            block = region[x, y, z]
            lines.append(f"{name}\t{x}\t{y}\t{z}\t{block.id}")
    lines.sort()
    return "\n".join(lines) + ("\n" if lines else "")
