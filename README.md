# NCS 结果库与后端

当前分支已完成工程骨架、Manifest/Schema/质量规则/状态机基础，以及按 V1 冻结合同搭建的查询 API 路由和空数据适配器。真实 MySQL 视图适配仍待上游字段确认。

查询仓储同时提供 `inspect_view_contracts` / `assert_view_contracts`，只检查白名单 `api_v1_*` 视图的列结构，不读取业务数据；真实结果表和 ADS 字段确认后再接入迁移与运行检查。

当前范围只包含处理后数据的结果库、数据管理后端和大屏查询后端。机器学习训练、推理、模型管理及特征处理不在当前范围；上游若提供预测结果，本项目按普通处理后数据集导入和发布。范围决策见 `docs/当前范围决策.md`，历史 ML 原型仅保存在 `archive/ml-control-plane-prototype`。

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

初始化本地 staging 表：

```powershell
python scripts/admin_cli.py init-staging-schema --sqlite .local/control.sqlite
```

推荐使用统一命令创建完整的本地开发库：

```powershell
python scripts/init_local_database.py --sqlite .local/ncs.sqlite
python scripts/admin_cli.py check-local-database --sqlite .local/ncs.sqlite
```

统一初始化会创建控制表、staging 表和迁移记录，支持重复执行。生成的 `.local/ncs.sqlite` 已被 Git 忽略，只用于本地开发，不是正式结果库；真实 MySQL 迁移和生产凭据接入仍需单独配置。

数据库窗口连接该开发库时，在当前终端设置连接地址后启动：

```powershell
$env:NCS_DATABASE_URL = "sqlite:///.local/ncs.sqlite"
python scripts/run_db_console.py
```

打开 `http://127.0.0.1:5002/db-console`。默认 `unmanaged` 模式只检查连接，不提供数据库进程启停。

也可以用统一的本地入口启动任一服务；该入口会先幂等初始化开发库：

```powershell
python scripts/run_local.py admin
python scripts/run_local.py query
python scripts/run_local.py console
```

默认端口依次为 `5001`、`5000`、`5002`。三个服务需要分别占用一个终端。没有 ADS 业务视图时，查询服务会把相应能力标记为不可用；这属于预期降级，不会创建或猜测业务数据。

控制面当前已提供批次生命周期、质量校验、发布和显式回滚用例的本地 DB-API 适配：批次按
`CREATED -> LOADING -> VALIDATING -> READY -> PUBLISHED` 受状态机约束，重复提交同一
上游批次（含 Manifest 校验和）、规则结果和 Schema 版本幂等；本地 JSON/CSV/TSV 交付先经过 Manifest、Schema、校验和质量检查，再创建导入批次，并可写入只保存原始 JSON 行的 staging 表。质量结果中的 `BLOCKER/ERROR` 会阻断进入 `READY`，发布和回滚会在事务中切换活动发布记录并写入审计日志。实现位于
`src/ncs_backend/admin/importers.py`、`src/ncs_backend/admin/staging.py`、`src/ncs_backend/admin/repositories.py` 和 `src/ncs_backend/admin/services.py`；正式 JDBC/Sqoop 导入通道和具体质量规则编排将在后续迭代接入。

管理服务已提供受控的 `/internal/v1` 路由骨架：数据集登记/列表、Schema 列表、批次创建/查询/筛选、质量完成与筛选查询、发布历史/详情、当前活动发布、发布和按目标批次回滚。路由必须注入对应应用服务后才会执行写操作，未配置依赖时返回 `DEPENDENCY_NOT_READY`。

代码边界和后续阶段见：

- `docs/代码实现规划.md`
- `docs/实现路线与对接清单.md`
- `docs/api-contract.md`
- `docs/大屏接口冻结合同_v1.md`
- `docs/前端接口协议.md`
- `docs/前端启动元数据接口简表.md`
- `docs/data-contract.md`
- `docs/当前范围决策.md`
