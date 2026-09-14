# NCS 结果库与后端

当前统一业务、架构和代码规划见 `docs/项目业务架构与代码规划.md`。现有代码已完成 ADS v2.1 到 Windows MySQL 8.0.46 的历史联调；最新 ADS Spark v2.3 已核验但尚未适配，当前虚拟机 MySQL 5.7.35 也尚未完成项目建库和权限验收。

查询仓储通过 `inspect_view_contracts` / `assert_view_contracts` 检查白名单 `api_v1_*` 视图合同。9 个当前必需视图已通过真实 MySQL 验证；预测视图属于可选上游能力，不作为当前健康检查的阻断项。

当前范围只包含处理后数据的结果库、数据管理后端和大屏查询后端。机器学习训练、推理、模型管理及特征处理不在当前范围；上游若提供预测结果，本项目按普通处理后数据集导入和发布。范围决策见 `docs/当前范围决策.md`，历史 ML 原型仅保存在 `archive/ml-control-plane-prototype`。

最终实训环境采用 Python 3.11 或 3.12；上游使用 Hadoop 3.x 与 Spark SQL/PySpark 产生 ADS，MySQL 运行在虚拟机内。数据管理程序支持 Windows 远程导入和虚拟机就地处理两种部署模式，Windows Flask 通过虚拟机 IP 查询。设计见 `docs/双运行位置数据接入设计.md`。前端单独使用 Node.js 23+、Vue 3 和 DataV。

向前端交接项目时不要直接压缩工作目录。数据库密码放在被忽略的 `.local/ncs.env`，前端只使用查询 API 和可选开发 API Key；快速说明见 `docs/前端联调交接说明.md`，从下载仓库开始的完整步骤见 `docs/仓库下载与联调操作手册.md`。

前端 `ncs-dashboard.zip` 只作为只读联调依据，不纳入或修改其源码。实际请求与联调门禁见 `docs/前端代码包只读评审.md`。

## 环境准备与前置工作（新成员必读）

> 按项目纪律，所有环境要求和前置工作以本章为准并保持更新；细节设计可再读 `docs/`，但接入步骤以本章为唯一入口。

### 1. 前置软件

| 软件 | 版本要求 | 用途 |
| --- | --- | --- |
| Python | 3.11 或 3.12（验收固定） | 后端全部服务与脚本 |
| Git | 任意较新版本 | 拉取仓库；推送需已配置的 SSH 密钥或账号凭据 |
| MySQL | 5.7 或 8.0 | 真实结果库（可选，本地开发可用 SQLite 免装） |
| Node.js | 23 及以上 | 仅前端 `ncs-dashboard` 需要，后端开发可不装 |
| bash + flock + cron | 常见 Linux 工具 | 仅虚拟机 Shell 自动同步需要（`scripts/shell/`，当前分支） |

### 2. 创建环境并安装依赖

PowerShell（Windows 实训环境）：

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,mysql]"
```

bash（Linux/虚拟机）：

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,mysql]"
```

依赖组说明：

- 默认仅依赖 `Flask`，足以运行全部单元测试（SQLite 路径）。
- `mysql` 组提供 `PyMySQL`，连接真实 MySQL（含集成测试和 Shell 同步）时必须安装。
- `dev` 组提供 `pytest`。
- 预测功能（`src/ncs_backend/prediction/`）运行时额外需要 `numpy` 和 `torch`，未声明为包依赖，按需手动 `pip install numpy torch`；不装不影响结果库与查询功能，仅张量构建相关测试会报缺少依赖的明确错误。

### 3. 环境变量与本地配置

仓库不保存真实凭据。本地配置统一放在被 Git 忽略的 `.local/ncs.env`，启动脚本会自动加载；现有进程环境变量优先。模板见 `config/handoff.example`。

关键变量：

