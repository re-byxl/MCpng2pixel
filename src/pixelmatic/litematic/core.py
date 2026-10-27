"""Litematic 方向转换与方块替换的核心逻辑。

坐标系约定
----------
Minecraft 是右手系：+X 向东，+Y 向上，+Z 向南。

观察一个"贴在平面上的图案"时，用 (right, up, normal) 三元组描述它的朝向，
其中 right × up = normal（即从图案正面看过去，right 向右、up 向上、normal 朝向观察者）：

=========  ==========  ==========  ===========
法线轴     right       up          观察方式
=========  ==========  ==========  ===========
``z``      +X          +Y          站在图案正面（+Z 侧）平视
``y``      +X          -Z          从上往下俯视（+Z 在屏幕下方）
``x``      -Z          +Y          站在图案侧面（+X 侧）平视
=========  ==========  ==========  ===========

所有方向变换都被表示成一个 3x3 有符号置换矩阵 M：``dst = M · src + offset``。
这样的矩阵可以精确表达轴重映射、90 度整数倍旋转与镜像，组合时直接做矩阵乘法。
"""

from __future__ import annotations

import csv
import logging
import os
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

from litemapy import BlockState, Entity, Region, Schematic, TileEntity
from nbtlib.tag import Compound, Double, Int, List

from ..matching.palette import MC_BLOCKS

logger = logging.getLogger(__name__)

Vector = tuple[int, int, int]
Matrix = tuple[Vector, Vector, Vector]

IDENTITY: Matrix = ((1, 0, 0), (0, 1, 0), (0, 0, 1))

AXIS_NAMES = ("x", "y", "z")

#: (right, up, normal)，满足 right × up = normal
FRAMES: dict[str, tuple[Vector, Vector, Vector]] = {
    "z": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "y": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "x": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
}

AIR = BlockState("minecraft:air")


# --------------------------------------------------------------------------- #
# 矩阵工具
# --------------------------------------------------------------------------- #


def mat_mul(a: Matrix, b: Matrix) -> Matrix:
    """矩阵相乘，``(a · b)`` 表示先作用 b 再作用 a。"""
    rows: list[Vector] = []
    for i in range(3):
        values = [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        rows.append((values[0], values[1], values[2]))
    r0, r1, r2 = rows
    return (r0, r1, r2)


def _dot(a: Vector, b: Vector) -> int:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add(a: Vector, b: Vector) -> Vector:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vector, k: int) -> Vector:
    return (a[0] * k, a[1] * k, a[2] * k)


def axis_source(matrix: Matrix, dst_axis: int) -> tuple[int, int]:
    """返回目标轴 ``dst_axis`` 对应的源轴索引与方向符号（+1 / -1）。"""
    for j in range(3):
        if matrix[dst_axis][j] != 0:
            return j, matrix[dst_axis][j]
    raise ValueError("矩阵不是有效的置换矩阵")


def rotation_matrix(axis: str, degrees: int) -> Matrix:
    """绕指定轴做右手系旋转（90 的整数倍）。"""
    if degrees % 90 != 0:
        raise ValueError("只支持 90 度的整数倍旋转")
    steps = (degrees // 90) % 4
    base = {
        "x": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),  # +90°: Y→Z, Z→-Y
        "y": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),  # +90°: Z→X, X→-Z
        "z": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),  # +90°: X→Y, Y→-X
    }[axis]
    result = IDENTITY
    for _ in range(steps):
        result = mat_mul(base, result)
    return result


