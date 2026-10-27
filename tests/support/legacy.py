"""加载旧版"数字开头"脚本名的辅助。

这些脚本在重构后都成了正式模块（``pixelmatic.pipeline.postprocess`` 等），
这里只保留「旧脚本名 -> 新模块名」的映射，测试代码不用跟着改名。
"""

from __future__ import annotations

import importlib
from types import ModuleType

#: 旧脚本名 -> 新模块名
LEGACY_MODULES = {
    "3postprocess.py": "pixelmatic.pipeline.postprocess",
    "4litematic.py": "pixelmatic.pipeline.export",
    "grid_utils.py": "pixelmatic.pipeline.grid",
    "match_modes.py": "pixelmatic.matching.modes",
    "palette.py": "pixelmatic.matching.palette",
    "litematic_tool/core.py": "pixelmatic.litematic.core",
    "litematic_tool/server.py": "pixelmatic.tool.server",
}


def load(legacy_filename: str) -> ModuleType:
    """按旧脚本名加载对应的正式模块。"""
    new_name = LEGACY_MODULES.get(legacy_filename)
    if not new_name:
        raise ImportError(f"没有和 {legacy_filename} 对应的模块")
    return importlib.import_module(new_name)
