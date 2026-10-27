"""MCpng2pixel —— 把图片转换成 Minecraft 方块投影。

模块一览：

- ``config``    配置模型（唯一配置来源）
- ``cli``       命令行入口
- ``pipeline``  图片流水线：网格对齐 -> 取色 -> 匹配 -> 后处理 -> 导出
- ``matching``  匹配算法：调色板、颜色科学、目标函数
- ``litematic`` 投影方向转换与方块替换
- ``tool``      方向转换的网页前端
- ``publish``   投稿产物（命名、清单、页面）
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
