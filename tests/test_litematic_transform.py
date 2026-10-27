"""方向转换（平面重映射 / 旋转 / 镜像）的单元测试。

这部分是纯数学，出错时不会报错，只会安静地产出歪掉的图案 ——
所以每个方向都要有断言。
"""

from __future__ import annotations

import pytest
from litemapy import BlockState, Region

from support import legacy

core = legacy.load("litematic_tool/core.py")

W, H = 4, 3


@pytest.fixture()
def wall():
    """一张 4x3 的立面图，法线朝 Z。

    方块名是 ``stone_{列}{行}``，行号 0 是图案最上面一行
    （和 4litematic.py 里 CSV 行 0 = 图片顶行的约定一致）。
    """
    region = Region(0, 0, 0, W, H, 1)
    for row in range(H):
        for col in range(W):
            region[col, H - 1 - row, 0] = BlockState(f"minecraft:stone_{col}{row}")
    return region


def _names(region: Region) -> list[list[str]]:
    """按 (行, 列) 读出方块名，行 0 是最上面。"""
    out = []
    for row in range(region.height):
        line = []
        for col in range(region.width):
            line.append(region[col, region.height - 1 - row, 0].id.replace("minecraft:stone_", ""))
        out.append(line)
    return out


def _transform(region, **kwargs):
    plan = core.TransformPlan(**kwargs)
    matrix = core.build_matrix(core.plan_for_region(region, plan))
    return core.transform_region(region, matrix, None, False)


def test_detect_normal_axis(wall):
    assert core.detect_normal_axis((W, H, 1)) == "z"
    assert core.detect_normal_axis((W, 1, H)) == "y"
    assert core.detect_normal_axis((1, H, W)) == "x"


def test_identity_keeps_everything(wall):
    out = _transform(wall, target_normal="z")
    assert (out.width, out.height, out.length) == (W, H, 1)
    assert _names(out) == _names(wall)


def test_wall_to_flat(wall):
    """墙面 -> 地面：宽度沿 X，厚度变成 1 层 Y。"""
    out = _transform(wall, target_normal="y")
    assert (out.width, out.height, out.length) == (W, 1, H)
    assert core.detect_normal_axis((out.width, out.height, out.length)) == "y"


def test_flat_view_equals_wall_view(wall):
    """从上面俯视平铺后的图案，必须和正面看原来的墙面画一模一样。

    这是整套方向约定成立的核心断言：变换是"旋转"而不是"镜像"。
    """
    flat = _transform(wall, target_normal="y")

    wall_view = core.project_region(wall)  # 正面看
    flat_view = core.project_region(flat)  # 俯视看

    def to_grid(view):
        return [
            [
                view["palette"][i] if i >= 0 else "air"
                for i in view["grid"][r * view["cols"] : (r + 1) * view["cols"]]
            ]
            for r in range(view["rows"])
        ]

    assert to_grid(flat_view) == to_grid(wall_view)


def test_rotation_is_counter_clockwise(wall):
    """平面内旋转 90° 是逆时针：原图最上面一行变成最左边一列（自上而下倒序）。"""
    out = _transform(wall, target_normal="z", rotation=90)
    assert (out.width, out.height, out.length) == (H, W, 1)

    names = _names(out)
    # 原来第 0 行（最上面）的四个格子，现在沿最左边一列自上而下排开
    assert names[0][0] == "30"
    assert names[1][0] == "20"
    assert names[2][0] == "10"
    assert names[3][0] == "00"


def test_mirror_horizontal(wall):
    out = _transform(wall, target_normal="z", mirror_h=True)
    names = _names(out)
    assert names[0] == ["30", "20", "10", "00"]


def test_mirror_vertical(wall):
    out = _transform(wall, target_normal="z", mirror_v=True)
    names = _names(out)
    assert names[0] == ["02", "12", "22", "32"]


def test_rotation_180(wall):
    out = _transform(wall, target_normal="z", rotation=180)
    names = _names(out)
    assert names[0] == ["32", "22", "12", "02"]


def test_global_rotation_applies_after_remap(wall):
    """额外全局旋转作用在朝向转换之后。"""
    out = _transform(wall, target_normal="y", rotate_z=90)
    # 先变成 4x1x3，再绕 Z 转 90° -> 1x4x3
    assert (out.width, out.height, out.length) == (1, 4, 3)


def test_replacement_applies():
    """替换规则把 red_concrete 换成 red_terracotta。"""
    region = Region(0, 0, 0, 2, 1, 1)
    region[0, 0, 0] = BlockState("minecraft:red_concrete")
    region[1, 0, 0] = BlockState("minecraft:white_concrete")

    matrix = core.build_matrix(core.plan_for_region(region, core.TransformPlan(target_normal="z")))
    out = core.transform_region(region, matrix, {"red_concrete": "red_terracotta"})

    assert out[0, 0, 0].id == "minecraft:red_terracotta"
    assert out[1, 0, 0].id == "minecraft:white_concrete"


def test_replacement_to_air_removes_block():
    """规则值为 air 时把方块删掉。"""
    region = Region(0, 0, 0, 2, 1, 1)
    region[0, 0, 0] = BlockState("minecraft:red_concrete")
    region[1, 0, 0] = BlockState("minecraft:white_concrete")

    matrix = core.build_matrix(core.plan_for_region(region, core.TransformPlan(target_normal="z")))
    out = core.transform_region(region, matrix, {"red_concrete": "air"})

    assert out[0, 0, 0].id == "minecraft:air"
    assert out[1, 0, 0].id == "minecraft:white_concrete"
