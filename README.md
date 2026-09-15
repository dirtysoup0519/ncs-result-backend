# NCS 结果库与后端

## 1. 项目简介

本仓库负责新能源汽车充电桩项目的下游服务：接收上游 Spark/Hive 生成的 ADS v2.5 数据包，校验并发布到 MySQL 结果库，通过 Flask 为 Vue 3/DataV 大屏提供查询接口，并可使用外部交付的模型结构与权重生成预测结果。

本仓库负责：

- ADS 交接包校验、幂等导入、质量检查、发布和回滚；
- MySQL 结果表、控制表和稳定的 `api_v1_*` 查询视图；
- 面向前端的 Flask 查询 API；
- 数据库简易管理窗口；
- 使用已经训练好的模型和权重完成推理及预测发布；
- Windows 手工导入与虚拟机 Shell 自动同步两个入口。

本仓库不负责：

- ODS、DWD、DWS、ADS 的生产计算；
- 模型训练、调参和评估；
- 修改前端源码；
- Hadoop、Hive 和 Spark 集群运维。

当前技术基线：

| 组件 | 要求 |
| --- | --- |
| Hadoop | 3.x，由上游负责 |
| ADS | Spark v2.5，18 个数据集 |
| MySQL | 5.7.x 或 8.0，当前验证版本为 5.7.35 |
| Python | 3.11 或 3.12 |
| 后端 | Flask + PyMySQL |
| 前端 | Vue 3 + DataV，Node.js 23+ |

应用不得使用 MySQL `root`。迁移账号负责结构变更，管理账号负责数据导入，查询账号只允许读取固定的 `api_v1_*` 视图。密码只能保存到 Git 忽略的本地配置中，不能写入仓库文件。

## 2. 项目架构

```text
上游 Spark/Hive ADS
  -> ADS v2.5 ZIP/TAR.GZ + 完成标记
  -> 数据入口
       ├─ Windows 手工导入
       └─ 虚拟机 Shell 自动同步
  -> 统一 Python 校验、幂等、事务和发布逻辑
  -> 虚拟机 MySQL / ncs_analytics
       ├─ ctl_*      控制、批次、质量和发布记录
       ├─ stg_*      导入暂存
       ├─ rpt_*      结果数据
       └─ api_v1_*   面向查询后端的稳定视图
  -> Windows Flask API :5000
  -> Vue 3/DataV 大屏 :5173

外部模型包 + 已发布 load_hourly
  -> 后端模型适配与推理
  -> 预测结果表和 api_v1_load_prediction
  -> 大屏 AI 预测组件
```

两个数据入口只负责发现和提交数据，不允许各写一套业务逻辑。相同 `sourceBatchId + packageChecksum` 重复提交时只能产生一次有效发布。新批次失败时继续保留旧的已发布批次；预测失败不回滚已经成功发布的 ADS 数据。

推荐目录结构如下，仓库内命令均从 `ncs-result-backend` 根目录执行：

```text
workspace/
├── ncs-result-backend/
├── ncs-dashboard/
│   └── ncs-dashboard/
├── ncs-runtime/          # 虚拟机运行环境和私密配置，不进入 Git
└── ncs-ads-exchange/     # 虚拟机 ADS 交换目录，不进入 Git
```

运行位置：

| 部分 | 位置 | 数据库地址 |
| --- | --- | --- |
| MySQL | 虚拟机 | 本机服务 |
| Flask 查询 API | Windows | 虚拟机 IP |
| Windows 手工导入 | Windows | 虚拟机 IP |
| Shell 自动同步 | 虚拟机 | `127.0.0.1` |
| Vue 大屏 | Windows | `http://127.0.0.1:5000` |

## 3. 安装与启动

### 3.1 虚拟机最低条件

假设虚拟机初始状态只有 `hadoop` 用户和 Hadoop 3.x。先确认 `hadoop` 具有 sudo 权限，并记录虚拟机 IP 和 Windows VMware 网卡 IP。

bash（虚拟机）：

```bash
whoami
hostname -I
sudo -v
timedatectl
sudo timedatectl set-timezone Asia/Shanghai
```

PowerShell（Windows）：

```powershell
Get-NetIPAddress -AddressFamily IPv4
Test-Connection <VM-IP> -Count 2
```

后续示例使用：

