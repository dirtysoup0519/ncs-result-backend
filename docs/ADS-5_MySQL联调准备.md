# ADS-5 MySQL 联调准备

## 当前状态

本仓库已完成 MySQL DB-API 方言、连接工厂、结果库迁移入口和视图合同检查脚本。当前开发环境没有 PyMySQL 和可用 MySQL 地址，因此尚未声称真实 MySQL 验收通过。

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

不带 `--initialize` 时只检查服务器元信息和 `api_v1_*` 视图合同；带 `--initialize` 才会执行控制表、结果表和视图迁移。脚本不会执行上游联调包中的 `TRUNCATE` 或 `LOAD DATA` SQL。

## 权限边界

| 账号 | 允许 | 禁止 |
| --- | --- | --- |
| `ncs_ads_migrator` | 迁移表、控制表、结果表、视图的 DDL | 业务查询账号使用该身份 |
| `ncs_ads_admin` | 控制表、staging、结果表的导入、质量和发布 | 任意库管理、用户管理 |
| `ncs_ads_reader` | 仅 `api_v1_*` 视图的 `SELECT` | 物理结果表、控制表、staging、写入和 DDL |

查询后端只使用 `ncs_ads_reader`。权限验证必须在 MySQL 实例中分别用三个账号执行，不能仅凭应用配置推断。

## 验收记录模板

- MySQL 版本：待填写
- 字符集/排序规则：待填写
- `@@time_zone` / 应用时区：待填写
- `@@sql_mode`：待填写
- 迁移重复执行：待填写
- ADS A0/Wave B 导入与回滚：待填写
- 查询账号视图合同：待填写
- 查询账号访问物理表/控制表：应失败
