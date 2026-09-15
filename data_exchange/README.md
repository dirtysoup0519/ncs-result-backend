# 数据交换目录

- `packages/`：放置待导入的 ADS v2.5 解压目录、`.zip` 或 `.tar.gz` 数据包。
- `models/`：放置外部交付的模型目录、ZIP 或 `.pth` 权重。
- `exports/`：`export_dataset.cmd` 生成的数据集目录和 ZIP。

数据文件默认不提交到 Git，只保留目录结构。导入成功不会修改或删除原始数据包。
