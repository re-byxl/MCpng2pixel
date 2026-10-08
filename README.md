# MCYQQS

将图片转换为 Minecraft 方块图案，支持透明PNG处理，导出调试图、预览图、CSV 和 `.litematic` 文件。

## 依赖环境

使用 [uv](https://github.com/astral-sh/uv) 管理依赖：

```bash
uv sync
```

## 配置

所有参数通过 `config.json` 统一配置：

```json
{
    "block_size": "9",
    "grid_cells": "auto",
    "mode": "contrast_priority",
    "skip_litematic": false,
    "skip_postprocess": false,
    "blue_penalty": {
        "threshold_b": -15,
        "penalty_purple": 25,
        "penalty_pink": 20
    },
    "neutral_mask": {
        "enabled": false
    },
    "paths": {
        "input_dir": "input_images",
        "output_preview": "output/preview",
        "output_csv": "output/csv",
        "debug_dir": "debug",
        "color_debug": "debug/color_preview"
    },
    "cell": {
        "margin": 4
    },
    "grid": {
        "min_block": 6,
        "center_ratio": 0.45,
        "smooth_window": 9,
        "shift_radius": 4
    }
}
```

### 基础配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `block_size` | 方块大小（像素），设为 `"auto"` 由 `grid_cells` 自动计算 | "9" |
| `grid_cells` | 目标网格大小，如 `"64"`（64×64）、`"64x48"`（64×48）或 `"auto"` | "auto" |
| `mode` | 匹配模式，见下方匹配模式说明 | "contrast_priority" |
| `skip_litematic` | 是否跳过 `.litematic` 生成 | false |
| `skip_postprocess` | 是否跳过背景黑色删除后处理 | false |

### 颜色惩罚配置 (blue_penalty)

用于解决蓝色系被错误匹配为紫色/粉色的问题。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `threshold_b` | LAB 颜色空间中 b 通道阈值，低于此值认为是蓝色调 | -15 |
| `penalty_purple` | 对紫色/品红方块添加的惩罚值 | 25 |
| `penalty_pink` | 对粉色方块添加的惩罚值 | 20 |

**LAB 颜色空间说明**：
- L 通道：亮度（0-100），越大越亮
- a 通道：绿-红（负值偏绿，正值偏红）
- b 通道：蓝-黄（负值偏蓝，正值偏黄）

**调色板关键颜色的 LAB 参考值**：

| 方块 | L | a | b | 特点 |
|------|---|---|---|------|
| light_blue_concrete_powder | 66.8 | -18.3 | -25.2 | 浅蓝色调 |
| blue_concrete_powder | 37.2 | 24.1 | -47.7 | 深蓝色调 |
| pink_concrete_powder | 68.9 | 29.2 | -4.4 | 暖粉色 |
| purple_concrete_powder | 39.9 | 48.5 | -48.4 | 紫色调 |
| white_concrete_powder | 86.2 | -0.5 | -1.8 | 近中性白 |
| snow_block | 94.4 | -1.4 | -2.1 | 最亮白 |

**blue_penalty 参数调整指南**：

| 问题表现 | 原因 | 调整建议 |
|----------|------|----------|
| 蓝色被匹配为粉色 | threshold_b 阈值过大，误判蓝色 | 将 `threshold_b` 改为 `-25` 或更低 |
| 蓝色被匹配为紫色 | 紫色惩罚不够 | 将 `penalty_purple` 增加 5-10 |
| 整体偏橙红色 | threshold_b 过小，误伤暖色调 | 将 `threshold_b` 改为 `-10` 或 `-5`，或完全移除 blue_penalty |
| 偏色问题严重 | 惩罚值过大 | 将 `penalty_purple` 和 `penalty_pink` 减半 |

**完全禁用 blue_penalty**：将整个 `blue_penalty` 节从 config.json 中删除即可。

### 中性色保护配置 (neutral_mask)

用于在高色度颜色匹配时保护白/灰/黑等中性色方块。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `enabled` | 是否启用中性色保护 | false |

**启用条件**：当源颜色色度 `src_chroma >= pastel_chroma_threshold`（由匹配模式参数控制）时生效。

**效果**：对调色板中色度较低的中性色方块添加额外惩罚，防止高色度颜色被白/灰/黑色方块"吞掉"。

**完全禁用 neutral_mask**：在 config.json 中设置 `"enabled": false` 或删除 `neutral_mask` 节。

### 路径配置 (paths)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `input_dir` | 输入图片目录 | "input_images" |
| `output_preview` | 方块匹配预览图输出目录 | "output/preview" |
| `output_csv` | CSV 文件输出目录 | "output/csv" |
| `debug_dir` | 调试文件目录 | "debug" |
| `color_debug` | 每格平均色预览图目录 | "debug/color_preview" |

### 格子配置 (cell)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `margin` | 每个格子边缘排除的像素数（用于避免边界颜色干扰） | 4 |

### 网格配置 (grid)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `min_block` | 最小方块大小（像素） | 6 |
| `center_ratio` | 中心窗口比例，用于锚点检测 | 0.45 |
| `smooth_window` | 平滑窗口大小，用于梯度信号处理 | 9 |
| `shift_radius` | 偏移搜索半径，用于微调网格锚点 | 4 |

命令行覆盖：

```bash
python main.py                           # 使用默认 config.json
python main.py --config my.json          # 使用指定配置文件
python main.py --block-size 20           # 临时覆盖方块大小
python main.py --grid-cells 100          # 临时覆盖目标网格大小
python main.py --mode quality             # 临时覆盖匹配模式
python main.py --skip-postprocess         # 跳过背景黑色删除后处理
```

## 目录结构

```
input_images/          原始输入图片（支持 PNG、JPG）
output/
  preview/             方块匹配预览图
  csv/                 方块清单（x, y, block）
  litematic/           .litematic 文件
debug/                 调试输出
  grid_output_images/  网格调试图
  color_preview/       每格平均色预览
  grid_debug.txt       网格切分参数
```

## 使用流程

1. 将图片放入 `input_images/`
2. 运行 `python main.py`
3. 查看 `output/preview/` 中的匹配预览
4. 查看 `output/csv/` 中的方块清单
5. 查看 `output/litematic/` 中的可导入文件

## 流水线步骤

| 步骤 | 脚本 | 功能 |
|------|------|------|
| STEP 1/4 | `1grid.py` | 网格切分 |
| STEP 2/4 | `2color.py` | 平均色提取 |
| STEP 3/4 | `3match.py` | 方块匹配 |
| STEP 3.5/4 | `3postprocess.py` | 删除背景黑色，保留描边和前景黑色 |
| STEP 4/4 | `4litematic.py` | 生成 `.litematic` |

## 脚本说明

| 脚本 | 功能 |
|------|------|
| `main.py` | 完整流水线入口 |
| `1grid.py` | 检查网格切分是否正确 |
| `2color.py` | 生成每格平均色预览 |
| `3match.py` | 方块匹配，生成预览图和 CSV |
| `3postprocess.py` | 后处理：删除背景黑色 |
| `4litematic.py` | CSV 转 `.litematic` |
| `5replace.py` | 替换部分方块后重新生成 |

## 匹配模式

| 模式 | 说明 |
|------|------|
| `quality` | 高质量模式，8轮迭代优化 |
| `balanced` | 平衡模式（默认），3轮迭代 |
| `color_priority` | 优先保留原图颜色，4轮迭代 |
| `contrast_priority` | 优先保留局部对比，5轮迭代 |
| `smooth_priority` | 优先整体平滑，2轮迭代 |

匹配模式参数（位于 `match_modes.py`）：

| 参数 | 说明 | 常用值范围 |
|------|------|------------|
| `top_k` | 候选方块数量，越大越精细但越慢 | 6-14 |
| `repeat_threshold` | 重复惩罚阈值（CIEDE2000） | 6-10 |
| `repeat_penalty` | 重复惩罚强度 | 6-14 |
| `contrast_weight` | 对比度权重，边缘保护 | 0.28-0.55 |
| `lightness_weight` | 亮度权重，亮度匹配精度 | 0.10-0.16 |
| `chroma_weight` | 色度权重，颜色纯度匹配 | 0.15-0.38 |
| `chroma_loss_weight` | 色度损失权重 | 0.45-1.00 |
| `pastel_chroma_threshold` | 粉色系检测阈值 | 10-14 |
| `neutral_chroma_threshold` | 中性色（白/灰/黑）检测阈值 | 8 |
| `iterations` | 迭代次数，越多越精细但越慢 | 2-8 |
| `edge_weight` | 边缘权重，边缘清晰度 | 0.20-0.70 |
| `detail_weight` | 细节权重 | 0.10-0.35 |

**匹配模式参数调整指南**：

| 问题表现 | 原因 | 调整建议 |
|----------|------|----------|
| 浅色/肤色偏暗 | lightness_weight 太低 | 增加 `lightness_weight` 到 0.15-0.20 |
| 颜色偏灰/偏白 | chroma_weight 太低 | 增加 `chroma_weight` 到 0.25-0.35 |
| 边缘模糊/白色方块出现在交界处 | edge_weight 太高 | 降低 `edge_weight` 到 0.30-0.40 |
| 深色线条出现白色描边 | edge_weight 太高 + detail_weight 太高 | 同时降低两者 |
| 相邻不同颜色塌成同一种 | edge_weight 太低 | 增加 `edge_weight` 到 0.50 以上 |
| 整体颜色正确但细节差 | iterations 太低 | 增加 `iterations` 到 5-8 |
| 匹配结果过于杂乱 | iterations 太高 | 减少 `iterations` 到 2-3 |

**模式选择建议**：
- `quality`：对质量要求高，不介意等待
- `balanced`：默认选择，兼顾效果和速度
- `color_priority`：原图颜色丰富鲜艳时使用
- `contrast_priority`：线条/边缘清晰时使用（当前默认）
- `smooth_priority`：需要整体平整效果时使用

## 调色板

编辑 `palette.py` 自定义方块调色板，`MCblocks.png` 为参考图片。

## 背景黑色后处理

`3postprocess.py` 在方块匹配后执行，用于处理 `black_concrete` 方块：

| 处理类型 | 说明 |
|----------|------|
| 删除背景黑色 | 删除与图像边框相连的 `black_concrete` |
| 保留前景黑色 | 保留前景内部的 `black_concrete`（如瞳孔、黑色衣物） |
| 保留描边 | 在背景与前景交界处保留 1 像素宽的黑色描边 |
| 填充空气 | 删除的黑色方块替换为 `air`（空气/透明方块） |

**跳过此步骤**：使用 `--skip-postprocess` 或在 config.json 中设置 `"skip_postprocess": true`

**算法说明**：
1. BFS 从图像四边出发，标记所有与边框相连的 `black_concrete`
2. 多源 BFS 计算每个格子到最近前景的曼哈顿距离
3. 背景黑色中距离=1的作为描边保留，其他替换为空气

## 常见问题排查

### 调试流程

1. **对比 color_preview 和 output/preview**
   - `debug/color_preview/` 是每格平均色（无匹配优化）
   - `output/preview/` 是最终匹配结果
   - 如果 color_preview 正常但 output/preview 偏色，说明问题在匹配算法

2. **尝试不同匹配模式**
   - 使用 `--mode balanced` 或 `--mode color_priority` 测试
   - 不同模式对同一张图效果可能差异很大

3. **调整 block_size**
   - 较小的 block_size（如 6-8）保留更多细节
   - 较大的 block_size（如 12-16）更抽象但更整齐

### 快速修复参考

| 问题 | 最简单的修复方法 |
|------|------------------|
| 蓝色变紫色/粉色 | 在 `blue_penalty` 中降低 `threshold_b` 到 `-25` |
| 整体偏橙红 | 在 `blue_penalty` 中提高 `threshold_b` 到 `-5`，或删除该节 |
| 边缘白色方块 | 降低匹配模式的 `edge_weight` 和 `detail_weight` |
| 浅色偏暗 | 提高匹配模式的 `lightness_weight` |
| 颜色发灰 | 提高匹配模式的 `chroma_weight` 并降低 `edge_weight` |
