# NCS 结果库与后端

当前分支正在实现 `Iteration 1`：工程骨架、公共合同模型、Flask 应用工厂、机器学习 CLI 和基础测试。

## 本地验证

```powershell
python -m pytest
```

启动查询服务：

```powershell
python scripts/run_query.py
```

启动内部管理服务：

```powershell
python scripts/run_admin.py
```

数据库未配置时，`/health/live` 应返回存活，`/health/ready` 会明确返回未就绪；这不是数据库连接验证。

代码边界和后续阶段见：

- `docs/代码实现规划.md`
- `docs/实现路线与对接清单.md`
- `docs/api-contract.md`
- `docs/data-contract.md`
