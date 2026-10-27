"""后处理：把背景黑色换成空气，保留前景黑色和 1 格描边。

背景的判定是「从图片四边出发、只穿过黑色格子能到达的黑色格子」。
黑色但被前景隔开的（比如瞳孔）会被保留。
"""

from __future__ import annotations

import csv
from collections import deque
from pathlib import Path

BLACK_BLOCK = "black_concrete"
AIR_BLOCK = "air"

#: 四邻域
NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))

#: CSV 的表头（与 pipeline.match 共用同一套格式）
CSV_HEADER = ("x", "y", "block")


def read_cells(csv_path: str | Path) -> list[tuple[int, int, str]]:
    """读方块清单。"""
    cells: list[tuple[int, int, str]] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cells.append((int(row["x"]), int(row["y"]), row["block"].strip()))
    return cells


def write_cells(csv_path: str | Path, cells: list[tuple[int, int, str]]) -> None:
    """写方块清单（换行固定用 ``\\n``，不跟随平台）。"""
    with open(csv_path, "w", newline="\n", encoding="utf-8-sig") as f:
        f.write(",".join(CSV_HEADER) + "\n")
        for x, y, block in cells:
            f.write(f"{x},{y},{block}\n")


def bfs_from_edges(black_cells: set[tuple[int, int]], nx: int, ny: int) -> set[tuple[int, int]]:
    """BFS 从四边出发，标记所有与边框相连的黑色格子。"""
    visited: set[tuple[int, int]] = set()
    background: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    for x in range(nx):
        if (x, 0) in black_cells:
            queue.append((x, 0))
        if (x, ny - 1) in black_cells:
            queue.append((x, ny - 1))
    for y in range(ny):
        if (0, y) in black_cells:
            queue.append((0, y))
        if (nx - 1, y) in black_cells:
            queue.append((nx - 1, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in visited:
            continue
        visited.add((x, y))
        if (x, y) in black_cells:
            background.add((x, y))
            for dx, dy in NEIGHBORS:
                nx2 = x + dx
                ny2 = y + dy
                if 0 <= nx2 < nx and 0 <= ny2 < ny and (nx2, ny2) not in visited:
                    queue.append((nx2, ny2))

    return background


def compute_distance_to_foreground(
    grid: dict[tuple[int, int], str], nx: int, ny: int
) -> dict[tuple[int, int], int]:
    """多源 BFS：每个格子到最近前景的曼哈顿距离。"""
    dist: dict[tuple[int, int], int] = {}
    queue: deque[tuple[int, int]] = deque()

    for y in range(ny):
        for x in range(nx):
            if (x, y) in grid and grid[(x, y)] != BLACK_BLOCK:
                dist[(x, y)] = 0
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        for dx, dy in NEIGHBORS:
            nx2 = x + dx
            ny2 = y + dy
            if 0 <= nx2 < nx and 0 <= ny2 < ny and (nx2, ny2) not in dist:
                dist[(nx2, ny2)] = dist[(x, y)] + 1
                queue.append((nx2, ny2))

    return dist


def process_cells(cells: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """对一份方块清单做后处理，返回处理后的清单。"""
    if not cells:
        return cells

    max_x = max(c[0] for c in cells) + 1
    max_y = max(c[1] for c in cells) + 1

    grid = {(x, y): name for x, y, name in cells}
    black_cells = {(x, y) for x, y, name in cells if name == BLACK_BLOCK}

    if not black_cells:
        return cells

    background = bfs_from_edges(black_cells, max_x, max_y)
    if not background:
        return cells

    dist = compute_distance_to_foreground(grid, max_x, max_y)

    result = []
    for x, y, name in cells:
        if name == BLACK_BLOCK and (x, y) in background:
            d = dist.get((x, y), float("inf"))
            result.append((x, y, name if d == 1 else AIR_BLOCK))
        else:
            result.append((x, y, name))
    return result


def process_csv(csv_path: str | Path) -> bool:
    """就地处理一个 CSV 清单，返回是否真的改动了。"""
    cells = read_cells(csv_path)
    if not cells:
        return False

    processed = process_cells(cells)
    if processed == cells:
        return False

    write_cells(csv_path, processed)
    return True
