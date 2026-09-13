# NCS 结果库与后端

当前分支已完成工程骨架、Manifest/Schema/质量规则/状态机基础，以及按 V1 冻结合同搭建的查询 API 路由和空数据适配器。真实 MySQL 视图适配仍待上游字段确认。

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

当前合同样例位于 `contracts/examples/`。这些样例用于验证内部协议，不代表上游真实字段已经确认。

校验一份 Schema、Manifest 和 JSON 样例：

```powershell
python scripts/admin_cli.py validate-delivery `
  --schema contracts/examples/station-hourly.schema.v1.json `
  --manifest contracts/examples/station-hourly.manifest.v1.json `
  --data contracts/examples/station-hourly.rows.v1.json
```

初始化本地控制面 SQLite：

```powershell
python scripts/admin_cli.py init-control-schema --sqlite .local/control.sqlite
```

该命令只创建控制表，支持重复执行；真实 MySQL 迁移和生产凭据接入仍需单独配置。

控制面当前已提供批次生命周期和发布用例的本地 DB-API 适配：批次按
`CREATED -> LOADING -> VALIDATING -> READY -> PUBLISHED` 受状态机约束，重复提交同一
上游批次幂等，发布会在事务中切换活动发布记录并写入审计日志。实现位于
`src/ncs_backend/admin/repositories.py` 和 `src/ncs_backend/admin/services.py`；导入器、质量规则持久化和回滚接口将在后续迭代接入。

代码边界和后续阶段见：

- `docs/代码实现规划.md`
- `docs/实现路线与对接清单.md`
- `docs/api-contract.md`
- `docs/大屏接口冻结合同_v1.md`
- `docs/前端接口协议.md`
- `docs/前端启动元数据接口简表.md`
- `docs/data-contract.md`
