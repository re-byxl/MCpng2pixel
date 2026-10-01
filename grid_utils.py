import os

import cv2
import numpy as np

MIN_BLOCK = 6
CENTER_RATIO = 0.45
SMOOTH_WINDOW = 9
DEFAULT_BLOCK_SIZE = 30
SHIFT_RADIUS = 4

DEBUG_DIR = "debug"
DEBUG_FILE = os.path.join(DEBUG_DIR, "grid_debug.txt")

_block_size = None
_grid_info = {}


def set_block_size(size):
    global _block_size
    _block_size = size


def get_block_size():
    return _block_size if _block_size is not None else DEFAULT_BLOCK_SIZE


def set_grid_info(info):
    global _grid_info
    _grid_info = info


def get_grid_info():
    return _grid_info


def write_grid_debug(img_name, info):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"图片: {img_name}\n")
        f.write(f"{'='*60}\n")
        f.write(f"  原始图像: {info.get('original_size', 'N/A')[0]}x{info.get('original_size', 'N/A')[1]}\n")
        f.write(f"  Canny裁剪后: {info.get('cropped_size', 'N/A')[0]}x{info.get('cropped_size', 'N/A')[1]}\n")
        f.write(f"  方块大小: {info.get('block_size', 0)} 像素\n")
        f.write(f"  网格锚点偏移: anchor_x={info.get('anchor_x', 0)}, anchor_y={info.get('anchor_y', 0)}\n")
        f.write(f"  网格覆盖范围: {info.get('grid_cells_x', 0)}x{info.get('grid_cells_y', 0)} 格\n")
        f.write(f"  丢弃像素: 左{info.get('discarded_left', 0)} 右{info.get('discarded_right', 0)} 上{info.get('discarded_top', 0)} 下{info.get('discarded_bottom', 0)}\n")


def parse_grid_cells(grid_cells_str):
    """解析 grid_cells 配置，返回 (target_cells_x, target_cells_y)"""
    if grid_cells_str == "auto" or grid_cells_str is None:
        return None, None

    if isinstance(grid_cells_str, int):
        return grid_cells_str, grid_cells_str

    parts = str(grid_cells_str).split("x")
    if len(parts) == 1:
        v = int(parts[0])
        return v, v
    elif len(parts) == 2:
        return int(parts[0]), int(parts[1])
    return None, None


