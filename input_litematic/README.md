# 输入的投影文件

把需要做方向转换 / 方块替换的 **.litematic** 文件放进这个文件夹。

也可以直接放 **.csv** 清单（`x,y,block` 三列，与 `pixelmatic convert` 产出的格式一致），
工具会自动把它当成一张立面画来处理。

运行工具：

```bash
python -m pixelmatic.tool          # 打开网页前端
python -m pixelmatic.tool --cli    # 命令行批量处理本目录里的全部文件
```

输出默认写到 `output/litematic_transformed/`。
