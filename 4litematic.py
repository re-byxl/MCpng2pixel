import os
import csv
from litemapy import Schematic, Region, BlockState

CSV_DIR = "output/csv"
OUT_DIR = "output/litematic"


def convert(csv_path):
    cells = []

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                cells.append((int(r["x"]), int(r["y"]), r["block"].strip()))
    except Exception as e:
        print(f" ❌ 读取 CSV 失败: {csv_path}, 错误: {e}")
        return

    if not cells:
        return

    max_x = max(c[0] for c in cells) + 1
    max_y = max(c[1] for c in cells) + 1

    schem = Schematic()
    reg = Region(0, 0, 0, max_x, max_y, 1)

    for x, y, name in cells:
        mc = BlockState("minecraft:" + name)
        reg[x, max_y-1-y, 0] = mc

    schem.regions["main"] = reg

    base_name = os.path.splitext(os.path.basename(csv_path))[0]
    out_path = os.path.join(OUT_DIR, f"{base_name}.litematic")

    try:
        schem.save(out_path)
        print(" [OK] 生成完成:", out_path)
    except Exception as e:
        print(f" [ERR] 保存投影失败: {out_path}, 错误: {e}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if not os.path.exists(CSV_DIR):
        print(f"找不到目录: {CSV_DIR}")
        return 1

    for f in os.listdir(CSV_DIR):
        if f.lower().endswith(".csv"):
            convert(os.path.join(CSV_DIR, f))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
