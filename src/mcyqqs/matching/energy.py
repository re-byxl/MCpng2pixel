"""匹配目标函数与求解器。

思路：
1. **一元项** —— 每个格子在自己的候选方块里挑"颜色最接近"的那个。
2. **成对项** —— 让相邻格子之间的*对比度大小*贴近原图里的对比度，
   而不是简单地把相邻格子弄成一样（那样会糊掉边缘）。
3. 用 ICM（迭代条件模式）逐轮改进：一轮里按棋盘格顺序更新，
   每个格子在 top_k 个候选里挑让总能量最小的。

数学与原实现完全一致，只是把散落的模块级全局变量换成了显式参数。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import BluePenaltyConfig, MatchParams, NeutralMaskConfig
from .color import chroma_of, delta_e, palette_lab

#: 四邻域，顺序与原实现一致
NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass
class PaletteIndex:
    """调色板的预计算结果。"""

    names: tuple[str, ...]
    lab: np.ndarray  # (N, 3)
    chroma: np.ndarray  # (N,)
    delta: np.ndarray  # (N, N) 方块之间的色差
    purple_indices: np.ndarray
    pink_indices: np.ndarray

    @property
    def size(self) -> int:
        return len(self.names)


def build_palette_index(names: tuple[str, ...], rgb: np.ndarray) -> PaletteIndex:
    """预计算调色板的 Lab、彩度、方块间色差。"""
    lab = palette_lab(rgb)
    chroma = chroma_of(lab)
    delta = delta_e(lab[:, None, :], lab[None, :, :])
    purple = np.array([i for i, n in enumerate(names) if "purple" in n or "magenta" in n])
    pink = np.array([i for i, n in enumerate(names) if "pink" in n])
    return PaletteIndex(
        names=names,
        lab=lab,
        chroma=chroma,
        delta=delta,
        purple_indices=purple,
        pink_indices=pink,
    )


def candidate_indices(
    lab: np.ndarray,
    palette: PaletteIndex,
    params: MatchParams,
    blue_penalty: BluePenaltyConfig,
    neutral_mask: NeutralMaskConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """给一个格子算所有方块的得分，返回 (最优的 top_k 个索引, 全部得分)。"""
    lab = lab.reshape(1, 3)
    base = delta_e(palette.lab, lab)
    lightness_gap = np.abs(palette.lab[:, 0] - lab[0, 0])
    source_chroma = float(chroma_of(lab)[0])
    chroma_gap = np.abs(palette.chroma - source_chroma)

    score = base + params.lightness_weight * lightness_gap + params.chroma_weight * chroma_gap

    if neutral_mask.enabled and source_chroma >= params.pastel_chroma_threshold:
        is_neutral = palette.chroma <= params.neutral_chroma_threshold
        chroma_loss = np.maximum(0.0, source_chroma - palette.chroma)
        score = score + is_neutral * chroma_loss * params.chroma_loss_weight

    if lab[0, 2] < blue_penalty.threshold_b:
        score[palette.purple_indices] += blue_penalty.penalty_purple
        score[palette.pink_indices] += blue_penalty.penalty_pink

    order = np.argsort(score)
    return order[: params.top_k], score


def compute_detail_weight(
    mean_grid: np.ndarray, valid_grid: np.ndarray | None = None
) -> np.ndarray:
    """每个格子与四邻域的平均色差，归一化到 0..1 —— 细节越强的格子权重越高。"""
    ny, nx, _ = mean_grid.shape
    detail = np.zeros((ny, nx), dtype=np.float32)
    for iy in range(ny):
        for ix in range(nx):
            if valid_grid is not None and not valid_grid[iy, ix]:
                continue
            center = mean_grid[iy, ix]
            acc = 0.0
            count = 0
            for dx, dy in NEIGHBORS:
                nx2 = ix + dx
                ny2 = iy + dy
                if 0 <= nx2 < nx and 0 <= ny2 < ny:
                    if valid_grid is not None and not valid_grid[ny2, nx2]:
                        continue
                    diff = float(
                        delta_e(center.reshape(1, 3), mean_grid[ny2, nx2].reshape(1, 3))[0]
                    )
                    acc += diff
                    count += 1
            if count:
                detail[iy, ix] = acc / count
    if detail.max() > 0:
        detail /= detail.max()
    return detail


def build_neighbor_graph(
    mean_grid: np.ndarray, valid_grid: np.ndarray | None = None
) -> dict[tuple[int, int], list[tuple[int, int, float]]]:
    """每个格子的有效四邻域，带上原图里这两个格子的色差。"""
    ny, nx, _ = mean_grid.shape
    graph: dict[tuple[int, int], list[tuple[int, int, float]]] = {}
    for iy in range(ny):
        for ix in range(nx):
            if valid_grid is not None and not valid_grid[iy, ix]:
                continue
            edges = []
            for dx, dy in NEIGHBORS:
                nx2 = ix + dx
                ny2 = iy + dy
                if 0 <= nx2 < nx and 0 <= ny2 < ny:
                    if valid_grid is not None and not valid_grid[ny2, nx2]:
                        continue
                    src_diff = float(
                        delta_e(
                            mean_grid[iy, ix].reshape(1, 3),
                            mean_grid[ny2, nx2].reshape(1, 3),
                        )[0]
                    )
                    edges.append((nx2, ny2, src_diff))
            graph[(ix, iy)] = edges
    return graph


def initialize_assignments(
    mean_grid: np.ndarray,
    palette: PaletteIndex,
    params: MatchParams,
    blue_penalty: BluePenaltyConfig,
    neutral_mask: NeutralMaskConfig,
    valid_grid: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[tuple[int, int], list[int]], np.ndarray]:
    """给每个格子挑最优方块作为初值。"""
    ny, nx, _ = mean_grid.shape
    unary_scores = np.full((ny, nx, palette.size), np.inf, dtype=np.float32)
    candidate_map: dict[tuple[int, int], list[int]] = {}
    chosen_idx = np.full((ny, nx), -1, dtype=np.int32)

    for iy in range(ny):
        for ix in range(nx):
            if valid_grid is not None and not valid_grid[iy, ix]:
                continue
            mean = mean_grid[iy, ix]
            indices, scores = candidate_indices(mean, palette, params, blue_penalty, neutral_mask)
            unary_scores[iy, ix] = scores.astype(np.float32)
            candidate_map[(ix, iy)] = [int(v) for v in indices]
            chosen_idx[iy, ix] = int(indices[0])

    return unary_scores, candidate_map, chosen_idx


def local_energy(
    ix: int,
    iy: int,
    candidate_idx: int,
    chosen_idx: np.ndarray,
    unary_scores: np.ndarray,
    neighbor_graph: dict[tuple[int, int], list[tuple[int, int, float]]],
    detail_map: np.ndarray,
    palette: PaletteIndex,
    params: MatchParams,
) -> float:
    """一个格子换成某个方块后的总能量。"""
    score = float(unary_scores[iy, ix, candidate_idx])
    detail_scale = 1.0 + params.detail_weight * float(detail_map[iy, ix])

    for nx2, ny2, src_diff in neighbor_graph[(ix, iy)]:
        neighbor_idx = int(chosen_idx[ny2, nx2])
        if neighbor_idx < 0:
            continue

        palette_diff = float(palette.delta[candidate_idx, neighbor_idx])
        edge_scale = 1.0 + params.edge_weight * min(src_diff, 20.0) / 20.0
        score += params.contrast_weight * edge_scale * abs(palette_diff - src_diff) * detail_scale

        if candidate_idx == neighbor_idx and src_diff > params.repeat_threshold:
            score += params.repeat_penalty * edge_scale * min(src_diff, 20.0) / 20.0

    return score


def optimize_assignments(
    mean_grid: np.ndarray,
    palette: PaletteIndex,
    params: MatchParams,
    blue_penalty: BluePenaltyConfig,
    neutral_mask: NeutralMaskConfig,
    valid_grid: np.ndarray | None = None,
) -> np.ndarray:
    """迭代条件模式（ICM）求解，返回每个格子选中的调色板索引。"""
    unary_scores, candidate_map, chosen_idx = initialize_assignments(
        mean_grid, palette, params, blue_penalty, neutral_mask, valid_grid
    )
    detail_map = compute_detail_weight(mean_grid, valid_grid)
    neighbor_graph = build_neighbor_graph(mean_grid, valid_grid)

    for _ in range(params.iterations):
        changed = False
        for parity in (0, 1):
            for iy in range(mean_grid.shape[0]):
                for ix in range(mean_grid.shape[1]):
                    if (ix + iy) % 2 != parity:
                        continue
                    if (ix, iy) not in candidate_map:
                        continue

                    current = int(chosen_idx[iy, ix])
                    best = current
                    best_score = local_energy(
                        ix,
                        iy,
                        current,
                        chosen_idx,
                        unary_scores,
                        neighbor_graph,
                        detail_map,
                        palette,
                        params,
                    )

                    for candidate_idx in candidate_map[(ix, iy)]:
                        if candidate_idx == current:
                            continue
                        score = local_energy(
                            ix,
                            iy,
                            candidate_idx,
                            chosen_idx,
                            unary_scores,
                            neighbor_graph,
                            detail_map,
                            palette,
                            params,
                        )
                        if score < best_score:
                            best = candidate_idx
                            best_score = score

                    if best != current:
                        chosen_idx[iy, ix] = best
                        changed = True
        if not changed:
            break

    return chosen_idx
