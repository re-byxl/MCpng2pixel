"""
后处理脚本：删除背景黑色，保留前景黑色和描边
"""
import csv
import os
from collections import deque

BLACK_BLOCK = "black_concrete"
AIR_BLOCK = "air"

CSV_DIR = "output/csv"


def bfs_from_edges(black_cells, nx, ny):
    """BFS 从四边出发，标记所有与边框相连的黑色格子"""
    visited = set()
    background = set()
    queue = deque()

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
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx2, ny2 = x + dx, y + dy
                if 0 <= nx2 < nx and 0 <= ny2 < ny and (nx2, ny2) not in visited:
                    queue.append((nx2, ny2))

    return background


def compute_distance_to_foreground(grid, nx, ny):
    """多源 BFS 计算每个格子到最近前景的曼哈顿距离"""
    dist = {}
    queue = deque()

    for y in range(ny):
        for x in range(nx):
            if (x, y) in grid and grid[(x, y)] != BLACK_BLOCK:
                dist[(x, y)] = 0
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx2, ny2 = x + dx, y + dy
            if 0 <= nx2 < nx and 0 <= ny2 < ny and (nx2, ny2) not in dist:
                dist[(nx2, ny2)] = dist[(x, y)] + 1
                queue.append((nx2, ny2))

    return dist


def process_csv(csv_path):
    """处理单个 CSV 文件"""
    cells = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cells.append((int(r["x"]), int(r["y"]), r["block"].strip()))

    if not cells:
        return

    max_x = max(c[0] for c in cells) + 1
    max_y = max(c[1] for c in cells) + 1

    grid = {(x, y): name for x, y, name in cells}
    black_cells = {(x, y) for x, y, name in cells if name == BLACK_BLOCK}

    if not black_cells:
        return

    background = bfs_from_edges(black_cells, max_x, max_y)

    if not background:
        return

    dist = compute_distance_to_foreground(grid, max_x, max_y)

    result = []
    for x, y, name in cells:
        if name == BLACK_BLOCK and (x, y) in background:
            d = dist.get((x, y), float('inf'))
            if d == 1:
                result.append((x, y, name))
            else:
                result.append((x, y, AIR_BLOCK))
        else:
            result.append((x, y, name))

    with open(csv_path, "w", encoding="utf-8-sig") as f:
        f.write("x,y,block\n")
        for row in result:
            f.write(f"{row[0]},{row[1]},{row[2]}\n")


def main():
    if not os.path.exists(CSV_DIR):
        print(f"未找到目录: {CSV_DIR}")
        return 1

    files = [f for f in os.listdir(CSV_DIR) if f.lower().endswith(".csv")]
    if not files:
        print(f"未找到 CSV 文件")
        return 0

    for f in files:
        csv_path = os.path.join(CSV_DIR, f)
        process_csv(csv_path)
        print(f"  [OK] 处理完成: {f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
