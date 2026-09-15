# ADS-5 MySQL 联调准备

> 已废止：本文中的三账号、授权和权限隔离命令只记录历史试验，不适用于当前环境。当前安装和验收必须按根目录 `README.md` 的“恢复模式 + 无密码 root 单连接”流程执行。

> 历史环境说明：本文记录的是 Windows MySQL 8.0.46 验收，不代表当前虚拟机 MySQL 5.7.35 已通过。当前环境与后续步骤见 `项目业务架构与代码规划.md`。

> 最新进度：虚拟机 MySQL 5.7.35 已完成基础迁移、9 个查询视图授权和三账号权限复核；当前尚未导入 ADS v2.3 业务数据。

> 状态：首轮验收已完成；本文现作为复现步骤和验收记录使用

## 当前状态

2026-09-14 已在本机 MySQL 8.0.46 完成真实联调：控制表和结果表迁移、ADS v2.1 A0/Wave B 导入、重复导入、事务回滚、只读视图、查询 API 和权限隔离均通过。凭据不写入仓库，仍只通过进程环境变量传递。

## 联调前置条件

- MySQL 8.0 及以上版本，确认结果库不是与 Hive 元数据共用的实例；
- 提供测试库 URL、字符集、时区和 SQL mode；
- 安装可选依赖 `PyMySQL`；
- 准备迁移/管理账号和查询只读账号，凭据只通过环境变量或受保护的 CI Secret 传递。

## 验证命令

```powershell
$env:NCS_MYSQL_TEST_URL = "mysql+pymysql://<user>:<password>@<host>:3306/<database>"
python scripts/verify_mysql_ads.py --initialize
pytest -q tests/integration/test_mysql_ads.py
```

统一初始化、授权和三账号自检：

```powershell
$env:NCS_MYSQL_MIGRATOR_URL = "mysql+pymysql://<migrator>:<password>@<host>:3306/<database>"
$env:NCS_MYSQL_PRIVILEGED_URL = "mysql+pymysql://<privileged>:<password>@<host>:3306/<database>"
$env:NCS_MYSQL_ADMIN_URL = "mysql+pymysql://<admin>:<password>@<host>:3306/<database>"
$env:NCS_MYSQL_READER_URL = "mysql+pymysql://<reader>:<password>@<host>:3306/<database>"
python scripts/setup_mysql_ads.py --initialize --grant-reader --verify
```

`--grant-reader` 仅向固定 `api_v1_*` 视图授予 `SELECT`，不创建账号、不修改密码。`--verify` 检查迁移账号具备 DDL、管理账号仅具备 DML、查询账号能读取全部必需视图且不能读取物理结果表和控制表。

完整端到端验收入口：

```powershell
$env:NCS_ADS_V21_PACKAGE = "<extracted-package-directory>"
python scripts/verify_mysql_e2e.py
```

复用上述迁移、管理、查询账号环境变量。脚本要求三个 URL 指向同一数据库，并执行两次幂等导入、必需视图合同、12 个非模型查询请求和事务回滚探针。回滚探针使用唯一临时批次，预期不留下控制记录或结果行；只应对测试/联调数据库运行。

不带 `--initialize` 时只检查服务器元信息和 `api_v1_*` 视图合同；带 `--initialize` 才会执行控制表、结果表和视图迁移。脚本不会执行上游联调包中的 `TRUNCATE` 或 `LOAD DATA` SQL。

## 权限边界

| 账号 | 允许 | 禁止 |
| --- | --- | --- |
| `ncs_ads_migrator` | 迁移表、控制表、结果表、视图的 DDL | 业务查询账号使用该身份 |
| `ncs_ads_admin` | 控制表、staging、结果表的导入、质量和发布 | 任意库管理、用户管理 |
| `ncs_ads_reader` | 仅 `api_v1_*` 视图的 `SELECT` | 物理结果表、控制表、staging、写入和 DDL |

查询后端只使用 `ncs_ads_reader`。权限验证必须在 MySQL 实例中分别用三个账号执行，不能仅凭应用配置推断。

## 验收记录模板

- MySQL 版本：8.0.46
- 数据库字符集：`utf8mb4`
- `@@time_zone` / 应用时区：`SYSTEM` / `Asia/Shanghai`；部署到其他机器前应显式确认系统时区
- `@@sql_mode`：`ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION`
- 迁移重复执行：通过；相同迁移版本和校验和不会重复执行 DDL
- ADS A0/Wave B 导入：9 个逻辑数据集首次导入及重复导入均通过
- 失败回滚：在第二个数据集写入后注入异常，新增批次记录为 0，旧总览发布仍为 7 行
- 查询账号视图合同：9 个必需视图通过；模型预测视图属于可选上游能力，不作为当前结果库健康条件
- 查询账号权限：9 个 `api_v1_*` 视图可读；读取 `rpt_dashboard_overview` 和 `ctl_import_batch` 均返回 MySQL 1142
- 后端冒烟：元数据、manifest、总览、时长、热力图、排行、趋势和过程摘要等 10 个请求均返回 200
- 执行计划：迁移账号可执行 `EXPLAIN`；只读账号因无底层表权限不能执行，这是预期的最小权限结果
