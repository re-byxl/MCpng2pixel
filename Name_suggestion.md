## 1. 命名模板

```
{分类}_{名称}_{尺寸}_{变体}_{修订}[_{分段}].{扩展名}
```

示例：

```
CHR_Pikachu_64x64x1_default_r1.litematic
LND_MountFuji-Sunset_128x72x1_wool_r2.litematic
LOG_Anthropic_32x32x1_survival_r1.litematic
CHR_Eevee_96x96x1_default_r1_p2of4.litematic
```

## 2. 字段定义

| 序号 | 字段 | 英文名 | 格式 | 说明 |
|---|---|---|---|---|
| 1 | 分类 | Category | 3 位大写字母 | 见分类表 |
| 2 | 名称 | Name | PascalCase，子标题用 `-` 连接 | 纯英文/拼音 |
| 3 | 尺寸 | Size | `宽x高x深` | 单位为方块；竖直墙面画为 `64x64x1`，平铺地面画为 `64x1x64` |
| 4 | 变体 | Variant | 小写字母/数字/`-` | 见变体表 |
| 5 | 修订 | Revision | `r` + 整数 | 内容修改时递增 |
| 6 | 分段（可选） | Part | `p{n}of{N}` | 大图拆分时使用 |

## 3. 变体码表

| 代码 | English Name | 中文名称 | 含义 |
|---|---|---|---|
| `default` | Default | 默认 | 你的标准配方（默认调色板与处理方式），无特殊要求时使用 |
| `full` | Full Palette | 全方块 | 含创造模式专属方块 |
| `survival` | Survival | 生存 | 仅含生存模式可获取方块 |
| `wool` | Wool | 羊毛 | 仅羊毛 |
| `concrete` | Concrete | 混凝土 | 仅混凝土 |
| `terracotta` | Terracotta | 陶瓦 | 仅陶瓦/彩色陶瓦 |
| `stair` | Staircase | 阶梯 | 利用高度差明暗的 3D 地图画 |
| `dither` | Dither | 抖动 | 含抖动处理 |
| `mono` | Monochrome | 单色 | 单色/灰度 |

- 组合用 `-` 连接，如 `survival-dither`。
- `default` 不与其他变体组合；有任何特殊特征时，不写 `default`。

## 4. 命名规则（修订）

1. 文件名只用 ASCII：`A-Z a-z 0-9 _ - .`。
2. 字段间用 `_` 分隔，字段内部不得出现 `_`。
3. 分类在最前，同类文件自动聚集。
4. 修订号只增不减，旧版本保留在 `archive/`。
5. 游戏版本不再体现在文件名中，改记录于 `index.csv`。

## 5. `index.csv` 修订

新增一列保存游戏版本：

| 列名 | 说明 |
|---|---|
| `filename` | 完整文件名（主键） |
| `name_zh` | 中文名称 |
| `mc_version` | **新增**：导出所用游戏版本，如 `1.21` |
| `source` | 原图来源/作者 |
| `block_count` | 方块总数 |
| `created` | 创建日期（`YYYY-MM-DD`） |
| `notes` | 备注 |

## 6. 校验脚本修订

**文件**：`tools/naming.py`（命名校验模块 / Naming Validation Module）
**位置**：替换原 `FILENAME_PATTERN` 整段定义，`parse_filename` 函数无需改动。

```python
FILENAME_PATTERN = re.compile(
    r"^(?P<category>[A-Z]{3})"
    r"_(?P<name>[A-Z][A-Za-z0-9]*(?:-[A-Z][A-Za-z0-9]*)*)"
    r"_(?P<width>\d+)x(?P<height>\d+)x(?P<depth>\d+)"
    r"_(?P<variant>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"_r(?P<revision>\d+)"
    r"(?:_p(?P<part>\d+)of(?P<total_parts>\d+))?"
    r"\.(?P<ext>litematic|schem|nbt)$"
)
```



# 蓝图网站发布规范

## 1. 发布字段总览

| 字段 | English Name | 长度建议 | 来源 |
|---|---|---|---|
| 标题 | Title | ≤ 40 字符 | 文件名 + `index.csv` |
| 摘要 | Summary | ≤ 100 字符 | 模板生成 |
| 正文 | Body | 不限 | 模板生成 |
| 版本信息 | Version Info | 结构化 | `index.csv` |

实际字数上限以目标网站为准，超限时按"名称 > 尺寸 > 变体"的优先级保留。

## 2. 标题规范

```
{名称中文} {NameEnglish}｜{宽}×{高}×{深}｜{变体中文}
```

| 示例 |
|---|
| `皮卡丘 Pikachu｜64×64×1｜默认` |
| `富士山日落 Mount Fuji Sunset｜128×72×1｜羊毛` |
| `伊布 Eevee｜96×96×1｜默认（第 2/4 部分）` |

规则：

1. 中文名在前，便于搜索；英文名由文件名 PascalCase 拆分得到。
2. 尺寸用 `×` 而非 `x`，且始终写满三维。
3. 分段文件末尾追加 `（第 n/N 部分）`。
4. 不加分类前缀，分类通过站点的标签或分类字段填写。
5. 标题不含修订号，修订号放入版本信息。

## 3. 摘要规范

```
{名称中文}（{NameEnglish}）{宽}×{高}×{深} 像素画投影，{变体中文}配方，共 {block_count} 个方块，适用 Minecraft {mc_version}。
```

示例：

> 皮卡丘（Pikachu）64×64×1 像素画投影，默认配方，共 3,842 个方块，适用 Minecraft 1.21。

规则：一句话，只写事实（内容、尺寸、方块数、游戏版本），不写评价性形容词。

## 4. 正文规范

正文固定为以下 6 个章节，顺序不变，缺失内容写"无"：

```markdown
## 简介
{一至两句话介绍原图主题，可附原作者}

## 规格
| 项目 | 内容 |
|---|---|
| 尺寸 | 64×64×1 |
| 方块总数 | 3,842 |
| 变体 | 默认 |
| 摆放方向 | 竖直墙面（朝南） |

## 建造说明
- 粘贴位置：{基准点，如"左下角为原点"}
- 所需模组：Litematica（{版本}）
- 材料清单：见 Litematica 材料列表

## 版本信息
{见第 5 节}

## 来源与授权
- 原图来源：{source}
- 授权：{license}

## 标签
{tag1}, {tag2}, {tag3}
```

## 5. 版本信息规范

版本信息拆为三类，各自独立记录：

| 项目 | English Name | 格式 | 说明 |
|---|---|---|---|
| 文件修订 | File Revision | `r{n}` | 与文件名中的修订号完全一致 |
| 游戏版本 | MC Version | `1.21` / `1.20.4` | 导出投影所用的游戏版本 |
| 兼容范围 | Compatibility | `1.20.4 – 1.21` | 选填，仅在实测过其他版本时填写 |
| 更新日志 | Changelog | 每行一条 | 每次修订必须有一条 |

更新日志格式（倒序，最新在前）：

```
r2 (2025-03-18): 修正右下角颜色偏差；替换 12 个不可生存获取的方块
r1 (2025-03-10): 首次发布
```

规则：

1. 站点版本号字段统一填 `r{n}`，不使用 `v1.0` 等其他体系。
2. 游戏版本以导出时实际版本为准，未实测的版本不得写入兼容范围。
3. 每次内容改动都递增 `r`，同步更新日志，旧文件归档到 `archive/`。
4. 首次发布固定为 `r1`。