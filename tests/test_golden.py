"""黄金样本回归测试。

这是整个重构的"不变性证明"：只要这些断言还绿，就说明流水线对同一张图的
输出（方块清单 + 最终投影的每一格）没有变。

基线文件在 ``tests/golden/`` 下，用 ``python tests/generate_baseline.py`` 重新生成。
**只有在明确知道自己在改行为时才应该重新生成基线。**
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _read(golden_dir: Path, name: str, encoding: str = "utf-8") -> str:
    path = golden_dir / name
    if not path.exists():
        pytest.fail(f"缺少基线文件 {path}，请运行 python tests/generate_baseline.py 生成")
    return path.read_text(encoding=encoding)


def test_csv_matches_baseline(pipeline_output, golden_dir):
    """方块清单逐字节一致。"""
    csv_text, _ = pipeline_output
    expected = _read(golden_dir, "grid_sample.csv", encoding="utf-8-sig")
    assert csv_text == expected, "方块清单与基线不一致（流水线行为发生了变化）"


def test_blocks_match_baseline(pipeline_output, golden_dir):
    """最终 .litematic 的每一格方块都一致。"""
    _, blocks = pipeline_output
    expected = _read(golden_dir, "grid_sample.blocks.txt")
    assert blocks == expected, "投影方块与基线不一致（流水线行为发生了变化）"


def test_baseline_is_not_empty(pipeline_output):
    """基线本身不能是空的 —— 否则"一致"毫无意义。"""
    csv_text, blocks = pipeline_output
    assert csv_text.strip(), "流水线没有产出任何方块"
    assert blocks.strip(), "投影里没有任何方块"
    assert len(csv_text.splitlines()) > 10, "方块数量异常地少"