```text
虚拟机：192.168.176.100
Windows VMware 网卡：192.168.176.1
MySQL：3306
```

实际地址不同时必须替换，不能直接照抄。

### 3.2 安装虚拟机基础工具

bash（虚拟机）：

```bash
sudo yum install -y git curl wget unzip tar util-linux cronie
sudo systemctl enable --now crond
git --version
flock --version
crontab -l
```

`util-linux` 提供 `flock`，`cronie` 提供 `cron/crontab`。只使用 Windows 手工导入时可以暂不配置 cron，但 MySQL 必须安装。

### 3.3 安装和配置 MySQL

为保持实训环境一致，优先使用与原虚拟机相同的 MySQL 5.7 RPM 包。将安装包放在当前用户目录下的 `./mysql57-rpms/`，然后执行：

```bash
cd ./mysql57-rpms
sudo yum localinstall -y ./*.rpm
```

如果已经配置可用的 MySQL 5.7 Community 仓库，可以执行：

```bash
sudo yum install -y mysql-community-server
```

不要同时混装 MariaDB 和 MySQL Community Server。确认安装结果：

```bash
rpm -qa | grep -Ei 'mysql|mariadb'
which mysqld
mysqld --version
```

使用下面的命令查找系统实际读取的 MySQL 配置文件：

```bash
mysqld --verbose --help 2>/dev/null | sed -n '/Default options are read from/,+1p'
```

在该系统配置文件的 `[mysqld]` 段设置：

```ini
[mysqld]
port=3306
bind-address=0.0.0.0
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
default-time-zone='+08:00'
```

配置中不得存在：

```ini
skip-grant-tables
skip-networking
```

检查有效启动参数：

```bash
my_print_defaults mysqld | grep -Ei 'skip-grant|skip-networking|bind-address|port'
sudo systemctl enable mysqld
sudo systemctl restart mysqld
sudo systemctl status mysqld --no-pager
sudo ss -lntp | grep ':3306'
```

如果修改过 systemd 服务覆盖配置，重启前先运行：

```bash
sudo systemctl daemon-reload
```

### 3.4 设置 MySQL root 并退出恢复模式

全新 MySQL 5.7 通常会在日志中生成临时 root 密码。找到临时密码并登录：

```bash
sudo grep 'temporary password' /var/log/mysqld.log | tail -n 1
mysql -uroot -p
```

以下命令只能在 `mysql>` 提示符中执行：

```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY '<strong-root-password>';
FLUSH PRIVILEGES;
SHOW VARIABLES LIKE 'skip_grant_tables';
```

`skip_grant_tables` 必须为 `OFF`。如果为 `ON`，退出 MySQL，删除系统 MySQL 配置中的 `skip-grant-tables`，然后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart mysqld
mysql -uroot -p -e "SHOW VARIABLES LIKE 'skip_grant_tables';"
```

`--skip-grant-tables` 只用于密码恢复。在该模式下 MySQL 会拒绝 `CREATE USER`、`ALTER USER` 和 `GRANT`，项目初始化脚本无法运行。

### 3.5 配置虚拟机防火墙

只向 Windows VMware 网卡放行 3306，不要向公共网络开放。

bash（虚拟机）：

```bash
sudo systemctl is-active firewalld
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.176.1/32" port protocol="tcp" port="3306" accept'
sudo firewall-cmd --reload
sudo firewall-cmd --list-rich-rules
```

如果 `firewalld` 未运行，应先确认虚拟机网络隔离方式，不要盲目修改防火墙服务。Windows 验证：

```powershell
Test-NetConnection 192.168.176.100 -Port 3306
```

只有 `TcpTestSucceeded : True` 才继续。

### 3.6 临时允许 Windows 完成首次初始化

当前 Windows 初始化脚本需要一次 root 连接来建库、建账号和授权。不要创建 `root@'%'`，只临时允许 Windows VMware 地址。

在虚拟机执行 `mysql -uroot -p`，然后在 `mysql>` 中执行：

```sql
CREATE USER IF NOT EXISTS 'root'@'192.168.176.1'
  IDENTIFIED BY '<strong-root-password>';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'192.168.176.1' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SELECT User, Host FROM mysql.user WHERE User = 'root';
