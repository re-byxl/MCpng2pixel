import os
import argparse

import cv2
import numpy as np
import pandas as pd
from PIL import Image
from scipy.signal import find_peaks
from skimage import color
from skimage.color import deltaE_ciede2000

from palette import MC_BLOCKS

IMG = "MCblocks.png"
PALETTE_FILE = "palette.py"

MARGIN = 4
PEAK_DIST = 80
PEAK_HEIGHT = 0.03
TARGET_ROWS = 6
TARGET_COLS = 9

OUTPUT_DIR = "extract_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description="从 MCblocks.png 提取调色板并自动对齐到 palette.py。")
    parser.add_argument(
        "--brightness",
        type=float,
        default=1.2,
        help="亮度倍率，1.0 为原图，>1 提亮，<1 压暗。",
    )
    return parser.parse_args()


def apply_brightness(img_np, brightness):
    if brightness == 1.0:
        return img_np
    adjusted = np.clip(img_np * brightness, 0.0, 1.0)
    return adjusted


def segment_palette_image(img_np):
    h, w, _ = img_np.shape

    row_diff = np.mean(np.abs(np.diff(img_np, axis=0)), axis=(1, 2))
    row_peaks, _ = find_peaks(row_diff, height=PEAK_HEIGHT, distance=PEAK_DIST)
    row_bounds = [0] + (row_peaks + 1).tolist() + [h]

    col_diff = np.mean(np.abs(np.diff(img_np, axis=1)), axis=(0, 2))
    col_peaks, _ = find_peaks(col_diff, height=PEAK_HEIGHT, distance=PEAK_DIST)
    col_bounds = [0] + (col_peaks + 1).tolist() + [w]

    return row_bounds, col_bounds


def normalize_bounds(bounds, target_count):
    lengths = np.diff(bounds)
    cell_count = len(lengths)
    if cell_count < target_count:
        raise ValueError(f"检测到的格子数 {cell_count} 少于目标格子数 {target_count}")
    if cell_count == target_count:
        return bounds

    best_start = 0
    best_score = -1e18
    for start in range(cell_count - target_count + 1):
        seg = lengths[start:start + target_count].astype(np.float64)
        mean = seg.mean()
        std = seg.std()
        min_len = seg.min()
        edge_penalty = abs(seg[0] - mean) + abs(seg[-1] - mean)
        score = mean * 3.0 + min_len * 1.5 - std * 3.0 - edge_penalty * 0.8
        if score > best_score:
            best_score = score
            best_start = start

    return bounds[best_start:best_start + target_count + 1]


def normalize_grid_bounds(row_bounds, col_bounds):
    return (
        normalize_bounds(row_bounds, TARGET_ROWS),
        normalize_bounds(col_bounds, TARGET_COLS),
    )


def extract_cells(img_np, row_bounds, col_bounds):
    lab = color.rgb2lab(img_np)
    preview = np.zeros_like(img_np)
    rows = []

    for iy in range(len(row_bounds) - 1):
        for ix in range(len(col_bounds) - 1):
            y0, y1 = row_bounds[iy], row_bounds[iy + 1]
            x0, x1 = col_bounds[ix], col_bounds[ix + 1]

            block_lab = lab[y0 + MARGIN : y1 - MARGIN, x0 + MARGIN : x1 - MARGIN]
            if block_lab.size == 0:
                continue

            mean_lab = block_lab.mean(axis=(0, 1))
            mean_rgb = color.lab2rgb(mean_lab.reshape(1, 1, 3))[0, 0]
            preview[y0:y1, x0:x1] = mean_rgb

            r, g, b = (mean_rgb * 255).astype(int)
            rows.append({
                "x": ix,
                "y": iy,
                "r": r,
                "g": g,
                "b": b,
                "L": float(mean_lab[0]),
                "a": float(mean_lab[1]),
                "b2": float(mean_lab[2]),
            })

    return pd.DataFrame(rows), preview


def save_debug_outputs(img_np, row_bounds, col_bounds, df):
    h, w, _ = img_np.shape
    dbg = (img_np * 255).astype(np.uint8)

    for y in row_bounds[1:-1]:
        cv2.line(dbg, (0, y), (w, y), (255, 0, 0), 1)
    for x in col_bounds[1:-1]:
        cv2.line(dbg, (x, 0), (x, h), (255, 0, 0), 1)

    cv2.imwrite(
        os.path.join(OUTPUT_DIR, "segmented.png"),
        cv2.cvtColor(dbg, cv2.COLOR_RGB2BGR),
    )
    df.to_csv(os.path.join(OUTPUT_DIR, "palette.csv"), index=False)


def align_rows_to_blocks(df):
    block_names = list(MC_BLOCKS.keys())
    block_rgbs = np.array([MC_BLOCKS[name] for name in block_names], dtype=np.float32) / 255.0
    block_labs = color.rgb2lab(block_rgbs.reshape(-1, 1, 3)).reshape(-1, 3)

    expected_total = 54
    expected_blocks = len(block_names)
    if len(df) != expected_total:
        raise ValueError(f"提取到的色块数为 {len(df)}，预期应为 {expected_total}")
    if expected_blocks != 51:
        raise ValueError(f"palette.py 中方块数为 {expected_blocks}，预期应为 51")

    # 固定规则：9 列 6 行，共 54 格，跳过第一行最右边 3 格。
    skip_mask = (df["y"] == 0) & (df["x"] >= 6)
    mapped_source = df.loc[~skip_mask].reset_index()
    skipped_rows = df.loc[skip_mask].copy().reset_index(drop=True)

    if len(mapped_source) != expected_blocks:
        raise ValueError(
            f"应用固定跳过规则后剩余 {len(mapped_source)} 个色块，预期应为 {expected_blocks}"
        )

    pair_cost = deltaE_ciede2000(
        mapped_source[["L", "a", "b2"]].to_numpy(dtype=np.float32),
        block_labs
    )

    rows = []
    for block_idx, (_, src_row) in enumerate(mapped_source.iterrows()):
        row = src_row.to_dict()
        extract_idx = int(row["index"])
        del row["index"]
        row["block"] = block_names[block_idx]
        row["deltaE"] = float(pair_cost[block_idx])
        row["source_index"] = extract_idx
        rows.append(row)

    mapped_df = pd.DataFrame(rows, columns=[
        "block", "x", "y", "r", "g", "b", "L", "a", "b2", "deltaE", "source_index"
    ])
    return mapped_df, skipped_rows


