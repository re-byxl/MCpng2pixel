"""Litematic 方向转换与方块替换工具。

模块划分：

- ``cli``    : 命令行入口（``python -m mcyqqs.tool``），批量转换 / 启动网页
- ``server`` : 本地网页前端所用的 HTTP 服务与 JSON API
- ``dialog`` : 服务器端的目录选择弹窗（独立进程）
- ``web``    : 前端静态页面（HTML / CSS / JS，无构建步骤）

变换数学、投影读取、方块替换这些纯领域逻辑都在
:mod:`mcyqqs.litematic.core` 里，这里不重复导出。
"""

from __future__ import annotations

import os
from pathlib import Path

#: 仓库根目录（``src/mcyqqs/tool/__init__.py`` 的上三层）
#:
#: 相对路径（输入目录、输出目录……）都以它为基准展开。
PROJECT_ROOT = Path(__file__).resolve().parents[3]

#: 配置文件名（放在仓库根目录，工具的配置是它的 ``tool`` 节）
SETTINGS_FILENAME = "config.json"


def resolve_path(path: str | os.PathLike[str] | None) -> str:
    """把相对路径按项目根目录展开。

    空路径返回空串；绝对路径原样规范化；相对路径拼到仓库根目录后面。
    """
    if not path:
        return ""
    text = os.fspath(path)
    if os.path.isabs(text):
        return os.path.normpath(text)
    return os.path.normpath(os.path.join(str(PROJECT_ROOT), text))


__all__ = ["PROJECT_ROOT", "SETTINGS_FILENAME", "resolve_path"]
