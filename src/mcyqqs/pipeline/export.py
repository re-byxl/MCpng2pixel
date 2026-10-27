"""导出：把方块清单转成 .litematic 投影文件。

坐标约定（和 ``3match.py`` 生成的 CSV 一致）：
- CSV 的 ``x`` 是列号（0 = 最左），``y`` 是行号（**0 = 图片最上面一行**）
- Minecraft 的 Y 轴向上，所以写进区域时要把行号翻转：``y_mc = max_y - 1 - y``
- 区域厚度为 1，法线朝 Z —— 也就是"贴墙"的画
"""

from __future__ import annotations

from pathlib import Path

from litemapy import BlockState, Region, Schematic

from .postprocess import read_cells


def build_region(cells: list[tuple[int, int, str]]) -> Region:
    """把方块清单变成一个 1 层厚的立面区域。"""
    max_x = max(c[0] for c in cells) + 1
    max_y = max(c[1] for c in cells) + 1

    region = Region(0, 0, 0, max_x, max_y, 1)
    for x, y, name in cells:
        block_id = name if ":" in name else f"minecraft:{name}"
        region[x, max_y - 1 - y, 0] = BlockState(block_id)
    return region


def csv_to_litematic(csv_path: str | Path, out_path: str | Path) -> Path:
    """把 CSV 清单转成 .litematic。"""
    cells = read_cells(csv_path)
    if not cells:
        raise ValueError(f"CSV 里没有方块数据: {csv_path}")

    schematic = Schematic(name=Path(csv_path).stem)
    schematic.regions["main"] = build_region(cells)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    schematic.save(str(out))
    return out
