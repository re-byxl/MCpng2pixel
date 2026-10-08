import argparse
import json
import os

import cv2
import numpy as np
from skimage import color
from skimage.color import deltaE_ciede2000

from grid_utils import aligned_crop, iter_cells, read_image, save_png, get_block_size, get_grid_info
from match_modes import MATCH_MODES, get_match_mode
from palette import MC_BLOCKS

INPUT_DIR = "input_images"
OUT_PREVIEW = "output/preview"
OUT_CSV = "output/csv"
MARGIN = 4

_config = None


def _load_config():
    global _config
    if _config is not None:
        return _config
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            _config = json.load(f)
    else:
        _config = {}
    return _config


def _get_path_config():
    config = _load_config()
    return config.get("paths", {})


def _get_cell_config():
    config = _load_config()
    return config.get("cell", {})


def _get_output_dirs():
    path_cfg = _get_path_config()
    preview = path_cfg.get("output_preview", OUT_PREVIEW)
    csv = path_cfg.get("output_csv", OUT_CSV)
    return preview, csv


def _get_margin():
    cell_cfg = _get_cell_config()
    return cell_cfg.get("margin", MARGIN)


os.makedirs(OUT_PREVIEW, exist_ok=True)
os.makedirs(OUT_CSV, exist_ok=True)

names = list(MC_BLOCKS.keys())
rgb_palette = np.array([MC_BLOCKS[n] for n in names]) / 255.0
lab_palette = color.rgb2lab(rgb_palette.reshape(-1, 1, 3)).reshape(-1, 3)
palette_chroma = np.sqrt(lab_palette[:, 1] ** 2 + lab_palette[:, 2] ** 2)
palette_delta = deltaE_ciede2000(
    lab_palette[:, None, :],
    lab_palette[None, :, :]
)


PURPLE_INDICES = [i for i, n in enumerate(names) if "purple" in n or "magenta" in n]
PINK_INDICES = [i for i, n in enumerate(names) if "pink" in n]

_BLUE_PENALTY = None
_NEUTRAL_MASK_CONFIG = None


def _load_blue_penalty():
    global _BLUE_PENALTY
    if _BLUE_PENALTY is not None:
        return _BLUE_PENALTY
    config = _load_config()
    _BLUE_PENALTY = config.get("blue_penalty", {
        "threshold_b": -15,
        "penalty_purple": 25,
        "penalty_pink": 20
    })
    return _BLUE_PENALTY


def _load_neutral_mask_config():
    global _NEUTRAL_MASK_CONFIG
    if _NEUTRAL_MASK_CONFIG is not None:
        return _NEUTRAL_MASK_CONFIG
    config = _load_config()
    _NEUTRAL_MASK_CONFIG = config.get("neutral_mask", {
        "enabled": False
    })
    return _NEUTRAL_MASK_CONFIG


def candidate_indices(lab, params):
    lab = lab.reshape(1, 3)
    base = deltaE_ciede2000(lab_palette, lab)
    lightness_gap = np.abs(lab_palette[:, 0] - lab[0, 0])
    src_chroma = float(np.sqrt(lab[0, 1] ** 2 + lab[0, 2] ** 2))
    chroma_gap = np.abs(palette_chroma - src_chroma)
    chroma_loss = np.maximum(0.0, src_chroma - palette_chroma)

    score = (
        base
        + params["lightness_weight"] * lightness_gap
        + params["chroma_weight"] * chroma_gap
    )

    neutral_cfg = _load_neutral_mask_config()
    if neutral_cfg.get("enabled", False) and src_chroma >= params["pastel_chroma_threshold"]:
        neutral_mask = palette_chroma <= params["neutral_chroma_threshold"]
        score = score + neutral_mask * chroma_loss * params["chroma_loss_weight"]

    penalty = _load_blue_penalty()
    if lab[0, 2] < penalty["threshold_b"]:
        score[PURPLE_INDICES] += penalty["penalty_purple"]
        score[PINK_INDICES] += penalty["penalty_pink"]

    order = np.argsort(score)
    return order[: params["top_k"]], score


def compute_detail_weight(mean_grid, valid_grid=None):
    ny, nx, _ = mean_grid.shape
    detail = np.zeros((ny, nx), dtype=np.float32)
    for iy in range(ny):
        for ix in range(nx):
            center = mean_grid[iy, ix]
            if valid_grid is not None and not valid_grid[iy, ix]:
                continue
            acc = 0.0
            count = 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx2 = ix + dx
                ny2 = iy + dy
                if 0 <= nx2 < nx and 0 <= ny2 < ny:
                    if valid_grid is not None and not valid_grid[ny2, nx2]:
                        continue
                    diff = float(deltaE_ciede2000(
                        center.reshape(1, 3),
                        mean_grid[ny2, nx2].reshape(1, 3)
                    )[0])
                    acc += diff
                    count += 1
            if count:
                detail[iy, ix] = acc / count
    if detail.max() > 0:
        detail /= detail.max()
    return detail


def build_neighbor_graph(mean_grid, valid_grid=None):
    ny, nx, _ = mean_grid.shape
    graph = {}
    for iy in range(ny):
        for ix in range(nx):
            if valid_grid is not None and not valid_grid[iy, ix]:
                continue
            edges = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx2 = ix + dx
                ny2 = iy + dy
                if 0 <= nx2 < nx and 0 <= ny2 < ny:
                    if valid_grid is not None and not valid_grid[ny2, nx2]:
                        continue
                    src_diff = float(deltaE_ciede2000(
                        mean_grid[iy, ix].reshape(1, 3),
                        mean_grid[ny2, nx2].reshape(1, 3)
                    )[0])
                    edges.append((nx2, ny2, src_diff))
            graph[(ix, iy)] = edges
    return graph


