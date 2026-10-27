"""重新生成黄金样本基线。

用法::

    python tests/generate_baseline.py

基线用的是 ``tests/golden/config.json`` 这份固定配置（不随仓库根目录的
config.json 变动）。

只有在**明确知道自己在改流水线行为**的时候才应该跑这个脚本 ——
它会覆盖 tests/golden/ 下的期望文件，让测试重新变绿。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent

sys.path.insert(0, str(TESTS_DIR))

from support import pipeline, reference  # noqa: E402

GOLDEN_DIR = TESTS_DIR / "golden"


def main() -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        image_path = workdir / "grid_sample.png"
        reference.write_reference(str(image_path))

        pipeline.run_pipeline(workdir, image_path)
        csv_path = pipeline.find_output(workdir, ".csv")
        litematic_path = pipeline.find_output(workdir, ".litematic")

        csv_text = csv_path.read_text(encoding="utf-8-sig")
        blocks = pipeline.dump_blocks(litematic_path)

    (GOLDEN_DIR / "grid_sample.csv").write_text(csv_text, encoding="utf-8-sig")
    (GOLDEN_DIR / "grid_sample.blocks.txt").write_text(blocks, encoding="utf-8")

    print(f"已写入 {GOLDEN_DIR / 'grid_sample.csv'}")
    print(f"已写入 {GOLDEN_DIR / 'grid_sample.blocks.txt'}")
    print(f"  CSV 行数: {len(csv_text.splitlines())}")
    print(f"  方块行数: {len(blocks.splitlines())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