| 变量 | 必填场景 | 说明 |
| --- | --- | --- |
| `NCS_DATABASE_URL` | 连接数据库时 | 例如 `sqlite:///.local/ncs.sqlite` 或 `mysql+pymysql://ncs_ads_admin:<密码>@127.0.0.1:3306/ncs_analytics` |
| `NCS_QUERY_HOST` / `NCS_QUERY_PORT` | 跨机器联调时 | 默认 `127.0.0.1:5000`，管理/控制台默认只绑本机 |
| `NCS_QUERY_API_KEY` | 前端跨机访问时 | 只读查询接口的开发 API Key |
| `NCS_CORS_ORIGINS` | 浏览器联调时 | 允许的前端 Origin 白名单，逗号分隔 |
| `NCS_MYSQL_MIGRATOR_URL` / `NCS_MYSQL_ADMIN_URL` / `NCS_MYSQL_READER_URL` / `NCS_MYSQL_PRIVILEGED_URL` | 真实 MySQL 迁移与验收时 | 三账号权限体系，root/特权账号仅迁移授权时使用 |
| `NCS_ADS_EXCHANGE_ROOT` / `NCS_ADS_SYNC_INTERVAL_SECONDS` 等 | Shell 自动同步（当前分支） | 见 `scripts/shell/ncs_ads_sync.env.example` 与 `docs/ADS_v2.5自动同步与模型推理设计.md` |

### 4. 首次本地初始化与自检

初始化完整本地开发库（控制表、staging、迁移记录，可重复执行）：

```powershell
python scripts/init_local_database.py --sqlite .local/ncs.sqlite
python scripts/admin_cli.py check-local-database --sqlite .local/ncs.sqlite
```

运行全部测试确认环境就绪（预期 `N passed, 2 skipped`；跳过项是需要真实 MySQL 与 ADS 包路径的集成测试）：

```powershell
python -m pytest
```

### 5. 服务启动速查

三个服务的统一入口（会先幂等初始化开发库），默认端口 `admin=5001`、`query=5000`、`console=5002`：

```powershell
python scripts/run_local.py admin    # 或 query / console
```

等价的单独入口：`scripts/run_query.py`、`scripts/run_admin.py`、`scripts/run_db_console.py`。Windows 联调可双击 `start_project.cmd` 同时启动后端与相邻目录的 Vue 前端。

### 6. 接入真实 MySQL（可选）

按 `docs/仓库下载与联调操作手册.md` 第 8～10 节操作；命令入口：

```powershell
python scripts/setup_mysql_ads.py --initialize --grant-reader --verify   # 迁移+授权+自检
python scripts/verify_mysql_e2e.py                                        # 完整端到端验收
```

## 本地验证

```powershell
python -m pytest
```

启动查询服务：

```powershell
python scripts/run_query.py
```

Windows 联调环境也可以双击仓库根目录的 `start_project.cmd`，一次启动查询后端和位于相邻目录 `../ncs-dashboard/ncs-dashboard` 的 Vue 前端，并自动打开 `http://localhost:5173/`。该脚本按当前学生实训环境固定连接虚拟机 MySQL；如果目录或虚拟机地址变化，需要先修改脚本顶部配置。

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

统一初始化会创建控制表、staging 表和迁移记录，支持重复执行。生成的 `.local/ncs.sqlite` 已被 Git 忽略，只用于本地开发；真实 MySQL 迁移和 ADS v2.1 导入已经验收，连接凭据仍必须通过环境变量配置且不得进入 Git。

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

ADS v2.1 已提供同步管理入口 `POST /internal/v1/ads-v21/imports`。它接收服务器本地解压目录并选择 `A0`/`B` 波次；迁移和建表必须提前由迁移账号执行，管理接口只使用 DML 权限。

MySQL 迁移、固定视图授权和三账号权限自检使用：

```powershell
python scripts/setup_mysql_ads.py --initialize --grant-reader --verify
```

连接地址分别通过 `NCS_MYSQL_MIGRATOR_URL`、`NCS_MYSQL_PRIVILEGED_URL`、`NCS_MYSQL_ADMIN_URL`、`NCS_MYSQL_READER_URL` 提供。命令不会输出连接串；特权连接只在授予固定视图权限时需要。

配置迁移、管理、查询三账号 URL 和 ADS 包目录后，可运行完整验收：

```powershell
python scripts/verify_mysql_e2e.py
```

该命令会执行幂等迁移、两次 ADS 导入、权限检查、必需视图合同、12 个查询请求和无残留事务回滚探针，仅用于测试/联调数据库。

代码边界和后续阶段见：

- `docs/代码实现规划.md`
- `docs/实现路线与对接清单.md`
- `docs/api-contract.md`
- `docs/大屏接口冻结合同_v1.md`
- `docs/前端接口协议.md`
- `docs/前端启动元数据接口简表.md`
- `docs/data-contract.md`
- `docs/当前范围决策.md`
- `docs/项目当前状态与下一步.md`
- `docs/项目业务架构与代码规划.md`
- `docs/ADS_Spark_v2.3交接包评审.md`
- `docs/ADS_v2.5自动同步与模型推理设计.md`
