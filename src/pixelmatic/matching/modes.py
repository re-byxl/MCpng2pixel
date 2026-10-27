"""匹配模式（目标函数的参数预设）。

每种模式就是一组 :class:`~pixelmatic.config.MatchParams`。
参数有 schema 校验，缺 key 会在加载时就报错，而不是在跑到一半时 KeyError。
"""

from __future__ import annotations

from ..config import MatchParams

#: 模式名 -> (参数, 说明)
_MATCH_MODE_SPECS: dict[str, tuple[dict, str]] = {
    "quality": (
        {
            "top_k": 14,
            "repeat_threshold": 6.0,
            "repeat_penalty": 13.0,
            "contrast_weight": 0.52,
            "lightness_weight": 0.10,
            "chroma_weight": 0.34,
            "chroma_loss_weight": 1.00,
            "pastel_chroma_threshold": 10.0,
            "neutral_chroma_threshold": 8.0,
            "iterations": 8,
            "edge_weight": 0.62,
            "detail_weight": 0.35,
        },
        "高质量模式，使用更重的全局迭代优化，优先最终观感。",
    ),
    "balanced": (
        {
            "top_k": 8,
            "repeat_threshold": 8.0,
            "repeat_penalty": 10.0,
            "contrast_weight": 0.35,
            "lightness_weight": 0.12,
            "chroma_weight": 0.28,
            "chroma_loss_weight": 0.65,
            "pastel_chroma_threshold": 12.0,
            "neutral_chroma_threshold": 8.0,
            "iterations": 3,
            "edge_weight": 0.45,
            "detail_weight": 0.20,
        },
        "默认模式，综合色相、亮度和局部对比。",
    ),
    "color_priority": (
        {
            "top_k": 10,
            "repeat_threshold": 7.0,
            "repeat_penalty": 9.0,
            "contrast_weight": 0.28,
            "lightness_weight": 0.10,
            "chroma_weight": 0.38,
            "chroma_loss_weight": 0.90,
            "pastel_chroma_threshold": 10.0,
            "neutral_chroma_threshold": 8.0,
            "iterations": 4,
            "edge_weight": 0.38,
            "detail_weight": 0.18,
        },
        "优先保色，尽量避免淡彩被白灰吞掉。",
    ),
    "contrast_priority": (
        {
            "top_k": 10,
            "repeat_threshold": 6.0,
            "repeat_penalty": 14.0,
            "contrast_weight": 0.55,
            "lightness_weight": 0.12,
            "chroma_weight": 0.15,
            "chroma_loss_weight": 0.60,
            "pastel_chroma_threshold": 12.0,
            "neutral_chroma_threshold": 8.0,
            "iterations": 5,
            "edge_weight": 0.30,
            "detail_weight": 0.20,
        },
        "优先保局部差异，减少相邻区域塌成同一种方块。",
    ),
    "smooth_priority": (
        {
            "top_k": 6,
            "repeat_threshold": 10.0,
            "repeat_penalty": 6.0,
            "contrast_weight": 0.18,
            "lightness_weight": 0.16,
            "chroma_weight": 0.22,
            "chroma_loss_weight": 0.45,
            "pastel_chroma_threshold": 14.0,
            "neutral_chroma_threshold": 8.0,
            "iterations": 2,
            "edge_weight": 0.20,
            "detail_weight": 0.10,
        },
        "优先平滑过渡，整体观感更整齐。",
    ),
}

#: 模式名 -> 参数
MATCH_MODES: dict[str, MatchParams] = {
    name: MatchParams(**params) for name, (params, _) in _MATCH_MODE_SPECS.items()
}

#: 模式名 -> 说明
MODE_DESCRIPTIONS: dict[str, str] = {
    name: description for name, (_, description) in _MATCH_MODE_SPECS.items()
}


def get_match_mode(mode_name: str) -> MatchParams:
    """按名字取匹配模式。"""
    if mode_name not in MATCH_MODES:
        valid = ", ".join(MATCH_MODES)
        raise ValueError(f"未知模式: {mode_name}。可选模式: {valid}")
    return MATCH_MODES[mode_name]


def describe_mode(mode_name: str) -> str:
    """匹配模式的一句话说明。"""
    if mode_name not in MODE_DESCRIPTIONS:
        valid = ", ".join(MATCH_MODES)
        raise ValueError(f"未知模式: {mode_name}。可选模式: {valid}")
    return MODE_DESCRIPTIONS[mode_name]