def auto_blocksize(img_width, img_height, grid_cells_x=None, grid_cells_y=None):
    """自动计算 block_size，确保能整除图像尺寸"""
    if img_width <= 0 or img_height <= 0:
        return DEFAULT_BLOCK_SIZE

    if grid_cells_x is None or grid_cells_y is None:
        grid_cells_x = 64
        grid_cells_y = 64

    cw = max(1, img_width // grid_cells_x)
    ch = max(1, img_height // grid_cells_y)
    size = min(cw, ch)
    size = max(MIN_BLOCK, size)

    size = find_dividable_size(img_width, img_height, size)
    return size


def find_dividable_size(img_width, img_height, target_size):
    """从 target_size 开始向下找能同时整除宽高的最大值"""
    size = target_size
    while size >= MIN_BLOCK:
        if img_width % size == 0 and img_height % size == 0:
            return size
        size -= 1
    return MIN_BLOCK


def read_image(img_path):
    try:
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.shape[2] == 4:
            alpha = img[:, :, 3]
            mask = alpha > 10
            img = img[:, :, :3]
            if not mask.any():
                return None
            img = cv2.bitwise_and(img, img, mask=mask)
        return img
    except Exception as e:
        print(f"  [ERR] 读取异常: {img_path}, 错误: {e}")
        return None


def save_image(save_path, img):
    try:
        ext = os.path.splitext(save_path)[1]
        ok, encoded = cv2.imencode(ext, img)
        if ok:
            encoded.tofile(save_path)
            return True
        return False
    except Exception as e:
        print(f"  [ERR] 保存失败: {save_path}, 错误: {e}")
        return False


def save_png(save_path, img):
    try:
        ok, encoded = cv2.imencode(".png", img)
        if ok:
            encoded.tofile(save_path)
            return True
        return False
    except Exception as e:
        print(f"  [ERR] 保存失败: {save_path}, 错误: {e}")
        return False


def crop_like_original(img):
    has_alpha = img.shape[2] == 4 if len(img.shape) == 3 else False

    if has_alpha:
        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
        alpha = img[:, :, 3]
        edges = cv2.Canny(gray, 50, 150)
        mask = alpha > 10
        edges = cv2.bitwise_and(edges, edges, mask=mask)
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

    coords = cv2.findNonZero(edges)
    if coords is None:
        return None

    x, y, w, h = cv2.boundingRect(coords)
    if has_alpha:
        return img[y : y + h, x : x + w, :3]
    return img[y : y + h, x : x + w]


def smooth_signal(signal, window=SMOOTH_WINDOW):
    if signal.size == 0:
        return signal
    window = min(window, signal.size)
    if window < 3:
        return signal.astype(np.float32)
    if window % 2 == 0:
        window += 1
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(signal, kernel, mode="same")


def gradient_signal(gray, axis):
    dx = 1 if axis == 1 else 0
    dy = 1 if axis == 0 else 0
    grad = cv2.Sobel(gray, cv2.CV_32F, dx, dy, ksize=3)
    signal = np.mean(np.abs(grad), axis=1 - axis)
    signal = smooth_signal(signal)
    signal -= signal.min()
    peak = signal.max()
    if peak > 0:
        signal /= peak
    return signal


def best_offset(signal, block=None):
    if block is None:
        block = get_block_size()
    if signal.size < block * 2:
        return 0

    scores = []
    for offset in range(block):
        indices = np.arange(offset, len(signal), block)
        if len(indices) < 2:
            scores.append(-1.0)
            continue
        line_strength = float(signal[indices].mean())
        mask = np.ones(len(signal), dtype=bool)
        mask[indices] = False
        fill_strength = float(signal[mask].mean()) if mask.any() else 0.0
        scores.append(line_strength - 0.35 * fill_strength)
    return int(np.argmax(scores))


def grid_score(gray, block, x_offset, y_offset):
    h, w = gray.shape
    if h < block * 2 or w < block * 2:
        return -1.0

    x_lines = np.arange(x_offset, w, block)
    y_lines = np.arange(y_offset, h, block)
    if len(x_lines) < 2 or len(y_lines) < 2:
        return -1.0

    x_strength = float(np.mean([gray[:, x].mean() for x in x_lines]))
    y_strength = float(np.mean([gray[y, :].mean() for y in y_lines]))

    x_fill_mask = np.ones(w, dtype=bool)
    y_fill_mask = np.ones(h, dtype=bool)
    x_fill_mask[x_lines] = False
    y_fill_mask[y_lines] = False

    x_fill = float(gray[:, x_fill_mask].mean()) if x_fill_mask.any() else 0.0
    y_fill = float(gray[y_fill_mask, :].mean()) if y_fill_mask.any() else 0.0
    return (x_strength - 0.35 * x_fill) + (y_strength - 0.35 * y_fill)


def refine_offsets(crop, block, x_offset, y_offset):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    best = (x_offset, y_offset)
    best_score = -1.0
    for dx in range(-SHIFT_RADIUS, SHIFT_RADIUS + 1):
        for dy in range(-SHIFT_RADIUS, SHIFT_RADIUS + 1):
            trial_x = (x_offset + dx) % block
            trial_y = (y_offset + dy) % block
            score = grid_score(gray, block, trial_x, trial_y)
            if score > best_score:
                best_score = score
                best = (trial_x, trial_y)
    return best


def center_window(crop):
    h, w = crop.shape[:2]
    ch = max(MIN_BLOCK * 6, int(round(h * CENTER_RATIO)))
    cw = max(MIN_BLOCK * 6, int(round(w * CENTER_RATIO)))
    ch = min(ch, h)
    cw = min(cw, w)

    y0 = (h - ch) // 2
    x0 = (w - cw) // 2
    return x0, y0, crop[y0 : y0 + ch, x0 : x0 + cw]


def expand_lines(anchor, block, limit):
    lines = [anchor]

    pos = anchor - block
    while pos > 0:
        lines.append(pos)
        pos -= block

    pos = anchor + block
    while pos < limit:
        lines.append(pos)
        pos += block

    lines = sorted(set(lines))

    if lines and lines[0] > 0:
        lines.insert(0, 0)
    if lines and lines[-1] < limit:
        lines.append(limit)

    return sorted(set(lines))


def aligned_bounds(lines, limit, block):
    inner = [v for v in lines if 0 <= v <= limit]
    if len(inner) < 2:
        return None

    start = int(inner[0])
    end = int(inner[-1])
    usable = end - start
    cells = usable // block
    if cells <= 0:
        return None
    return start, start + cells * block


def aligned_crop(img, block=None, debug=False, img_name="unknown"):
    if block is None:
        block = get_block_size()

    info = {
        "original_size": None,
        "cropped_size": None,
        "block_size": block,
        "anchor_x": 0,
        "anchor_y": 0,
        "grid_cells_x": 0,
        "grid_cells_y": 0,
        "discarded_left": 0,
        "discarded_right": 0,
        "discarded_top": 0,
        "discarded_bottom": 0,
        "img_name": img_name,
    }

    orig_h, orig_w = img.shape[:2]
    info["original_size"] = (orig_w, orig_h)

    crop = crop_like_original(img)
    if crop is None or crop.size == 0:
        set_grid_info(info)
        return None

    crop_h, crop_w = crop.shape[:2]
    info["cropped_size"] = (crop_w, crop_h)

    center_x, center_y, center_crop = center_window(crop)
    center_gray = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
    center_x_signal = gradient_signal(center_gray, axis=1)
    center_y_signal = gradient_signal(center_gray, axis=0)

    anchor_x = center_x + best_offset(center_x_signal, block)
    anchor_y = center_y + best_offset(center_y_signal, block)
    anchor_x, anchor_y = refine_offsets(crop, block, anchor_x % block, anchor_y % block)

    info["anchor_x"] = anchor_x
    info["anchor_y"] = anchor_y

    x_lines = expand_lines(anchor_x, block, crop_w)
    y_lines = expand_lines(anchor_y, block, crop_h)
    x_bounds = aligned_bounds(x_lines, crop_w, block)
    y_bounds = aligned_bounds(y_lines, crop_h, block)
    if x_bounds is None or y_bounds is None:
        set_grid_info(info)
        return None

    x0, x1 = x_bounds
    y0, y1 = y_bounds
    aligned = crop[y0:y1, x0:x1]
    if aligned.size == 0:
        set_grid_info(info)
        return None

    aligned_h, aligned_w = aligned.shape[:2]
    info["grid_cells_x"] = aligned_w // block
    info["grid_cells_y"] = aligned_h // block

    info["discarded_left"] = x0
    info["discarded_right"] = crop_w - x1
    info["discarded_top"] = y0
    info["discarded_bottom"] = crop_h - y1

    set_grid_info(info)

    if debug:
        write_grid_debug(info.get("img_name", "unknown"), info)

    return aligned


def iter_cells(img, block=None):
    if block is None:
        block = get_block_size()
    h, w = img.shape[:2]
    ny = h // block
    nx = w // block
    for iy in range(ny):
        for ix in range(nx):
            y0 = iy * block
            x0 = ix * block
            y1 = y0 + block
            x1 = x0 + block
            yield ix, iy, x0, y0, x1, y1
