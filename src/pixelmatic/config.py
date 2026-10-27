"""配置模型：整个项目只有一份配置来源。

以前配置散在四个地方（``config.json``、``litematic_tool.json``、各脚本里的
硬编码常量、``settings.py`` 的 ``DEFAULT_SETTINGS``），而且 ``--config``
只对入口脚本生效。现在统一成：

- 一份 ``config.json``，顶层是流水线配置，``tool`` 节是方向转换工具的配置
- 一套 pydantic 模型做校验，缺 key / 类型错会**报错**，而不是静默回落默认值
- 配置对象**显式传参**给各个 stage，不再有模块级全局变量
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .litematic.core import TransformPlan

#: 配置文件名（相对于当前工作目录）
CONFIG_FILENAME = "config.json"


class PathsConfig(BaseModel):
    """流水线用到的所有目录。"""

    model_config = ConfigDict(extra="forbid")

    input_dir: Path = Path("input_images")
    output_preview: Path = Path("output/preview")
    output_csv: Path = Path("output/csv")
    output_litematic: Path = Path("output/litematic")
    debug_dir: Path = Path("debug")
    color_debug: Path = Path("debug/color_preview")
    grid_output_dir: Path = Path("debug/grid_output_images")


class CellConfig(BaseModel):
    """每个格子的取色区域。"""

    model_config = ConfigDict(extra="forbid")

    margin: int = Field(default=4, ge=0)


class GridConfig(BaseModel):
    """网格检测参数。"""

    model_config = ConfigDict(extra="forbid")

    min_block: int = Field(default=6, ge=1)
    center_ratio: float = Field(default=0.45, gt=0, le=1)
    smooth_window: int = Field(default=9, ge=1)
    shift_radius: int = Field(default=4, ge=0)


class BluePenaltyConfig(BaseModel):
    """蓝色系被误判成紫/粉时的惩罚。

    默认全部为 0（即不启用）—— 只有在结果里真的出现蓝被误判时才按需调高。
    """

    model_config = ConfigDict(extra="forbid")

    threshold_b: int = 0
    penalty_purple: int = 0
    penalty_pink: int = 0


class NeutralMaskConfig(BaseModel):
    """中性色（白/灰/黑）保护。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class MatchParams(BaseModel):
    """匹配目标函数的全部权重。

    以前这些参数散在 ``match_modes.py`` 的普通 dict 里，取值靠 ``params["..."]``
    直接下标 —— 少一个 key 就 KeyError。现在有 schema 兜底。
    """

    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=8, ge=1)
    repeat_threshold: float = Field(default=8.0, ge=0)
    repeat_penalty: float = Field(default=10.0, ge=0)
    contrast_weight: float = Field(default=0.4, ge=0)
    lightness_weight: float = Field(default=0.13, ge=0)
    chroma_weight: float = Field(default=0.25, ge=0)
    chroma_loss_weight: float = Field(default=0.7, ge=0)
    pastel_chroma_threshold: float = Field(default=12.0, ge=0)
    neutral_chroma_threshold: float = Field(default=8.0, ge=0)
    iterations: int = Field(default=3, ge=1)
    edge_weight: float = Field(default=0.4, ge=0)
    detail_weight: float = Field(default=0.2, ge=0)


class ToolConfig(BaseModel):
    """方向转换工具的配置。"""

    model_config = ConfigDict(extra="forbid")

    input_dir: Path = Path("input_litematic")
    output_dir: Path = Path("output/litematic_transformed")
    suffix: str = "_transformed"
    overwrite: bool = True
    keep_properties: bool = False
    plan: TransformPlan = Field(default_factory=TransformPlan)
    replacements: dict[str, str] = Field(default_factory=dict)


class AppConfig(BaseModel):
    """``config.json`` 的完整结构。"""

    model_config = ConfigDict(extra="forbid")

    # --- 流水线 ---
    block_size: int | Literal["auto"] = "auto"
    grid_cells: str = "auto"
    mode: str = "balanced"
    skip_litematic: bool = False
    skip_postprocess: bool = False

    paths: PathsConfig = Field(default_factory=PathsConfig)
    cell: CellConfig = Field(default_factory=CellConfig)
    grid: GridConfig = Field(default_factory=GridConfig)
    blue_penalty: BluePenaltyConfig = Field(default_factory=BluePenaltyConfig)
    neutral_mask: NeutralMaskConfig = Field(default_factory=NeutralMaskConfig)

    # --- 方向转换工具 ---
    tool: ToolConfig = Field(default_factory=ToolConfig)

    @field_validator("block_size", mode="before")
    @classmethod
    def _coerce_block_size(cls, value: Any) -> Any:
        """``"9"`` 这种字符串写法也接受。"""
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return value

    @field_validator("grid_cells", mode="before")
    @classmethod
    def _coerce_grid_cells(cls, value: Any) -> Any:
        if isinstance(value, int):
            return str(value)
        return value


def config_path(path: str | Path | None = None) -> Path:
    """配置文件路径（默认当前目录下的 ``config.json``）。"""
    return Path(path) if path else Path(CONFIG_FILENAME)


def load_config(path: str | Path | None = None) -> AppConfig:
    """读取并校验配置。

    文件不存在时返回默认配置；文件存在但**不合法**时直接报错 ——
    这正是我们要的：静默回落默认值会让人以为配置生效了。
    """
    target = config_path(path)
    if not target.exists():
        return AppConfig()

    raw = json.loads(target.read_text(encoding="utf-8"))
    return AppConfig.model_validate(raw)


def save_config(config: AppConfig, path: str | Path | None = None) -> Path:
    """把配置写回文件（原子替换）。"""
    target = config_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        config.model_dump_json(indent=2, exclude_defaults=False),
        encoding="utf-8",
    )
    tmp.replace(target)
    return target
