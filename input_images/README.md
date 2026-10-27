# 输入的图片

把要转换成方块投影的图片放进这个文件夹（PNG / JPG）。

```bash
pixelmatic convert        # 转换本目录里的全部图片
pixelmatic debug grid     # 只看网格切得对不对
pixelmatic debug color    # 只看每格取色
```

方块大小、匹配模式等参数在仓库根目录的 `config.json` 里调；
产出在 `output/`（预览图、CSV 清单、`.litematic` 投影）。
