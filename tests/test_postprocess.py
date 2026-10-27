"""后处理（背景黑色清除）的单元测试。

这条路径在端到端流水线里不容易被稳定触发（取决于网格对齐得好不好），
所以单独用手工构造的网格来测。
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from support import legacy

BLACK = "black_concrete"
AIR = "air"
WHITE = "white_concrete"

# 5x5 的网格，外圈全黑，中间 3x3 是白色（正中一个黑点，像瞳孔）
GRID = [
    [BLACK, BLACK, BLACK, BLACK, BLACK],
    [BLACK, WHITE, WHITE, WHITE, BLACK],
    [BLACK, WHITE, BLACK, WHITE, BLACK],
    [BLACK, WHITE, WHITE, WHITE, BLACK],
    [BLACK, BLACK, BLACK, BLACK, BLACK],
]


def _write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        f.write("x,y,block\n")
        for y, row in enumerate(GRID):
            for x, name in enumerate(row):
                f.write(f"{x},{y},{name}\n")


def _read_csv(path: Path) -> dict[tuple[int, int], str]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {(int(r["x"]), int(r["y"])): r["block"].strip() for r in csv.DictReader(f)}


@pytest.fixture()
def postprocess():
    return legacy.load("3postprocess.py")


def test_background_black_is_removed(postprocess, tmp_path):
    """与边框相连的黑块变成空气。"""
    csv_path = tmp_path / "grid.csv"
    _write_csv(csv_path)

    postprocess.process_csv(str(csv_path))
    cells = _read_csv(csv_path)

    # 四个角离前景最远（曼哈顿距离 2），被清掉
    for corner in ((0, 0), (4, 0), (0, 4), (4, 4)):
        assert cells[corner] == AIR, f"角落 {corner} 应该被清成空气"


def test_outline_is_kept(postprocess, tmp_path):
    """紧贴前景的那一圈黑块要保留（描边）。"""
    csv_path = tmp_path / "grid.csv"
    _write_csv(csv_path)

    postprocess.process_csv(str(csv_path))
    cells = _read_csv(csv_path)

    # 上边中间那一格紧挨着白色前景 → 保留
    assert cells[(2, 0)] == BLACK
    assert cells[(1, 1)] == WHITE


def test_foreground_black_is_kept(postprocess, tmp_path):
    """前景内部的黑色（瞳孔）不能被误删。"""
    csv_path = tmp_path / "grid.csv"
    _write_csv(csv_path)

    postprocess.process_csv(str(csv_path))
    cells = _read_csv(csv_path)

    assert cells[(2, 2)] == BLACK, "前景内部的黑色不应被清除"


def test_no_black_no_change(postprocess, tmp_path):
    """图里没有黑色时，文件不该被改动。"""
    csv_path = tmp_path / "grid.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        f.write("x,y,block\n0,0,white_concrete\n")

    before = csv_path.read_bytes()
    postprocess.process_csv(str(csv_path))
    assert csv_path.read_bytes() == before
