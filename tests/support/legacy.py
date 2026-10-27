"""加载旧版"数字开头"脚本的辅助。

重构之后这些脚本会变成普通模块（``mcyqqs.pipeline.postprocess`` 等），
这里优先用新模块，找不到再按文件路径加载旧脚本 —— 这样测试不用跟着改。
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 旧脚本名 -> 新模块名
LEGACY_MODULES = {
    "3postprocess.py": "mcyqqs.pipeline.postprocess",
    "4litematic.py": "mcyqqs.pipeline.export",
    "grid_utils.py": "mcyqqs.pipeline.grid",
    "match_modes.py": "mcyqqs.matching.modes",
    "palette.py": "mcyqqs.matching.palette",
    "litematic_tool/core.py": "mcyqqs.litematic.core",
    "litematic_tool/server.py": "mcyqqs.tool.server",
}


def load(legacy_filename: str) -> ModuleType:
    """加载一个模块：优先用重构后的正式模块，否则按文件路径加载旧脚本。"""
    new_name = LEGACY_MODULES.get(legacy_filename)
    if new_name:
        try:
            return importlib.import_module(new_name)
        except ImportError:
            pass

    # 已经是包内模块的（litematic_tool/core.py），按点号路径导入
    dotted = legacy_filename.replace("/", ".").removesuffix(".py")
    if "." in dotted:
        try:
            return importlib.import_module(dotted)
        except ImportError:
            pass

    path = PROJECT_ROOT / legacy_filename
    spec = importlib.util.spec_from_file_location(f"_legacy_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