def plane_remap_matrix(
    src_normal: str,
    dst_normal: str,
    rotation: int = 0,
    mirror_h: bool = False,
    mirror_v: bool = False,
) -> Matrix:
    """把贴在 ``src_normal`` 法线平面上的图案搬到 ``dst_normal`` 法线平面。

    ``rotation`` 是图案在自身平面内的旋转角度（0/90/180/270，逆时针为正）。
    ``mirror_h`` / ``mirror_v`` 是最终画面上的水平 / 垂直镜像。
    """
    if rotation % 90 != 0:
        raise ValueError("只支持 90 度的整数倍旋转")

    r_s, u_s, n_s = FRAMES[src_normal]
    r_d, u_d, n_d = FRAMES[dst_normal]

    columns: list[Vector] = []
    for j in range(3):
        e: Vector = (1, 0, 0) if j == 0 else (0, 1, 0) if j == 1 else (0, 0, 1)
        a = _dot(e, r_s)
        b = _dot(e, u_s)
        c = _dot(e, n_s)

        steps = (rotation // 90) % 4
        if steps == 0:
            a2, b2 = a, b
        elif steps == 1:
            a2, b2 = -b, a
        elif steps == 2:
            a2, b2 = -a, -b
        else:
            a2, b2 = b, -a

        if mirror_h:
            a2 = -a2
        if mirror_v:
            b2 = -b2

        columns.append(_add(_add(_scale(r_d, a2), _scale(u_d, b2)), _scale(n_d, c)))

    rows: list[Vector] = []
    for i in range(3):
        values = [columns[j][i] for j in range(3)]
        rows.append((values[0], values[1], values[2]))
    r0, r1, r2 = rows
    return (r0, r1, r2)


# --------------------------------------------------------------------------- #
# 变换计划
# --------------------------------------------------------------------------- #


@dataclass
class TransformPlan:
    """一次方向转换的完整描述。"""

    source_normal: str = "auto"  # "auto" / "x" / "y" / "z"
    target_normal: str = "keep"  # "keep" / "x" / "y" / "z"
    rotation: int = 0  # 平面内旋转 0/90/180/270
    mirror_h: bool = False
    mirror_v: bool = False
    rotate_x: int = 0  # 额外的全局旋转（作用在朝向转换之后）
    rotate_y: int = 0
    rotate_z: int = 0

    def to_dict(self) -> dict:
        return {
            "source_normal": self.source_normal,
            "target_normal": self.target_normal,
            "rotation": self.rotation,
            "mirror_h": self.mirror_h,
            "mirror_v": self.mirror_v,
            "rotate_x": self.rotate_x,
            "rotate_y": self.rotate_y,
            "rotate_z": self.rotate_z,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> TransformPlan:
        data = data or {}
        return cls(
            source_normal=str(data.get("source_normal", "auto")),
            target_normal=str(data.get("target_normal", "keep")),
            rotation=int(data.get("rotation", 0) or 0),
            mirror_h=bool(data.get("mirror_h", False)),
            mirror_v=bool(data.get("mirror_v", False)),
            rotate_x=int(data.get("rotate_x", 0) or 0),
            rotate_y=int(data.get("rotate_y", 0) or 0),
            rotate_z=int(data.get("rotate_z", 0) or 0),
        )


def detect_normal_axis(dims: Sequence[int]) -> str:
    """根据区域尺寸推测图案所在的平面（厚度最小的那个轴）。"""
    order = sorted(range(3), key=lambda i: dims[i])
    smallest = dims[order[0]]
    candidates = [i for i in order if dims[i] == smallest]
    if len(candidates) > 1:
        # 多个轴一样薄：挑一个让其余两轴构成真正二维平面的轴
        for i in candidates:
            others = [dims[j] for j in range(3) if j != i]
            if others[0] != others[1]:
                return AXIS_NAMES[i]
        return AXIS_NAMES[candidates[0]]
    return AXIS_NAMES[candidates[0]]


def plan_for_region(region: Region, plan: TransformPlan) -> TransformPlan:
    """把 ``source_normal="auto"`` / ``target_normal="keep"`` 落实为具体轴。"""
    dims = (abs(region.width), abs(region.height), abs(region.length))
    detected = detect_normal_axis(dims)

    src = plan.source_normal
    if src in ("auto", "", None):
        src = detected
    if src not in AXIS_NAMES:
        raise ValueError(f"未知的源平面: {src}")

    dst = plan.target_normal
    if dst in ("keep", "auto", "", None):
        dst = src
    if dst not in AXIS_NAMES:
        raise ValueError(f"未知的目标朝向: {dst}")

    return TransformPlan(
        source_normal=src,
        target_normal=dst,
        rotation=plan.rotation,
        mirror_h=plan.mirror_h,
        mirror_v=plan.mirror_v,
        rotate_x=plan.rotate_x,
        rotate_y=plan.rotate_y,
        rotate_z=plan.rotate_z,
    )


def build_matrix(plan: TransformPlan) -> Matrix:
    """根据计划生成最终使用的变换矩阵。

    计划里的 ``source_normal`` / ``target_normal`` 必须是具体轴，
    "auto" / "keep" 需要先用 :func:`plan_for_region` 落实。
    """
    if plan.source_normal not in AXIS_NAMES or plan.target_normal not in AXIS_NAMES:
        raise ValueError("build_matrix 需要具体的轴，请先调用 plan_for_region() 解析 auto / keep")
    remap = plane_remap_matrix(
        plan.source_normal,
        plan.target_normal,
        plan.rotation,
        plan.mirror_h,
        plan.mirror_v,
    )
    if not (plan.rotate_x or plan.rotate_y or plan.rotate_z):
        return remap
    # 全局旋转作用在朝向转换之后：先绕 Z，再绕 Y，最后绕 X
    global_rot = rotation_matrix("z", plan.rotate_z)
    if plan.rotate_y:
        global_rot = mat_mul(rotation_matrix("y", plan.rotate_y), global_rot)
    if plan.rotate_x:
        global_rot = mat_mul(rotation_matrix("x", plan.rotate_x), global_rot)
    return mat_mul(global_rot, remap)


# --------------------------------------------------------------------------- #
# 方块替换
# --------------------------------------------------------------------------- #


def normalize_block_name(name: str) -> str:
    """去掉命名空间前缀，``minecraft:red_concrete`` -> ``red_concrete``。"""
    return name.split(":")[-1].strip()


def apply_replacement(
    block: BlockState,
    rules: dict[str, str] | None,
    keep_properties: bool = False,
) -> BlockState:
    """按替换规则把一个方块换成另一个方块。

    规则键可以是 ``red_concrete`` 或完整的 ``minecraft:red_concrete``。
    规则值为空 / ``air`` 时表示删除该方块（替换成空气）。
    """
    if not rules:
        return block

    block_id = block.id
    short = normalize_block_name(block_id)
    if block_id in rules:
        target = rules[block_id]
    elif short in rules:
        target = rules[short]
    else:
        return block

    target = str(target).strip()
    if not target or target.lower() in ("air", "minecraft:air", "-", "none"):
        return AIR

    target_id = target if ":" in target else "minecraft:" + target
    if keep_properties:
        props = dict(block.properties())
        try:
            return BlockState(target_id, **props)
        except Exception as exc:  # noqa: BLE001
            logger.warning("带属性替换失败，回退为无属性 %s: %s", target_id, exc)
    try:
        return BlockState(target_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("无法构造目标方块 %s，保留原方块 %s: %s", target_id, block_id, exc)
        return block


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #


def load_schematic(path: str) -> Schematic:
    """读取 .litematic 文件。"""
    return Schematic.load(path)


def _region_volume(region: Region) -> int:
    return abs(region.width) * abs(region.height) * abs(region.length)


def load_region(path: str) -> tuple[Region, str]:
    """读取 .litematic 或 .csv，统一返回 (区域, 来源类型)。

    CSV 是 ``3match.py`` 生成的 ``x,y,block`` 清单，这里按同样的约定生成区域。
    """
    if path.lower().endswith(".csv"):
        return load_csv_region(path), "csv"

    schem = load_schematic(path)
    if not schem.regions:
        raise ValueError("文件里没有可用的区域")
    # 取体积最大的区域
    name = max(schem.regions.keys(), key=lambda k: _region_volume(schem.regions[k]))
    return schem.regions[name], "litematic"


def cells_to_region(cells: list[tuple[int, int, str]]) -> Region:
    """把 ``x,y,block`` 清单变成一个 1 层厚的立面区域。

    CSV 的 ``y`` 以图片顶部为 0，Minecraft 的 Y 轴向上，所以行号要翻转：
    ``y_mc = max_y - 1 - y``。流水线导出（``pipeline.export``）与这里的
    坐标约定完全一致，共用本函数。
    """
    if not cells:
        raise ValueError("清单里没有方块数据")

    max_x = max(c[0] for c in cells) + 1
    max_y = max(c[1] for c in cells) + 1

    region = Region(0, 0, 0, max_x, max_y, 1)
    for x, y, name in cells:
        block_id = name if ":" in name else "minecraft:" + name
        region[x, max_y - 1 - y, 0] = BlockState(block_id)
    return region


def load_csv_region(csv_path: str) -> Region:
    """读取 ``x,y,block`` 清单并生成 1 层厚的立面区域。"""
    cells: list[tuple[int, int, str]] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("block") or "").strip()
            if not name:
                continue
            cells.append((int(row["x"]), int(row["y"]), name))

    if not cells:
        raise ValueError(f"CSV 里没有方块数据: {csv_path}")

    return cells_to_region(cells)


def _store_axes(region: Region) -> list[list[tuple[int, int]]]:
    """给出每个轴上 (区域坐标, 存储坐标) 的对应关系。"""
    axes = []
    for width, rng in (
        (region.width, region.range_x()),
        (region.height, region.range_y()),
        (region.length, region.range_z()),
    ):
        pairs = []
        for r in rng:
            store = r - width - 1 if width < 0 else r
            pairs.append((r, store))
        axes.append(pairs)
    return axes


# --------------------------------------------------------------------------- #
# 变换
# --------------------------------------------------------------------------- #


def transform_region(
    region: Region,
    matrix: Matrix,
    replacements: dict[str, str] | None = None,
    keep_properties: bool = False,
) -> Region:
    """按矩阵变换一个区域，同时应用方块替换规则。"""
    dims = (abs(region.width), abs(region.height), abs(region.length))
    axes = _store_axes(region)

    new_dims = [0, 0, 0]
    offsets = [0, 0, 0]
    for d in range(3):
        src_axis, sign = axis_source(matrix, d)
        new_dims[d] = dims[src_axis]
        offsets[d] = 0 if sign > 0 else dims[src_axis] - 1

    new_region = Region(region.x, region.y, region.z, new_dims[0], new_dims[1], new_dims[2])

    for x, sx in axes[0]:
        for y, sy in axes[1]:
            for z, sz in axes[2]:
                block = region[x, y, z]
                if block.id == "minecraft:air":
                    continue
                block = apply_replacement(block, replacements, keep_properties)
                if block.id == "minecraft:air":
                    continue
                dx = matrix[0][0] * sx + matrix[0][1] * sy + matrix[0][2] * sz + offsets[0]
                dy = matrix[1][0] * sx + matrix[1][1] * sy + matrix[1][2] * sz + offsets[1]
                dz = matrix[2][0] * sx + matrix[2][1] * sy + matrix[2][2] * sz + offsets[2]
                new_region[dx, dy, dz] = block

    _transform_entities(region, new_region, matrix, offsets)
    return new_region


def _transform_entities(
    region: Region,
    new_region: Region,
    matrix: Matrix,
    offsets: Sequence[int],
) -> None:
    """按同样的矩阵搬运实体与方块实体。"""

    def convert(px: float, py: float, pz: float) -> tuple[float, float, float]:
        return (
            matrix[0][0] * px + matrix[0][1] * py + matrix[0][2] * pz + offsets[0],
            matrix[1][0] * px + matrix[1][1] * py + matrix[1][2] * pz + offsets[1],
            matrix[2][0] * px + matrix[2][1] * py + matrix[2][2] * pz + offsets[2],
        )

    for te in region.tile_entities:
        data = Compound(dict(te.data))
        x, y, z = convert(float(data["x"]), float(data["y"]), float(data["z"]))
        data["x"] = Int(int(round(x)))
        data["y"] = Int(int(round(y)))
        data["z"] = Int(int(round(z)))
        new_region.tile_entities.append(TileEntity(data))

    for ent in region.entities:
        data = Compound(dict(ent.data))
        pos = [float(v) for v in data["Pos"]]
        x, y, z = convert(*pos)
        data["Pos"] = List[Double]([Double(x), Double(y), Double(z)])
        new_region.entities.append(Entity(data))


def transform_schematic(
    schem: Schematic,
    plan: TransformPlan,
    replacements: dict[str, str] | None = None,
    keep_properties: bool = False,
) -> Schematic:
    """变换整个投影文件（逐个区域处理）。"""
    new_schem = Schematic(
        name=schem.name,
        author=schem.author,
        description=schem.description,
        mc_version=schem.mc_version,
    )
    for name, region in schem.regions.items():
        resolved = plan_for_region(region, plan)
        matrix = build_matrix(resolved)
        new_schem.regions[name] = transform_region(region, matrix, replacements, keep_properties)
    return new_schem


def resolve_output_path(
    output_dir: str,
    src_path: str,
    suffix: str = "_transformed",
    used: set[str] | None = None,
) -> str:
    """算出一个不会互相覆盖的输出路径。

    ``used`` 是本次运行已经占用过的文件名集合（大小写不敏感）。
    """
    stem = os.path.splitext(os.path.basename(src_path))[0]
    name = f"{stem}{suffix}.litematic"

    if used is not None and name.lower() in used:
        tag = "csv" if src_path.lower().endswith(".csv") else "litematic"
        name = f"{stem}{suffix}_{tag}.litematic"
        index = 2
        while name.lower() in used:
            name = f"{stem}{suffix}_{tag}_{index}.litematic"
            index += 1

    if used is not None:
        used.add(name.lower())
    return os.path.join(output_dir, name)


def transform_file(
    src_path: str,
    dst_path: str,
    plan: TransformPlan,
    replacements: dict[str, str] | None = None,
    keep_properties: bool = False,
) -> dict:
    """转换单个文件并写出，返回处理摘要。"""
    if src_path.lower().endswith(".csv"):
        region, kind = load_region(src_path)
        resolved = plan_for_region(region, plan)
        matrix = build_matrix(resolved)
        new_region = transform_region(region, matrix, replacements, keep_properties)
        new_schem = Schematic(name=os.path.splitext(os.path.basename(src_path))[0])
        new_schem.regions["main"] = new_region
    else:
        schem = load_schematic(src_path)
        kind = "litematic"
        new_schem = transform_schematic(schem, plan, replacements, keep_properties)

    out_dir = os.path.dirname(os.path.abspath(dst_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    new_schem.save(dst_path)

    summary: dict = {
        "source": src_path,
        "output": dst_path,
        "kind": kind,
        "regions": [],
    }
    for name, region in new_schem.regions.items():
        dims = (abs(region.width), abs(region.height), abs(region.length))
        summary["regions"].append(
            {
                "name": name,
                "dims": list(dims),
                "normal": detect_normal_axis(dims),
                "blocks": int(region.count_blocks()),
            }
        )
    return summary


# --------------------------------------------------------------------------- #
# 预览
# --------------------------------------------------------------------------- #


def project_region(region: Region, normal_axis: str | None = None) -> dict:
    """把区域投影成正对图案的二维网格，用于前端预览。

    返回 ``{"cols": n, "rows": m, "palette": [...], "grid": [...]}``，
    ``grid`` 是行优先的调色板索引数组（-1 表示空）。
    """
    dims = (abs(region.width), abs(region.height), abs(region.length))
    if normal_axis is None:
        normal_axis = detect_normal_axis(dims)
    right, up, _ = FRAMES[normal_axis]

    axes = _store_axes(region)

    entries: list[tuple[int, int, BlockState]] = []
    for x, sx in axes[0]:
        for y, sy in axes[1]:
            for z, sz in axes[2]:
                block = region[x, y, z]
                if block.id == "minecraft:air":
                    continue
                vec = (sx, sy, sz)
                entries.append((_dot(vec, right), _dot(vec, up), block))

    if not entries:
        return {"cols": 0, "rows": 0, "palette": [], "grid": []}

    min_u = min(e[0] for e in entries)
    max_u = max(e[0] for e in entries)
    min_v = min(e[1] for e in entries)
    max_v = max(e[1] for e in entries)

    cols = max_u - min_u + 1
    rows = max_v - min_v + 1

    palette: list[str] = []
    index_of: dict[str, int] = {}
    grid = [-1] * (cols * rows)

    for u, v, block in entries:
        name = normalize_block_name(block.id)
        idx = index_of.get(name)
        if idx is None:
            idx = len(palette)
            index_of[name] = idx
            palette.append(name)
        row = max_v - v  # 第 0 行是图案最上面
        col = u - min_u
        grid[row * cols + col] = idx

    return {"cols": cols, "rows": rows, "palette": palette, "grid": grid}


def collect_block_names(region: Region) -> set[str]:
    """收集区域里出现过的方块名。"""
    names: set[str] = set()
    axes = _store_axes(region)
    for x, _ in axes[0]:
        for y, _ in axes[1]:
            for z, _ in axes[2]:
                block = region[x, y, z]
                if block.id != "minecraft:air":
                    names.add(normalize_block_name(block.id))
    return names


# --------------------------------------------------------------------------- #
# 调色板与输入文件
# --------------------------------------------------------------------------- #

#: 输入目录里认识的投影文件后缀
SUPPORTED_SUFFIXES = (".litematic", ".csv")


def block_color(name: str) -> tuple[int, int, int]:
    """方块名 -> RGB，取不到时用灰色。"""
    rgb = MC_BLOCKS.get(name)
    if rgb:
        r, g, b = rgb
        return (r, g, b)
    # 没在调色板里就按名字散列出一个稳定的灰阶，方便肉眼分辨
    v = 90 + (zlib.crc32(name.encode("utf-8")) % 110)
    return (v, v, v)


def list_input_files(input_dir: str) -> list[dict]:
    """列出输入目录里的投影文件。"""
    files: list[dict] = []
    if not os.path.isdir(input_dir):
        return files

    for name in sorted(os.listdir(input_dir)):
        if not name.lower().endswith(SUPPORTED_SUFFIXES):
            continue
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path):
            continue
        entry = {
            "name": name,
            "path": path,
            "size": os.path.getsize(path),
            "kind": "csv" if name.lower().endswith(".csv") else "litematic",
            "dims": None,
            "normal": None,
            "blocks": None,
            "error": None,
        }
        if len(files) < 200:
            try:
                region, _ = load_region(path)
                dims = (abs(region.width), abs(region.height), abs(region.length))
                entry["dims"] = list(dims)
                entry["normal"] = detect_normal_axis(dims)
                entry["blocks"] = int(region.count_blocks())
            except Exception as exc:
                entry["error"] = str(exc)
        files.append(entry)
    return files


# --------------------------------------------------------------------------- #
# 预览
# --------------------------------------------------------------------------- #


def palette_colors(palette: list[str]) -> list[list[int]]:
    """把调色板里的方块名换成一串 RGB。"""
    return [list(block_color(name)) for name in palette]


def preview_payload(region: Region, normal_axis: str | None = None) -> dict:
    """一个区域的投影预览数据（含配色、尺寸与法线轴）。"""
    data = project_region(region, normal_axis)
    data["colors"] = palette_colors(data["palette"])
    data["dims"] = [abs(region.width), abs(region.height), abs(region.length)]
    data["normal"] = normal_axis or detect_normal_axis(
        (abs(region.width), abs(region.height), abs(region.length))
    )
    return data


def preview_file(path: str, plan: TransformPlan, replacements: dict | None = None) -> dict:
    """生成单个文件转换前 / 后的预览数据。"""
    region, kind = load_region(path)
    before = preview_payload(region)

    try:
        resolved = plan_for_region(region, plan)
        matrix = build_matrix(resolved)
        new_region = transform_region(region, matrix, replacements, False)
        after = preview_payload(new_region)
    except Exception as exc:
        after = {
            "cols": 0,
            "rows": 0,
            "palette": [],
            "colors": [],
            "grid": [],
            "dims": [0, 0, 0],
            "error": str(exc),
        }

    return {
        "kind": kind,
        "before": before,
        "after": after,
        "dims_before": before["dims"],
        "dims_after": after["dims"],
    }