```

### 3.7 准备 Windows 开发环境

Windows 必须安装：

- Python 3.11 或 3.12；
- Git；
- Node.js 23+，仅启动前端时需要。

将后端和前端放到“项目架构”所示的相邻目录。进入后端仓库根目录后检查：

```powershell
python --version
git branch --show-current
Test-Path .\scripts\setup_new_machine.ps1
Test-Path ..\ncs-dashboard\ncs-dashboard\package.json
```

如果前端目录不同，调整为推荐目录；不要修改前端源码来适配本机路径。

### 3.8 一键建库、建账号和生成本地配置

在后端仓库根目录双击 `./setup_new_machine.cmd`，或在 PowerShell 中运行：

```powershell
.\scripts\setup_new_machine.ps1 `
  -VmHost 192.168.176.100 `
  -MysqlPort 3306
```

脚本依次完成：

1. 检查虚拟机 MySQL 端口；
2. 检查 Python 3.11/3.12；
3. 创建 `./.venv/` 并安装项目依赖；
4. 在窗口中隐藏输入 root 和三个应用账号密码；
5. 检查 MySQL 没有运行在 `skip-grant-tables`；
6. 创建 `ncs_analytics`、控制表、结果表、索引和视图；
7. 创建并验证 `ncs_ads_migrator`、`ncs_ads_admin`、`ncs_ads_reader`；
8. 生成 Git 忽略的 `./.local/ncs.env`。

默认 `AccountHost=%` 用于学生隔离网络中的双入口：Windows 和虚拟机均可使用应用账号。部署到非隔离网络时必须按来源分别创建账号，不能使用 `%`。

成功标志：

```text
READY: MySQL schema, accounts and grants are ready.
Local config written to .../.local/ncs.env
```

脚本可重复执行。依赖已经安装时可以跳过重复安装：

```powershell
.\scripts\setup_new_machine.ps1 `
  -VmHost 192.168.176.100 `
  -MysqlPort 3306 `
  -SkipDependencyInstall
```

完成后回到虚拟机，删除临时远程 root，只保留 `root@localhost`：

```sql
DROP USER IF EXISTS 'root'@'192.168.176.1';
FLUSH PRIVILEGES;
```

### 3.9 导入 ADS 数据

初始化只创建数据库结构，不会自动生成业务数据。先将最新 ADS v2.5 包解压到后端仓库相邻目录，例如 `../ads-v25/`。

PowerShell（Windows，在后端仓库根目录）：

```powershell
Get-Content .\.local\ncs.env | ForEach-Object {
  if ($_ -match '^([^#=]+)=(.*)$') {
    Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
  }
}

.\.venv\Scripts\python.exe .\scripts\import_ads_v23.py `
  --package ..\ads-v25 `
  --database-url $env:NCS_MYSQL_ADMIN_URL `
  --skip-initialize
```

脚本名称保留 `v23` 是为了兼容旧调用，当前实现会根据 Manifest 识别并导入 ADS v2.5 的 18 个数据集。

### 3.10 启动后端和前端

PowerShell（Windows，在后端仓库根目录）：

```powershell
Test-Path .\.local\ncs.env
.\start_project.cmd
```

启动脚本会读取 `./.local/ncs.env`，自动寻找 `../ncs-dashboard/ncs-dashboard/`，并启动：

- 查询 API：`http://127.0.0.1:5000`；
- Vue 大屏：`http://localhost:5173`。

数据库简易管理窗口按需单独启动：

```powershell
.\.venv\Scripts\python.exe .\scripts\run_db_console.py
```

访问 `http://127.0.0.1:5002/db-console`。窗口只负责连接检查、日志和受控 SQL，不负责远程启动或停止虚拟机 MySQL。

端口 `5000` 或 `5173` 已被占用时，启动脚本会保留已有进程。修改代码或配置后，应先在对应终端按 `Ctrl+C` 停止旧进程，再重新启动。

### 3.11 运行测试

PowerShell（Windows）：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

需要连接真实 MySQL 的环境测试必须使用虚拟机 MySQL；默认测试中的少量跳过项表示未提供真实 MySQL、ADS 包或预测依赖，不代表单元测试失败。

### 3.12 可选：部署虚拟机 Shell 自动同步

仅使用 Windows 手工导入时可以跳过本节。自动同步要求虚拟机额外具备 Python 3.11/3.12。不要替换 CentOS 自带 Python，否则可能破坏 `yum`；应使用独立 Python 或 Conda 环境。

