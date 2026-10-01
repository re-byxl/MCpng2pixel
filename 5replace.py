import os
import csv
from litemapy import Schematic, Region, BlockState

# ===== 手动指定输入文件 =====
INPUT_CSV = "output/csv/test.csv"   # 改成你的文件名

# ===== 输出目录 =====
OUT_DIR = "output/litematic_replaced"

os.makedirs(OUT_DIR, exist_ok=True)

# ===== 替换规则 =====
REPLACE = {
    "red_concrete": "red_terracotta",
    # "gray_concrete": "smooth_quartz",
}

def convert(csv_path):

    cells = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r["block"]
            if name in REPLACE:
                name = REPLACE[name]
            cells.append((int(r["x"]), int(r["y"]), name))

    max_x = max(c[0] for c in cells) + 1
    max_y = max(c[1] for c in cells) + 1

    schem = Schematic()
    reg = Region(0,0,0,max_x,max_y,1)

    for x,y,name in cells:
        reg[x, max_y-1-y, 0] = BlockState("minecraft:"+name)

    schem.regions["main"] = reg

    out = os.path.join(
        OUT_DIR,
        os.path.splitext(os.path.basename(csv_path))[0] + "_replaced.litematic"
    )

    schem.save(out)
    print("生成:", out)


convert(INPUT_CSV)