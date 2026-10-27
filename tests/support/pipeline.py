"""跑流水线的辅助代码。

黄金样本测试要能在重构前后跑出**同一个结果**，所以这里把"怎么跑流水线"
收敛到一个函数里 —— 重构改变了入口时，只需要改这一个地方。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 流水线跑完后应该出现的产物
CSV_RELPATH = Path("output") / "csv"
LITEMATIC_RELPATH = Path("output") / "litematic"

#: 旧的扁平布局下，main.py 用相对路径加载这些脚本，所以要一起复制到临时目录
LEGACY_SCRIPTS = (
    "main.py",
    "1grid.py",
    "2color.py",
    "3match.py",
    "3postprocess.py",
    "4litematic.py",
    "grid_utils.py",
    "match_modes.py",
    "palette.py",
)


def has_new_api() -> bool:
    """重构后的 ``mcyqqs`` 包是否已经可用。"""
    return importlib.util.find_spec("mcyqqs") is not None


def _command(workdir: Path) -> list[str]:
    if has_new_api():
        return [sys.executable, "-m", "mcyqqs", "convert"]
    return [sys.executable, str(PROJECT_ROOT / "main.py")]


def run_pipeline(workdir: Path, image_path: Path, config_path: Path | None = None) -> str:
    """在 ``workdir`` 里跑一遍完整流水线，返回子进程的标准输出。

    ``image_path`` 会被放进 ``workdir/input_images/``；``config.json`` 会被复制到
    ``workdir``，这样流水线用的是一份干净的、可复制的配置。
    """
    workdir = Path(workdir)
    (workdir / "input_images").mkdir(parents=True, exist_ok=True)

    config = Path(config_path) if config_path else PROJECT_ROOT / "config.json"
    shutil.copyfile(config, workdir / "config.json")
    shutil.copyfile(image_path, workdir / "input_images" / image_path.name)

    if not has_new_api():
        # 旧版 main.py 按 cwd 找同级的步骤脚本
        for name in LEGACY_SCRIPTS:
            shutil.copyfile(PROJECT_ROOT / name, workdir / name)

    env = dict(os.environ)
    # 旧的扁平布局下，流水线脚本靠 cwd 找同级模块
    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT), env.get("PYTHONPATH", "")]).rstrip(
        os.pathsep
    )

    proc = subprocess.run(
        _command(workdir),
        cwd=str(workdir),
        env=env,
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
    sys.path.insert(0, str(PROJECT_ROOT))
    from litemapy import Schematic

    schem = Schematic.load(str(litematic_path))
    lines: list[str] = []
    for name, region in schem.regions.items():
        for x, y, z in region.block_positions():
            block = region[x, y, z]
            lines.append(f"{name}\t{x}\t{y}\t{z}\t{block.id}")
    lines.sort()
    return "\n".join(lines) + ("\n" if lines else "")
