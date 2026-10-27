"""匹配目标函数与求解器。

思路：
1. **一元项** —— 每个格子在自己的候选方块里挑"颜色最接近"的那个。
2. **成对项** —— 让相邻格子之间的*对比度大小*贴近原图里的对比度，
   而不是简单地把相邻格子弄成一样（那样会糊掉边缘）。
3. 用 ICM（迭代条件模式）逐轮改进：一轮里按棋盘格顺序更新，
   每个格子在 top_k 个候选里挑让总能量最小的。

数学与原实现完全一致。差别只在**怎么算**：CIEDE2000 的调用全部批量化
（逐格调用要 12 万次，每次 120 微秒；批量算只要 0.3 秒），
而且逐位结果相同 —— 黄金样本回归测试守着这条线。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import BluePenaltyConfig, MatchParams, NeutralMaskConfig
from .color import chroma_of, delta_e, palette_lab

#: 四邻域，顺序与原实现一致（累加顺序会影响浮点结果，不能改）
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


# --------------------------------------------------------------------------- #
# 一元项
# --------------------------------------------------------------------------- #


def score_matrix(
    labs: np.ndarray,
    palette: PaletteIndex,
    params: MatchParams,
    blue_penalty: BluePenaltyConfig,
    neutral_mask: NeutralMaskConfig,
) -> np.ndarray:
    """给一批格子算所有方块的得分。

    ``labs`` 形状 (M, 3)，返回 (M, 调色板大小) 的分数矩阵。
    """
    labs = np.asarray(labs, dtype=np.float64)
    if labs.size == 0:
        return np.zeros((0, palette.size))

    base = delta_e(palette.lab[None, :, :], labs[:, None, :])

    lightness_gap = np.abs(palette.lab[None, :, 0] - labs[:, None, 0])
    source_chroma = chroma_of(labs)
    chroma_gap = np.abs(palette.chroma[None, :] - source_chroma[:, None])

    score = base + params.lightness_weight * lightness_gap + params.chroma_weight * chroma_gap

    if neutral_mask.enabled:
        high = source_chroma >= params.pastel_chroma_threshold
        is_neutral = palette.chroma <= params.neutral_chroma_threshold
        chroma_loss = np.maximum(0.0, source_chroma[:, None] - palette.chroma[None, :])
        penalty = is_neutral[None, :] * chroma_loss * params.chroma_loss_weight
        score = score + np.where(high[:, None], penalty, 0.0)

    bluish = labs[:, 2] < blue_penalty.threshold_b
    if bluish.any():
        purple_penalty = np.zeros(palette.size)
        purple_penalty[palette.purple_indices] = blue_penalty.penalty_purple
        pink_penalty = np.zeros(palette.size)
        pink_penalty[palette.pink_indices] = blue_penalty.penalty_pink
        score = score + np.where(bluish[:, None], purple_penalty[None, :], 0.0)
        score = score + np.where(bluish[:, None], pink_penalty[None, :], 0.0)

    return score


# --------------------------------------------------------------------------- #
# 邻域
# --------------------------------------------------------------------------- #


@dataclass
class NeighborField:
    """每个格子到四邻域的色差。

    ``deltas`` 形状 (ny, nx, 4)，无效的位置是 nan；
    ``valid`` 形状 (ny, nx, 4)，标记这个方向有没有有效邻居。
    """

    deltas: np.ndarray
    valid: np.ndarray


def neighbor_field(mean_grid: np.ndarray, valid_grid: np.ndarray | None = None) -> NeighborField:
    """一次性算出所有格子到四邻域的色差。"""
    ny, nx, _ = mean_grid.shape
    deltas = np.full((ny, nx, len(NEIGHBORS)), np.nan)
    valid = np.zeros((ny, nx, len(NEIGHBORS)), dtype=bool)

    for k, (dx, dy) in enumerate(NEIGHBORS):
        # 中心 (iy, ix) 对应邻居 (iy + dy, ix + dx)
        ys0, ys1 = max(0, -dy), min(ny, ny - dy)
        xs0, xs1 = max(0, -dx), min(nx, nx - dx)
        center = mean_grid[ys0:ys1, xs0:xs1]
        neighbor = mean_grid[ys0 + dy : ys1 + dy, xs0 + dx : xs1 + dx]

        flat = delta_e(center.reshape(-1, 1, 3), neighbor.reshape(-1, 1, 3)).reshape(
            center.shape[:2]
        )

        ok = np.ones(center.shape[:2], dtype=bool)
        if valid_grid is not None:
            ok = valid_grid[ys0:ys1, xs0:xs1] & valid_grid[ys0 + dy : ys1 + dy, xs0 + dx : xs1 + dx]

        deltas[ys0:ys1, xs0:xs1, k] = np.where(ok, flat, np.nan)
        valid[ys0:ys1, xs0:xs1, k] = ok

    return NeighborField(deltas=deltas, valid=valid)


def compute_detail_weight(
    mean_grid: np.ndarray,
    valid_grid: np.ndarray | None = None,
    field: NeighborField | None = None,
) -> np.ndarray:
    """每个格子与四邻域的平均色差，归一化到 0..1 —— 细节越强的格子权重越高。"""
    ny, nx, _ = mean_grid.shape
    detail = np.zeros((ny, nx), dtype=np.float32)

    if field is None:
        field = neighbor_field(mean_grid, valid_grid)
    acc = np.zeros((ny, nx), dtype=np.float64)
    count = np.zeros((ny, nx), dtype=np.int64)

    # 累加顺序与原实现一致：((d1 + d2) + d3) + d4
    for k in range(len(NEIGHBORS)):
        d = field.deltas[:, :, k]
        ok = field.valid[:, :, k]
        acc = acc + np.where(ok, d, 0.0)
        count += ok

    mask = count > 0
    detail[mask] = (acc[mask] / count[mask]).astype(np.float32)

    if valid_grid is not None:
        detail[~valid_grid] = 0

    if detail.max() > 0:
        detail /= detail.max()
    return detail


# --------------------------------------------------------------------------- #
# 求解
# --------------------------------------------------------------------------- #


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

    if valid_grid is None:
        mask = np.ones((ny, nx), dtype=bool)
    else:
        mask = valid_grid
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return unary_scores, candidate_map, chosen_idx

    scores = score_matrix(mean_grid[ys, xs], palette, params, blue_penalty, neutral_mask)
    unary_scores[ys, xs] = scores.astype(np.float32)

    order = np.argsort(scores, axis=1)[:, : params.top_k]
    for i in range(len(ys)):
        iy = int(ys[i])
        ix = int(xs[i])
        candidate_map[(ix, iy)] = [int(v) for v in order[i]]
        chosen_idx[iy, ix] = int(order[i, 0])

    return unary_scores, candidate_map, chosen_idx


def local_energy(
    ix: int,
    iy: int,
    candidate_idx: int,
    chosen_idx: np.ndarray,
    unary_scores: np.ndarray,
    field: NeighborField,
    detail_map: np.ndarray,
    palette: PaletteIndex,
    params: MatchParams,
) -> float:
    """一个格子换成某个方块后的总能量。"""
    score = float(unary_scores[iy, ix, candidate_idx])
    detail_scale = 1.0 + params.detail_weight * float(detail_map[iy, ix])

    for k in range(len(NEIGHBORS)):
        if not field.valid[iy, ix, k]:
            continue
        nx2 = ix + NEIGHBORS[k][0]
        ny2 = iy + NEIGHBORS[k][1]
        neighbor_idx = int(chosen_idx[ny2, nx2])
        if neighbor_idx < 0:
            continue

        src_diff = float(field.deltas[iy, ix, k])
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
    # 邻域色差只算一次，细节权重和局部能量共用
    field = neighbor_field(mean_grid, valid_grid)
    detail_map = compute_detail_weight(mean_grid, valid_grid, field)

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
                        field,
                        detail_map,
                        palette,
                        params,
                    )

                    for candidate in candidate_map[(ix, iy)]:
                        if candidate == current:
                            continue
                        score = local_energy(
                            ix,
                            iy,
                            candidate,
                            chosen_idx,
                            unary_scores,
                            field,
                            detail_map,
                            palette,
                            params,
                        )
                        if score < best_score:
                            best = candidate
                            best_score = score

                    if best != current:
                        chosen_idx[iy, ix] = best
                        changed = True
        if not changed:
            break

    return chosen_idx
