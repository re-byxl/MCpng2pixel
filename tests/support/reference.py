"""生成黄金样本用的确定性参考图。

刻意不引用项目里的调色板：参考图的颜色写死在这里，这样即使调色板变了，
黄金样本也只会因为"匹配结果变了"而失败（这正是它该做的事），
而不会因为"生成器的输入变了"而静默失效。

图案设计：
- 整幅不透明，尺寸恰好是整数个方格，避免网格对齐出现歧义。
- 外圈是 ``black_concrete`` 的颜色（会被 3postprocess 当作背景清掉），
  但左上角留一个彩色格子，让 Canny 的包围盒覆盖整幅图 —— 这样外圈黑块
  才会落在裁剪结果里，后处理这条路径才真的被覆盖到。
"""

from __future__ import annotations

import numpy as np

#: 格子边长（像素），与 config.json 里的 block_size 一致
CELL = 9
COLS = 24
ROWS = 16

#: black_concrete 的 RGB，用于制造会被后处理清除的背景黑块
BLACK = (18, 21, 28)

#: 内部使用的颜色，取自当前调色板，混合了冷暖与明暗
COLORS: tuple[tuple[int, int, int], ...] = (
    (234, 240, 243),  # snow_block
    (196, 204, 207),  # white_concrete
    (161, 60, 60),  # red_concrete
    (212, 99, 15),  # orange_concrete
    (227, 169, 34),  # yellow_concrete
    (95, 164, 37),  # lime_concrete
    (77, 94, 48),  # green_concrete
    (30, 119, 137),  # cyan_concrete
    (42, 135, 193),  # light_blue_concrete
    (50, 54, 143),  # blue_concrete
    (100, 40, 155),  # purple_concrete
    (162, 55, 157),  # magenta_concrete
    (202, 103, 143),  # pink_concrete
    (97, 65, 43),  # brown_concrete
    (123, 124, 118),  # light_gray_concrete
    (59, 64, 70),  # gray_concrete
)


def cell_color(x: int, y: int) -> tuple[int, int, int]:
    """按坐标确定性地给出颜色（BGR 顺序，与 cv2 一致）。"""
    # 外圈是背景黑，但左上角留一个彩色格子，把包围盒撑到整幅图
    on_border = x in (0, COLS - 1) or y in (0, ROWS - 1)
    if on_border and not (x == 0 and y == 0):
        return BLACK
    return COLORS[(x * 7 + y * 13) % len(COLORS)]


def build_image() -> np.ndarray:
    """返回 BGR 图像，形状 (ROWS*CELL, COLS*CELL, 3)。"""
    img = np.zeros((ROWS * CELL, COLS * CELL, 3), dtype=np.uint8)
    for y in range(ROWS):
        for x in range(COLS):
            b, g, r = cell_color(x, y)
            # 内部再切一刀小色块，让格子内部也有结构（更接近真实像素画）
            if 2 <= x < COLS - 2 and 2 <= y < ROWS - 2 and (x + y) % 5 == 0:
                b, g, r = min(255, b + 40), min(255, g + 40), min(255, r + 40)
            img[y * CELL : (y + 1) * CELL, x * CELL : (x + 1) * CELL] = (b, g, r)
    return img


def write_reference(path: str) -> str:
    """把参考图写到 ``path``（PNG）。"""
    import cv2

    ok, encoded = cv2.imencode(".png", build_image())
    if not ok:
        raise RuntimeError("参考图编码失败")
    encoded.tofile(path)
    return path