def save_mapped_outputs(mapped_df, skipped_df):
    mapped_path = os.path.join(OUTPUT_DIR, "palette_mapped.csv")
    skipped_path = os.path.join(OUTPUT_DIR, "palette_skipped.csv")
    py_path = os.path.join(OUTPUT_DIR, "palette_generated.py")
    backup_path = os.path.join(OUTPUT_DIR, "palette_backup.py")

    mapped_df.to_csv(mapped_path, index=False, encoding="utf-8-sig")
    skipped_df.to_csv(skipped_path, index=False, encoding="utf-8-sig")

    lines = ["MC_BLOCKS = {"]
    for _, row in mapped_df.iterrows():
        lines.append(f'    "{row["block"]}": ({int(row["r"])}, {int(row["g"])}, {int(row["b"])}),')
    lines.append("}")
    lines.append("")

    if os.path.exists(PALETTE_FILE):
        with open(PALETTE_FILE, "r", encoding="utf-8") as f:
            original = f.read()
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original)

    with open(py_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(PALETTE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return mapped_path, skipped_path, py_path, backup_path


def save_palette_overview(mapped_df, ncols=5):
    if mapped_df.empty:
        return None

    names = mapped_df["block"].tolist()
    colors = mapped_df[["r", "g", "b"]].to_numpy(dtype=np.uint8)
    nrows = (len(names) + ncols - 1) // ncols

    cell_w = 260
    cell_h = 90
    pad = 16
    width = ncols * cell_w + pad * 2
    height = nrows * cell_h + pad * 2
    canvas = np.full((height, width, 3), 245, dtype=np.uint8)

    for idx, (name, rgb) in enumerate(zip(names, colors)):
        row = idx // ncols
        col = idx % ncols
        x0 = pad + col * cell_w
        y0 = pad + row * cell_h
        x1 = x0 + cell_w - 12
        y1 = y0 + cell_h - 12

        bgr = tuple(int(v) for v in rgb[::-1])
        cv2.rectangle(canvas, (x0, y0), (x1, y1), bgr, -1)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), (40, 40, 40), 1)

        brightness = int(rgb.mean())
        text_color = (255, 255, 255) if brightness < 120 else (20, 20, 20)
        cv2.putText(
            canvas,
            name,
            (x0 + 10, y0 + 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            text_color,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            f"RGB {int(rgb[0])},{int(rgb[1])},{int(rgb[2])}",
            (x0 + 10, y0 + 64),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            text_color,
            1,
            cv2.LINE_AA,
        )

    path = os.path.join(OUTPUT_DIR, "palette_overview.png")
    cv2.imwrite(path, canvas)
    return path


def cleanup_legacy_outputs():
    for name in ("palette_color.png", "order_check.png"):
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(path):
            os.remove(path)


def main():
    args = parse_args()
    img = Image.open(IMG).convert("RGB")
    img_np = np.array(img) / 255.0
    img_np = apply_brightness(img_np, args.brightness)

    row_bounds, col_bounds = segment_palette_image(img_np)
    row_bounds, col_bounds = normalize_grid_bounds(row_bounds, col_bounds)
    print("rows:", len(row_bounds) - 1, "cols:", len(col_bounds) - 1)
    print("brightness:", args.brightness)

    df, preview = extract_cells(img_np, row_bounds, col_bounds)
    save_debug_outputs(img_np, row_bounds, col_bounds, df)

    mapped_df, skipped_df = align_rows_to_blocks(df)
    mapped_path, skipped_path, py_path, backup_path = save_mapped_outputs(mapped_df, skipped_df)
    overview_path = save_palette_overview(mapped_df)
    cleanup_legacy_outputs()

    print("输出完成，所有文件保存在：", OUTPUT_DIR)
    print(" - segmented.png         （带分割线的原图）")
    print(" - palette.csv           （原始提取结果，按扫描顺序）")
    print(" - palette_mapped.csv    （已与 block 名称自动对齐）")
    print(" - palette_skipped.csv   （存在于图里但未进入 palette.py 的色块）")
    print(" - palette_generated.py  （同步更新后的调色板快照）")
    print(" - palette_overview.png  （整合后的调色板总览图）")
    print("自动对齐结果：")
    print(" - 已映射方块数:", len(mapped_df))
    print(" - 跳过色块数:", len(skipped_df))
    print(" - 映射文件:", mapped_path)
    print(" - 已更新:", PALETTE_FILE)
    print(" - 生成快照:", py_path)
    print(" - 旧版备份:", backup_path)
    print(" - 总览图:", overview_path)
    if not mapped_df.empty:
        print(" - 平均 deltaE:", round(float(mapped_df["deltaE"].mean()), 3))
        print(" - 最大 deltaE:", round(float(mapped_df["deltaE"].max()), 3))


if __name__ == "__main__":
    main()
