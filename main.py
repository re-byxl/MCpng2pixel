import argparse
import json
import os
import sys
import importlib.util


def get_bundle_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def load_module(name, filename):
    base = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
    filepath = os.path.join(base, filename)
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_config(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [ERR] 读取配置文件失败: {config_path}, 错误: {e}")
        return None


def parse_args():
    from match_modes import MATCH_MODES
    parser = argparse.ArgumentParser(description="运行完整图片转 Minecraft 投影流水线。")
    parser.add_argument(
        "--config",
        default="config.json",
        help="配置文件路径（默认 config.json）。",
    )
    parser.add_argument(
        "--mode",
        choices=list(MATCH_MODES.keys()),
        help="匹配模式，会覆盖配置文件中的设置。",
    )
    parser.add_argument(
        "--skip-litematic",
        action="store_true",
        help="跳过 .litematic 生成，会覆盖配置文件中的设置。",
    )
    parser.add_argument(
        "--skip-postprocess",
        action="store_true",
        help="跳过背景黑色删除后处理。",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        help="手动指定方块大小（像素），会覆盖配置文件中的设置。",
    )
    parser.add_argument(
        "--grid-cells",
        help="目标网格格子数，如 '64'、'64x48' 或 'auto'，会覆盖配置文件中的设置。",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    config = {}
    if os.path.exists(args.config):
        loaded = load_config(args.config)
        if loaded is not None:
            config = loaded

    mode = args.mode if args.mode is not None else config.get("mode", "balanced")
    skip_litematic = args.skip_litematic if args.skip_litematic else config.get("skip_litematic", False)
    skip_postprocess = args.skip_postprocess if args.skip_postprocess else config.get("skip_postprocess", False)

    from grid_utils import set_block_size, auto_blocksize, parse_grid_cells, read_image, DEBUG_FILE

    if args.block_size is not None:
        block_size = args.block_size
        set_block_size(block_size)
        print(f"使用命令行指定的方块大小: {block_size}")
    else:
        block_size_cfg = config.get("block_size", "auto")
        grid_cells_cfg = args.grid_cells if args.grid_cells is not None else config.get("grid_cells", "auto")

        if block_size_cfg == "auto":
            sample_file = None
            input_dir = "input_images"
            if os.path.exists(input_dir):
                for f in os.listdir(input_dir):
                    if f.lower().endswith((".png", ".jpg", ".jpeg")):
                        sample_file = os.path.join(input_dir, f)
                        break

            if sample_file:
                img = read_image(sample_file)
                if img is not None:
                    orig_h, orig_w = img.shape[:2]
                    from grid_utils import crop_like_original
                    crop = crop_like_original(img)
                    if crop is not None:
                        crop_h, crop_w = crop.shape[:2]
                    else:
                        crop_w, crop_h = orig_w, orig_h

                    grid_cells_x, grid_cells_y = parse_grid_cells(grid_cells_cfg)
                    block_size = auto_blocksize(crop_w, crop_h, grid_cells_x, grid_cells_y)
                    set_block_size(block_size)
                    print(f"自动计算方块大小: {block_size}（裁剪后图像 {crop_w}x{crop_h}，目标网格 {grid_cells_cfg}）")
                else:
                    block_size = 30
                    set_block_size(block_size)
                    print(f"无法读取图片，使用默认方块大小: {block_size}")
            else:
                block_size = 30
                set_block_size(block_size)
                print(f"未找到输入图片，使用默认方块大小: {block_size}")
        else:
            block_size = int(block_size_cfg)
            set_block_size(block_size)
            print(f"使用配置文件中的方块大小: {block_size}")

    from match_modes import MATCH_MODES
    print(f"Pipeline mode: {mode} - {MATCH_MODES[mode]['description']}")

    if os.path.exists(DEBUG_FILE):
        os.remove(DEBUG_FILE)

    print("[STEP 1/4] 网格切分...")
    step1 = load_module("_step1", "1grid.py")
    code = step1.main()
    if code != 0:
        return code

    print("[STEP 2/4] 平均色提取...")
    step2 = load_module("_step2", "2color.py")
    code = step2.main()
    if code != 0:
        return code

    print("[STEP 3/4] 方块匹配...")
    step3 = load_module("_step3", "3match.py")
    sys.argv = ["3match", "--mode", mode]
    code = step3.main()
    if code != 0:
        return code

    if not skip_postprocess:
        print("[STEP 3.5/4] 后处理...")
        step35 = load_module("_step35", "3postprocess.py")
        code = step35.main()
        if code != 0:
            return code

    if not skip_litematic:
        print("[STEP 4/4] 生成 .litematic...")
        step4 = load_module("_step4", "4litematic.py")
        code = step4.main()
        if code != 0:
            return code

    print("[OK] 全流程完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
