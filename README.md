# MCpng2pixel

把图片转换成 Minecraft 方块投影（`.litematic`），并提供方向转换、方块替换与投稿产物生成。

- 图片 → 网格对齐 → 每格取色 → 方块匹配 → 背景清理 → `.litematic`
- 投影可以换方向（墙面画 ↔ 地面平铺）、旋转、镜像
- 匹配时顺带批量替换方块
- 自带网页前端，可以边调参数边看预览

---

## 安装

用 [uv](https://github.com/astral-sh/uv) 管理依赖：

```bash
uv sync            # 装运行时依赖
uv sync --dev      # 连测试、lint、类型检查工具一起装
```

装完会有两个命令：`mcyqqs`（主命令）和 `python -m mcyqqs.tool`（方向转换工具）。

---

## 快速开始

```bash
# 1. 把图片放进 input_images/
# 2. 转换
mcyqqs convert

# 只想看网格切得对不对
mcyqqs debug grid

# 每格取色的结果（方块匹配之前的"参考图"）
mcyqqs debug color

# 方向转换工具的网页前端（默认 http://127.0.0.1:8765）
mcyqqs tool
```

`mcyqqs convert` 的产出：

```
output/
  preview/       方块匹配预览图（平涂的方块色）
  csv/           方块清单（x, y, block）
  litematic/     可导入 Litematica 的投影文件
debug/
  grid_output_images/  网格叠加图
  color_preview/       每格平均色预览
  grid_debug.txt       网格检测参数
```

---

## 目录结构

```
src/mcyqqs/                正式包（pip install 后可用）
  cli.py                   命令行入口：convert / debug / tool
  config.py                配置模型（唯一配置来源）
  pipeline/                图片流水线
    grid.py                网格检测与对齐
    color.py               每格取色
    match.py               方块匹配（读写 CSV 与预览图）
    postprocess.py         背景黑色清理
    export.py              CSV → .litematic
    debug.py               诊断视图
  matching/                匹配算法
    palette.py             调色板加载（数据在 palette.json）
    color.py               sRGB / Lab / CIEDE2000
    energy.py              目标函数 + ICM 求解器
    modes.py               匹配模式预设
  litematic/core.py        方向转换与方块替换（纯逻辑）
  tool/                    网页前端
    server.py              本地 HTTP 服务 + JSON API
    cli.py                 工具的命令行
    web/                   前端页面（无构建步骤）
tests/                     pytest + 黄金样本回归
tools/palette_extract.py   从材质图重新生成调色板
config.json                唯一配置文件
```

---

## 配置

所有参数都在 `config.json` 里，改完直接生效（不需要重启什么）。

```json
{
    "block_size": "9",
    "grid_cells": "auto",
    "mode": "quality",
    "skip_litematic": false,
    "skip_postprocess": true,

    "paths": {
        "input_dir": "input_images",
        "output_preview": "output/preview",
        "output_csv": "output/csv",
        "output_litematic": "output/litematic",
        "debug_dir": "debug",
        "color_debug": "debug/color_preview",
        "grid_output_dir": "debug/grid_output_images"
    },

    "cell": { "margin": 2 },

    "grid": {
        "min_block": 9,
        "center_ratio": 0.45,
        "smooth_window": 9,
        "shift_radius": 4
    },

    "blue_penalty": {
        "threshold_b": 0,
        "penalty_purple": 0,
        "penalty_pink": 0
    },

    "neutral_mask": { "enabled": true },

    "tool": {
        "input_dir": "input_litematic",
        "output_dir": "output/litematic_transformed",
        "suffix": "_transformed",
        "overwrite": true,
        "keep_properties": false,
        "plan": {
            "source_normal": "auto",
            "target_normal": "keep",
            "rotation": 0,
            "mirror_h": false,
            "mirror_v": false,
            "rotate_x": 0,
            "rotate_y": 0,
            "rotate_z": 0
        },
        "replacements": {
            "red_concrete": "red_terracotta"
        }
    }
}
```

配置由 pydantic 校验：**缺 key 或类型写错会直接报错**，不会静默回落到默认值。
用别的配置文件：`mcyqqs --config my.json convert`。

### 基础配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `block_size` | 方块大小（像素），设为 `"auto"` 由 `grid_cells` 自动计算 | "auto" |
| `grid_cells` | 目标网格大小，如 `"64"`、`"64x48"` 或 `"auto"` | "auto" |
| `mode` | 匹配模式，见下方 | "balanced" |
| `skip_litematic` | 是否跳过 `.litematic` 生成 | false |
| `skip_postprocess` | 是否跳过背景黑色后处理 | false |

### 颜色惩罚 (blue_penalty)

解决蓝色系被误判成紫/粉的问题。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `threshold_b` | LAB 空间 b 通道阈值，低于此值认为是蓝色调 | -15 |
| `penalty_purple` | 对紫色/品红方块的惩罚值 | 25 |
| `penalty_pink` | 对粉色方块的惩罚值 | 20 |

**LAB 空间**：L 是亮度（0-100），a 是绿-红，b 是蓝-黄。

| 问题表现 | 调整建议 |
|----------|----------|
| 蓝色被匹配为粉色 | `threshold_b` 调到 `-25` 或更低 |
| 蓝色被匹配为紫色 | `penalty_purple` 增加 5-10 |
| 整体偏橙红 | `threshold_b` 调到 `-10` 或 `-5` |
| 偏色问题严重 | 两个惩罚值减半 |

### 中性色保护 (neutral_mask)

源颜色彩度高时保护白/灰/黑，避免被"吞掉"。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `enabled` | 是否启用 | false |

---

## 流水线

| 阶段 | 模块 | 作用 |
|------|------|------|
| 1 | `pipeline/grid.py` | Canny 裁剪 → 梯度投影 → 相位搜索 → 网格对齐 |
| 2 | `pipeline/match.py` | 每格平均色 → CIEDE2000 打分 → ICM 优化 → CSV + 预览图 |
| 3 | `pipeline/postprocess.py` | 背景黑色换成空气，保留前景黑色与 1 格描边 |
| 4 | `pipeline/export.py` | CSV → `.litematic`（法线朝 Z 的立面） |

阶段 1 和 2 里的调试图（`mcyqqs debug grid` / `mcyqqs debug color`）只是诊断视图，
不参与主流程的产出。

### 匹配模式

| 模式 | 说明 |
|------|------|
| `quality` | 高质量，8 轮迭代（默认） |
| `balanced` | 平衡，3 轮迭代 |
| `color_priority` | 优先保留原图颜色 |
| `contrast_priority` | 优先保留局部对比 |
| `smooth_priority` | 优先整体平滑 |

模式参数在 `src/mcyqqs/matching/modes.py`，每一项都有 pydantic 校验。

| 参数 | 说明 | 常用值范围 |
|------|------|------------|
| `top_k` | 候选方块数量，越大越精细但越慢 | 6-14 |
| `repeat_threshold` | 重复惩罚阈值（CIEDE2000） | 6-10 |
| `repeat_penalty` | 重复惩罚强度 | 6-14 |
| `contrast_weight` | 对比度权重，边缘保护 | 0.28-0.55 |
| `lightness_weight` | 亮度权重 | 0.10-0.16 |
| `chroma_weight` | 色度权重 | 0.15-0.38 |
| `chroma_loss_weight` | 色度损失权重 | 0.45-1.00 |
| `pastel_chroma_threshold` | 粉色系检测阈值 | 10-14 |
| `neutral_chroma_threshold` | 中性色检测阈值 | 8 |
| `iterations` | 迭代次数 | 2-8 |
| `edge_weight` | 边缘权重 | 0.20-0.70 |
| `detail_weight` | 细节权重 | 0.10-0.35 |

### 数据契约

**方块清单 CSV**（`output/csv/*.csv`）——编码 UTF-8 with BOM，换行固定 `\n`：

```csv
x,y,block
0,0,snow_block
1,0,red_concrete
```

- `x` 是列号（0 = 最左），`y` 是行号（**0 = 图片最上面一行**）
- `block` 是方块名（不带 `minecraft:` 前缀）；`air` 表示空
- 写成 `.litematic` 时 Y 轴会翻转（`y_mc = max_y - 1 - y`），所以贴出来的画是正的

**预览图 PNG**（`output/preview/*.png`）——与裁剪后的图片同尺寸，每格平涂一种方块色，
不含纹理、光照和环境光遮蔽。它是给人看的，不能直接和游戏截图对比。

**投影 `.litematic`**——1 层厚、法线朝 Z 的立面，区域名 `main`。

---

## 方向转换工具

把 `.litematic` 换个方向（墙面画 ↔ 地面平铺）、旋转、镜像，同时批量替换方块。

```bash
mcyqqs tool                      # 网页前端
mcyqqs tool --cli --target y     # 命令行批量转换
mcyqqs tool --cli --target y --rotation 90 --replace red_concrete=red_terracotta
```

输入目录默认 `input_litematic/`，输出默认 `output/litematic_transformed/`。
也支持直接吃 `.csv` 清单（`x,y,block` 三列），会当成一张立面画处理。

### 网页前端

界面分三栏：左栏选文件，中间调方向并看**转换前 / 转换后**的彩色预览，
右栏编辑方块替换规则、看运行日志。预览是正对图案渲染的 ——
墙面画按正面（+Z 侧）看，地面平铺按俯视看，所以"地面平铺"的预览应该和原图长得一样。

网址参数可以直接预设方向，方便收藏：`?target=y&rotation=90`。

### 方向约定

Minecraft 是右手系（+X 东，+Y 上，+Z 南）。描述一个平面图案的朝向用
(right, up, normal) 三元组，其中 right × up = normal：

| 法线轴 | right | up | 观察方式 |
|--------|-------|----|----------|
| `z` | +X | +Y | 站在 +Z 侧平视（贴墙的画） |
| `y` | +X | -Z | 从上往下俯视（地面平铺） |
| `x` | -Z | +Y | 站在 +X 侧平视（侧面的画） |

因为这套约定做的是**旋转**而不是镜像，"墙面 → 地面平铺"之后从上往下看，
画面方向和原来完全一致。

「原图案所在平面」默认自动识别（取尺寸最小的那个轴：`110×149×1` 判定为立面，
`110×1×149` 判定为地面），也可以手动指定。

### 方块替换

规则写成 `原方块 = 新方块`：

- 规则键可以写 `red_concrete`，也可以写完整的 `minecraft:red_concrete`
- 规则值留空或填 `air` 表示删掉该方块
- 默认**不保留**方块属性（楼梯的朝向之类），需要保留就勾上「保留方块属性」

---

## 开发

```bash
uv sync --dev

uv run pytest                      # 测试（含黄金样本回归）
uv run pytest --cov=src/mcyqqs    # 带覆盖率
uv run ruff check .                # lint
uv run ruff format .               # 格式化
uv run mypy                        # 类型检查
```

### 黄金样本回归

`tests/golden/` 里存着一张确定性生成的参考图和它的**期望输出**（CSV 与投影的逐格内容）。
`tests/test_golden.py` 每次都会跑一遍完整流水线并逐字节比对。

这是重构的安全网：**流水线行为一旦变了，测试就会红**。

只有在明确知道自己在改行为时才应该重新生成基线：

```bash
uv run python tests/generate_baseline.py
```

### 重新生成调色板

调色板是数据，存放在 `src/mcyqqs/matching/palette.json`。
需要从材质图重新采样时：

```bash
uv run --with pandas --with scipy --with pillow python tools/palette_extract.py
```

（`MCblocks.png` 不在版本库里，需要自己准备一张 9×6 排布的方块材质图。）

---

## 常见问题

### 调试流程

1. `mcyqqs debug grid` 看网格切得对不对 —— 绿色线应该正好压在格子边界上
2. 对比 `debug/color_preview/`（每格平均色）和 `output/preview/`（匹配结果）
   —— 前者正常、后者偏色，说明问题在匹配算法
3. `debug/grid_debug.txt` 里有每次的网格锚点、格子数和丢弃的像素

### 快速修复参考

| 问题 | 最简单的修复方法 |
|------|------------------|
| 蓝色变紫色/粉色 | `blue_penalty.threshold_b` 降到 `-25` |
| 整体偏橙红 | `blue_penalty.threshold_b` 提到 `-5`，或把整节删掉 |
| 边缘白色方块 | 降低 `edge_weight` 和 `detail_weight` |
| 浅色偏暗 | 提高 `lightness_weight` |
| 颜色发灰 | 提高 `chroma_weight`、降低 `edge_weight` |

### 命名与投稿

投稿用的命名规范、清单格式和发布模板见 [Name_suggestion.md](Name_suggestion.md)。
