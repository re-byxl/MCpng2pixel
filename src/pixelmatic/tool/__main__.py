"""``python -m pixelmatic.tool`` 的入口。"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证从任意目录运行都能找到项目里的 palette.py 等模块，以及源码目录下的 pixelmatic
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
_SRC_ROOT = str(Path(__file__).resolve().parents[2])
for _path in (_SRC_ROOT, _PROJECT_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from .cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
