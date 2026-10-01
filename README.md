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
    "block_size": "auto",
    "grid_cells": "auto",
    "mode": "balanced",
    "skip_litematic": false
}
```

| 配置项 | 说明 |
|--------|------|
| `block_size` | 方块大小（像素），设为 `"auto"` 由 `grid_cells` 自动计算 |
| `grid_cells` | 目标网格大小，如 `"64"`（64×64）、`"64x48"`（64×48）或 `"auto"` |
| `mode` | 匹配模式，见下方匹配模式说明 |
| `skip_litematic` | 是否跳过 `.litematic` 生成 |

命令行覆盖：

```bash
python main.py                           # 使用默认 config.json
python main.py --config my.json          # 使用指定配置文件
python main.py --block-size 20           # 临时覆盖方块大小
python main.py --grid-cells 100          # 临时覆盖目标网格大小
python main.py --mode quality            # 临时覆盖匹配模式
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
  grid_debug.txt        网格切分参数
```

## 使用流程

1. 将图片放入 `input_images/`
2. 运行 `python main.py`
3. 查看 `output/preview/` 中的匹配预览
4. 查看 `output/csv/` 中的方块清单
5. 查看 `output/litematic/` 中的可导入文件

## 脚本说明

| 脚本 | 功能 |
|------|------|
| `main.py` | 完整流水线入口 |
| `1grid.py` | 检查网格切分是否正确 |
| `2color.py` | 生成每格平均色预览 |
| `3match.py` | 方块匹配，生成预览图和 CSV |
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

## 调色板

编辑 `palette.py` 自定义方块调色板，`MCblocks.png` 为参考图片。