将后端仓库放在当前用户目录的 `./ncs-result-backend/`，进入仓库后创建相邻运行目录：

```bash
cd ./ncs-result-backend
python3.11 -m venv ../ncs-runtime/venv
../ncs-runtime/venv/bin/pip install -e '.[mysql]'
mkdir -p ../ncs-ads-exchange/{ready,processing,archive,rejected,logs,locks}
cp ./scripts/shell/ncs_ads_sync.env.example ../ncs-runtime/ads-sync.env
chmod 600 ../ncs-runtime/ads-sync.env
chmod +x ./scripts/shell/*.sh
```

如果系统没有 `python3.11`，先通过独立 Conda 环境或离线 Python 3.11/3.12 安装包提供该命令，再继续。不要用 Python 3.10 作为最终验收环境。

编辑 `../ncs-runtime/ads-sync.env`：

```bash
export NCS_REPO=.
export NCS_DATABASE_URL='mysql+pymysql://ncs_ads_admin:<admin-password>@127.0.0.1:3306/ncs_analytics'
export NCS_ADS_EXCHANGE_ROOT=../ncs-ads-exchange
export NCS_ADS_SYNC_INTERVAL_SECONDS=30
export PATH=../ncs-runtime/venv/bin:/usr/local/bin:/usr/bin:/bin
```

暂不需要预测时不要设置 `NCS_MODEL_PACKAGE`。

先手工执行一次：

```bash
source ../ncs-runtime/ads-sync.env
./scripts/shell/sync_ads_once.sh
echo $?
```

没有新包时退出码应为 `0`。投递真实包时，必须先完整复制数据包，再创建同名完成标记：

```bash
cp ../incoming/package.zip ../ncs-ads-exchange/ready/package.zip
touch ../ncs-ads-exchange/ready/package.zip.ready
./scripts/shell/sync_ads_once.sh
tail -n 100 ../ncs-ads-exchange/logs/sync_ads.log
```

成功后数据包和标记进入 `../ncs-ads-exchange/archive/`；失败时进入 `../ncs-ads-exchange/rejected/`，详细错误写入 `../ncs-ads-exchange/logs/`。

前台验证轮询：

```bash
source ../ncs-runtime/ads-sync.env
./scripts/shell/watch_ads.sh
```

确认正常后按 `Ctrl+C` 停止，再在 `hadoop` 用户的 `crontab -e` 中加入：

```cron
@reboot cd ./ncs-result-backend && /bin/bash -lc 'source ../ncs-runtime/ads-sync.env; exec ./scripts/shell/watch_ads.sh >> ../ncs-ads-exchange/logs/watch.log 2>&1'
```

立即启动一次：

```bash
cd ./ncs-result-backend
nohup /bin/bash -lc 'source ../ncs-runtime/ads-sync.env; exec ./scripts/shell/watch_ads.sh' \
  >> ../ncs-ads-exchange/logs/watch.log 2>&1 &
```

检查：

```bash
ps -ef | grep '[w]atch_ads.sh'
crontab -l
tail -f ../ncs-ads-exchange/logs/sync_ads.log
```

不要同时运行多个 watcher，也不要同时配置每分钟 cron；脚本内部已经每 30 秒轮询并使用 `flock` 防止并发。

### 3.13 常见错误

`The MySQL server is running with --skip-grant-tables`：MySQL 仍处于密码恢复模式。删除有效配置中的 `skip-grant-tables`，重启 `mysqld`，确认 `skip_grant_tables=OFF` 后重新运行初始化。

`Missing ./.local/ncs.env`：建库初始化尚未成功，先运行 `./setup_new_machine.cmd`，不要手工把密码写入 Git 文件。

`Access denied for user`：进入 MySQL 后执行 `SELECT USER(), CURRENT_USER();`，检查实际匹配的账号主机。`user@localhost`、`user@node100` 和 `user@192.168.176.1` 是不同账号。

Windows 显示 `TcpTestSucceeded : False`：检查虚拟机 IP、MySQL 服务、`bind-address`、3306 监听和防火墙来源地址。

把 `mysql -h ...` 或 `systemctl` 输入到 `mysql>`：先执行 `exit` 回到 bash/PowerShell。`SELECT`、`CREATE USER`、`GRANT` 才是在 `mysql>` 中运行的 SQL。
