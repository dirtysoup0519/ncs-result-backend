# ADS-5 MySQL 联调准备

> **历史留档，不可照做（2026-09-15）**：本文记录 Windows MySQL 8.0.46 和三账号权限实验。当前唯一可执行基线是根目录 `README.md` 的虚拟机 MySQL 5.7.35、`skip-grant-tables`、无密码 root 单连接流程；本文命令不会用于当前环境。

> 已废止：本文中的三账号、授权和权限隔离命令只记录历史试验，不适用于当前环境。当前安装和验收必须按根目录 `README.md` 的“恢复模式 + 无密码 root 单连接”流程执行。

> 历史环境说明：本文记录的是 Windows MySQL 8.0.46 验收，不代表当前虚拟机 MySQL 5.7.35 已通过。当前环境与后续步骤见 `项目业务架构与代码规划.md`。

> 历史记录快照：曾在虚拟机/本机环境记录迁移、视图和三账号实验；这些结论不代表当前权限模型或数据版本。当前 v3.2 交付状态见 `项目当前状态与下一步.md`。

> 状态：首轮验收已完成；本文现作为复现步骤和验收记录使用

## 当前状态

2026-09-14 已在本机 MySQL 8.0.46 完成真实联调：控制表和结果表迁移、ADS v2.1 A0/Wave B 导入、重复导入、事务回滚、只读视图、查询 API 和权限隔离均通过。凭据不写入仓库，仍只通过进程环境变量传递。

## 联调前置条件

- MySQL 8.0 及以上版本，确认结果库不是与 Hive 元数据共用的实例；
- 提供测试库 URL、字符集、时区和 SQL mode；
- 安装可选依赖 `PyMySQL`。

## 验证命令

```powershell
$env:NCS_MYSQL_TEST_URL = "mysql+pymysql://<user>:<password>@<host>:3306/<database>"
python scripts/verify_mysql_ads.py --initialize
pytest -q tests/integration/test_mysql_ads.py
```

不带 `--initialize` 时只检查服务器元信息和 `api_v1_*` 视图合同；带 `--initialize` 才会执行控制表、结果表和视图迁移。脚本不会执行上游联调包中的 `TRUNCATE` 或 `LOAD DATA` SQL。

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
