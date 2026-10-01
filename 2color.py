import os

import cv2
import numpy as np
from skimage import color

from grid_utils import aligned_crop, iter_cells, read_image, save_image, get_block_size, get_grid_info

INPUT_DIR = "input_images"
COLOR_DEBUG = "debug/color_preview"
MARGIN = 4

os.makedirs(COLOR_DEBUG, exist_ok=True)


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
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) / 255.0
    lab = color.rgb2lab(rgb)
    preview = np.zeros_like(crop)

    for _, _, x0, y0, x1, y1 in iter_cells(crop, block):
        inner = lab[y0 + MARGIN : y1 - MARGIN, x0 + MARGIN : x1 - MARGIN]
        if inner.size == 0:
            continue

        mean_lab = inner.mean(axis=(0, 1))
        rgb_mean = color.lab2rgb(mean_lab.reshape(1, 1, 3))[0, 0] * 255
        preview[y0:y1, x0:x1] = rgb_mean

    out_bgr = cv2.cvtColor(preview, cv2.COLOR_RGB2BGR)
    return save_image(save_path, out_bgr)


def main():
    if not os.path.exists(INPUT_DIR):
        print(f"未找到输入目录: {INPUT_DIR}")
        return 1

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    for f in files:
        print("处理:", f)
        process_one_image(
            os.path.join(INPUT_DIR, f),
            os.path.join(COLOR_DEBUG, f)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
