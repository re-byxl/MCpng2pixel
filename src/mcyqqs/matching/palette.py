"""方块调色板。

调色板是**数据**，不是代码：存在同目录的 ``palette.json`` 里，
由 ``tools/palette_extract.py`` 从材质图采样生成。

这里返回的是有序 dict —— **顺序即调色板索引**，直接决定匹配结果的
索引编号，所以加载顺序必须稳定（json 保留插入顺序）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PALETTE_FILE = Path(__file__).with_name("palette.json")


@lru_cache(maxsize=1)
def load_palette() -> dict[str, tuple[int, int, int]]:
    """读取调色板，返回 ``{方块名: (r, g, b)}``。"""
    raw = json.loads(_PALETTE_FILE.read_text(encoding="utf-8"))
    return {name: tuple(rgb) for name, rgb in raw["blocks"].items()}


@lru_cache(maxsize=1)
def palette_names() -> tuple[str, ...]:
    """调色板里的方块名，顺序与索引一致。"""
    return tuple(load_palette())


@lru_cache(maxsize=1)
def palette_rgb() -> tuple[tuple[int, int, int], ...]:
    """调色板的 RGB 数组，顺序与索引一致。"""
    return tuple(load_palette().values())


#: 兼容旧写法：``from .palette import MC_BLOCKS``
MC_BLOCKS = load_palette()