def initialize_assignments(mean_grid, params, valid_grid=None):
    ny, nx, _ = mean_grid.shape
    unary_scores = np.full((ny, nx, len(names)), np.inf, dtype=np.float32)
    candidate_map = {}
    chosen_idx = np.full((ny, nx), -1, dtype=np.int32)

    for iy in range(ny):
        for ix in range(nx):
            if valid_grid is not None and not valid_grid[iy, ix]:
                continue
            mean = mean_grid[iy, ix]
            indices, scores = candidate_indices(mean, params)
            unary_scores[iy, ix] = scores.astype(np.float32)
            candidate_map[(ix, iy)] = [int(v) for v in indices]
            chosen_idx[iy, ix] = int(indices[0])
    return unary_scores, candidate_map, chosen_idx


def local_energy(ix, iy, candidate_idx, chosen_idx, unary_scores, neighbor_graph, detail_map, params):
    score = float(unary_scores[iy, ix, candidate_idx])
    detail_scale = 1.0 + params["detail_weight"] * float(detail_map[iy, ix])

    for nx2, ny2, src_diff in neighbor_graph[(ix, iy)]:
        neighbor_idx = int(chosen_idx[ny2, nx2])
        if neighbor_idx < 0:
            continue

        palette_diff = float(palette_delta[candidate_idx, neighbor_idx])
        edge_scale = 1.0 + params["edge_weight"] * min(src_diff, 20.0) / 20.0
        score += params["contrast_weight"] * edge_scale * abs(palette_diff - src_diff) * detail_scale

        if candidate_idx == neighbor_idx and src_diff > params["repeat_threshold"]:
            score += params["repeat_penalty"] * edge_scale * min(src_diff, 20.0) / 20.0

    return score


def optimize_assignments(mean_grid, params, valid_grid=None):
    unary_scores, candidate_map, chosen_idx = initialize_assignments(mean_grid, params, valid_grid)
    detail_map = compute_detail_weight(mean_grid, valid_grid)
    neighbor_graph = build_neighbor_graph(mean_grid, valid_grid)

    for _ in range(params["iterations"]):
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
                    best_score = local_energy(ix, iy, current, chosen_idx, unary_scores, neighbor_graph, detail_map, params)

                    for candidate_idx in candidate_map[(ix, iy)]:
                        if candidate_idx == current:
                            continue
                        score = local_energy(ix, iy, candidate_idx, chosen_idx, unary_scores, neighbor_graph, detail_map, params)
                        if score < best_score:
                            best = candidate_idx
                            best_score = score

                    if best != current:
                        chosen_idx[iy, ix] = best
                        changed = True
        if not changed:
            break

    return chosen_idx


def process(img_path, mode_name):
    params = get_match_mode(mode_name)

    img = read_image(img_path)
    if img is None:
        return

    img_name = os.path.basename(img_path)
    block = get_block_size()
    crop = aligned_crop(img, block, debug=True, img_name=img_name)
    if crop is None:
        return

    h, w = crop.shape[:2]
    ny = h // block
    nx = w // block

    margin = _get_margin()
    out_preview, out_csv = _get_output_dirs()

    lab = color.rgb2lab(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) / 255.0)
    preview = np.zeros_like(crop)
    table = []
    mean_grid = np.zeros((ny, nx, 3), dtype=np.float32)
    pixel_count_grid = np.zeros((ny, nx), dtype=np.int32)

    for ix, iy, x0, y0, x1, y1 in iter_cells(crop, block):
        inner = lab[y0 + margin : y1 - margin, x0 + margin : x1 - margin]
        if inner.size == 0:
            continue
        mean_grid[iy, ix] = inner.mean(axis=(0, 1))
        pixel_count_grid[iy, ix] = inner.shape[0] * inner.shape[1]

    chosen_idx = optimize_assignments(mean_grid, params, pixel_count_grid > 0)

    for ix, iy, x0, y0, x1, y1 in iter_cells(crop, block):
        if pixel_count_grid[iy, ix] == 0:
            continue

        idx = int(chosen_idx[iy, ix])
        name = names[idx]
        rgb = (rgb_palette[idx] * 255).astype(np.uint8)
        preview[y0:y1, x0:x1] = rgb[::-1]
        table.append((ix, iy, name))

    fname = os.path.splitext(os.path.basename(img_path))[0]
    os.makedirs(out_preview, exist_ok=True)
    save_png(os.path.join(out_preview, f"{fname}.png"), preview)

    csv_path = os.path.join(out_csv, f"{fname}.csv")
    os.makedirs(out_csv, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig") as f:
        f.write("x,y,block\n")
        for row in table:
            f.write(f"{row[0]},{row[1]},{row[2]}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="将图片匹配为 Minecraft 方块预览和 CSV。")
    parser.add_argument(
        "--mode",
        default="quality",
        choices=list(MATCH_MODES.keys()),
        help="匹配模式: quality / balanced / color_priority / contrast_priority / smooth_priority",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(INPUT_DIR):
        print(f"未找到输入目录: {INPUT_DIR}")
        return 1

    print(f"匹配模式: {args.mode} - {MATCH_MODES[args.mode]['description']}")
    for f in os.listdir(INPUT_DIR):
        if f.lower().endswith((".png", ".jpg", ".jpeg")):
            print("正在匹配:", f)
            process(os.path.join(INPUT_DIR, f), args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
