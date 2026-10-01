import os

import cv2

from grid_utils import aligned_crop, iter_cells, read_image, save_image, get_block_size, get_grid_info

INPUT_DIR = "input_images"
DEBUG_DIR = "debug/grid_output_images"

os.makedirs(DEBUG_DIR, exist_ok=True)


def draw_grid(img, block):
    vis = img.copy()
    h, w = vis.shape[:2]

    for x in range(0, w + 1, block):
        xx = min(x, w - 1)
        cv2.line(vis, (xx, 0), (xx, h - 1), (0, 255, 0), 1)
    for y in range(0, h + 1, block):
        yy = min(y, h - 1)
        cv2.line(vis, (0, yy), (w - 1, yy), (0, 255, 0), 1)

    return vis


def annotate(vis, block=None):
    if block is None:
        block = get_block_size()
    cells_x = vis.shape[1] // block
    cells_y = vis.shape[0] // block
    label = f"block={block}, cells={cells_x}x{cells_y}"
    cv2.putText(
        vis,
        label,
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return vis


def process_one_image(img_path, save_path):
    img = read_image(img_path)
    if img is None:
        return False

    img_name = os.path.basename(img_path)
    crop = aligned_crop(img, debug=True, img_name=img_name)
    if crop is None:
        print("  [ERR] 无法扩展出完整整数网格")
        return False

    block = get_block_size()
    vis = annotate(draw_grid(crop, block), block)
    return save_image(save_path, vis)


def main():
    if not os.path.exists(INPUT_DIR):
        print(f"错误：找不到输入目录 {INPUT_DIR}")
        return 1

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    total = len(files)
    print(f"共检测到 {total} 张图片")

    for i, fname in enumerate(files, 1):
        print(f"[{i}/{total}] 处理 {fname}")
        in_path = os.path.join(INPUT_DIR, fname)
        out_path = os.path.join(DEBUG_DIR, fname)

        ok = process_one_image(in_path, out_path)
        if ok:
            print("  [OK] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
