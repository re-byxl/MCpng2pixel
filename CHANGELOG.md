# 更新日志

显著变化都记在这里。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-10-27

### 新增

- 更名为 **pixelmatic**（原 mcyqqs），正式包结构：src 布局、pydantic 配置校验、
  命令行入口 `pixelmatic`
- **黄金样本回归**：确定性参考图 → CSV 与 `.litematic` 逐字节比对，
  基线用 `tests/golden/config.json` 固定配置
- 本更新日志；`input_images/README.md` 说明输入目录用途

### 变更

- **工具配置与 `config.json` 分离**：网页工具保存的运行时状态写到本地
  `.pixelmatic/tool_state.json`（不进版本库），`config.json` 的 `tool` 节只当
  出厂默认读 —— 之前「保存设置」会整体重写 `config.json`（改缩进、相对路径
  变绝对路径、字符串 `"9"` 变数字），会把机器本地的污染带进仓库
- 网页前端的「刷新」按钮不再隐式保存设置
- `blue_penalty` 默认值全部改为 0（默认不启用）；`config.json` 里已显式写 0，
  行为不变
- `pixelmatic tool` 与 `python -m pixelmatic.tool` 共用同一套参数定义，
  `pixelmatic --config X tool` 不再丢失 `--config`

### 修复

- 灰度图读取崩溃（访问 `shape[2]` 的 IndexError），统一转成三通道再处理
- HTTP 服务加固：坏 JSON / 错误 Content-Type 返回 400；Host 头只认本机回环
  （防 DNS 重绑定）；GET 未捕获异常返回 500 JSON；批量转换单个文件失败
  只记日志、不再拖垮整批任务
- 前端：任务出错时日志不再被清空；方块自动补全列表先于替换规则渲染

### 内部

- `matching/energy.py` 的 CIEDE2000 调用批量化（结果与逐格版逐位一致），
  删除重复的细节权重计算与孤儿函数
- 调色板预计算在 `convert` 全流程只做一次
- CSV 写出、立面区域构造（`cells_to_region`）各收敛到单一实现
- `pipeline/grid.py` 的异常输出走 logging；清理测试支撑里旧扁平脚本时代的
  回退代码

## [0.1.0] - 2026-10-01

- 最初可用版本：图片 → 方块清单 → `.litematic` 流水线（扁平脚本布局）
- 方向转换与方块替换的网页工具
