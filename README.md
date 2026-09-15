# NCS 结果库与后端

新机器建议优先直接执行第 3.7 节的一键初始化与启动；如果出现 Python、网络、MySQL 或依赖环境错误，再返回执行前面的环境检查步骤。

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

文档入口：新接手人员先阅读本 README，再按 `docs/文档现行基线.md` 的顺序阅读当前架构、状态、数据合同和联调说明。`docs/` 中带有“历史留档/不可执行”标记的文件只用于追溯，不要照抄其中的旧版本、三账号或数据库授权命令。

当前技术基线：

| 组件 | 要求 |
| --- | --- |
| Hadoop | 3.x，由上游负责 |
| ADS | Spark v2.5，18 个数据集 |
| MySQL | 5.7.35，实训恢复模式 |
| Python | 3.11 或 3.12 |
| 后端 | Flask + PyMySQL |
| 前端 | Vue 3 + DataV，Node.js 23+ |

当前答辩环境固定使用 `skip-grant-tables` 恢复模式和单一 root 连接，不创建项目数据库账号，也不执行数据库权限隔离检查。`api_v1_*` 视图继续用于隔离物理表结构和稳定前端合同。该模式没有数据库身份认证能力，只允许在隔离的 VMware 实训网络中使用。

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

当前代码的真实调用架构如下：

```text
Windows 启动入口
├─ start_project.cmd
│  └─ scripts/start_project.ps1
│     ├─ 创建或复用 .venv（Python 3.11/3.12）
│     ├─ 读取 .local/ncs.env
│     ├─ 启动 scripts/run_query.py
│     └─ 启动 Vue npm run dev
└─ scripts/setup_new_machine.ps1（首次初始化）
   ├─ bootstrap_mysql_recovery.py       检查 VM MySQL 恢复模式并建库
   ├─ setup_mysql_ads.py                执行迁移和视图初始化
   └─ verify_mysql_ads.py               验证 MySQL 结构合同

数据导入链路
├─ Windows：scripts/import_ads_v23.py
└─ 虚拟机：scripts/shell/sync_ads_once.sh
   └─ ncs_backend.admin.adapters.ads_v23_import
      ├─ Manifest/文件哈希/Schema/主键校验
      ├─ stg_* 暂存与 ctl_* 批次记录
      ├─ rpt_* 结果表导入
      └─ 发布 api_v1_* 视图可见批次

查询链路
scripts/run_query.py
└─ ncs_backend.bootstrap
   └─ ncs_backend.query.app（Flask）
      ├─ DashboardQueryService
      ├─ DashboardQueryRepository（只读 api_v1_*）
      └─ 前端 /api/v1/* DTO

预测链路（可选）
run_load_prediction.py
└─ 模型适配器读取外部模型包和已发布数据
   └─ 预测结果表 / api_v1_load_prediction
```

数据库当前固定在虚拟机 MySQL 5.7.35；Windows 后端通过虚拟机 IP 访问，虚拟机 Shell 通过 `127.0.0.1` 访问。两者统一使用恢复模式下的无密码 root 连接，项目不创建三个应用账号，也不把 MySQL 密码放入仓库。

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
| Vue 大屏 | Windows | `http://127.0.0.1:5173` |

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
虚拟机：<vm-ip>（以当前机器的 VMware 网段为准）
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

配置中必须存在：

```ini
skip-grant-tables
```

为了允许 Windows 查询后端访问，配置中不得存在 `skip-networking`。

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

### 3.4 启用并验证恢复模式

重启 MySQL 后直接无密码登录：

```bash
mysql -uroot
```

在 `mysql>` 中执行：

```sql
SHOW VARIABLES LIKE 'skip_grant_tables';
```

结果必须为 `ON`。不要执行 `ALTER USER`、`CREATE USER`、`GRANT` 或 `FLUSH PRIVILEGES`；项目不依赖 MySQL 账号权限，数据库、表和视图由无密码 root 连接创建。

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
Test-NetConnection <vm-ip> -Port 3306
```

只有 `TcpTestSucceeded : True` 才继续。

### 3.6 准备 Windows 开发环境

Windows 必须安装：

- Python 3.11 或 3.12；
- Git；
- Node.js 23+，仅启动前端时需要。

不需要手工安装 Flask 或 PyMySQL。`./setup_new_machine.cmd` 和 `./start_project.cmd` 会自动创建 `./.venv/` 并安装后端依赖。不要使用全局 `python ./scripts/run_query.py` 启动项目。

将后端和前端放到“项目架构”所示的相邻目录。进入后端仓库根目录后检查：

```powershell
python --version
git branch --show-current
Test-Path .\scripts\setup_new_machine.ps1
Test-Path ..\ncs-dashboard\ncs-dashboard\package.json
```

前端目录只要位于后端仓库的相邻目录，启动脚本会自动寻找。推荐使用以下任一结构：

```text
项目根目录/
├── ncs-result-backend/
└── ncs-dashboard/
    └── ncs-dashboard/
        └── package.json
```

或：

```text
项目根目录/
├── ncs-result-backend/
└── ncs-dashboard/
    └── package.json
```

如果你的前端目录不在上述位置，不要修改前端源码，也不要把前端文件复制到后端仓库。进入后端仓库根目录后，直接通过 `-FrontendDir` 指定“包含 `package.json` 的前端项目目录”：

```powershell
.\start_project.cmd -FrontendDir "D:\你的项目根目录\前端项目目录"
```

例如前端实际位于 `D:\SHIJIAN\SPARK\dashboard\`，且该目录下有 `package.json`，应执行：

```powershell
.\start_project.cmd -FrontendDir "D:\SHIJIAN\SPARK\dashboard"
```

首次运行时脚本会自动执行 `npm install`，并将该路径保存到 Git 忽略的 `./.local/ncs.env`；以后直接运行 `.\start_project.cmd` 即可。如果只执行数据库初始化，也可以传入同一个参数：

```powershell
.\scripts\setup_new_machine.ps1 -VmHost <vm-ip> -FrontendDir "D:\SHIJIAN\SPARK\dashboard"
```

### 3.7 一键初始化并启动

在后端仓库根目录直接运行：

```powershell
.\start_project.cmd
```

启动脚本会自动创建 Python 虚拟环境并安装 Flask/PyMySQL。如果 `./.local/ncs.env` 不存在，它会自动调用数据库初始化脚本。启动前还会检查 `dashboard_overview` 是否存在已发布批次：结果库为空时，自动导入 `./data_exchange/packages/` 中最后更新的 ADS 包；没有数据包时会停止启动并提示放入数据，避免前端在空库上显示“等待上游数据”。无需输入任何 MySQL 密码。

也可以只执行数据库初始化：

```powershell
.\scripts\setup_new_machine.ps1 `
  -VmHost <vm-ip> `
  -MysqlPort 3306
```

脚本依次完成：

1. 检查虚拟机 MySQL 端口；
2. 检查 Python 3.11/3.12；
3. 创建 `./.venv/` 并安装项目依赖；
4. 使用无密码 root 连接；
5. 确认 MySQL 正运行在 `skip-grant-tables`；
6. 创建 `ncs_analytics`、控制表、结果表、索引和视图；
7. 验证稳定视图合同；
8. 生成 Git 忽略的 `./.local/ncs.env`。

成功标志：

```text
READY: recovery-mode MySQL schema and views are ready.
Local config written to .../.local/ncs.env
```

脚本可重复执行。依赖已经安装时可以跳过重复安装：

```powershell
.\scripts\setup_new_machine.ps1 `
  -VmHost <vm-ip> `
  -MysqlPort 3306 `
  -SkipDependencyInstall
```

### 3.8 导入 ADS 数据和导出数据集

初始化只创建数据库结构，不会自动生成业务数据。仓库根目录提供统一数据交换目录：

```text
data_exchange/
├── packages/    # 放待导入的 ADS v2.5 目录、ZIP 或 TAR.GZ
├── models/      # 放模型目录、ZIP 或 PTH 权重
└── exports/     # 生成的数据集目录和 ZIP
```

把数据包放入 `./data_exchange/packages/` 后，在后端仓库根目录执行：

```powershell
.\import_data_package.cmd
```

未指定文件时，脚本自动选择 `packages/` 中最后更新的数据包。也可以明确指定目录或压缩包：

```powershell
.\import_data_package.cmd ".\data_exchange\packages\batch-001.zip"
```

脚本支持解压目录、`.zip`、`.tar.gz` 和 `.tgz`，会校验包路径、Manifest、Schema、哈希、行数和主键，然后将合格批次发布到 `.local/ncs.env` 指向的虚拟机 MySQL。原始数据包不会被修改或删除。

#### 更新已有业务数据

更新数据不需要重新建库，也不要直接修改 `rpt_*` 表。每个新批次使用新的文件名和 `sourceBatchId`，保留旧包以便审计和回滚。

Windows 手工更新：

```powershell
# 1. 把最新 ADS v2.5 包复制到 data_exchange/packages/
# 2. 明确指定新包，避免误选旧包
.\import_data_package.cmd ".\data_exchange\packages\ads-v25-20260915.zip"
```

导入器会在事务中完成校验、暂存、发布和旧批次切换；失败时旧的 `PUBLISHED` 批次保持不变。导入成功后刷新：

```text
GET /api/v1/meta/data-status
GET /api/v1/dashboard/overview
```

虚拟机 Shell 自动更新：

```bash
# 在虚拟机完成复制后再生成 .ready 标记
cp batch-002.zip "$NCS_ADS_EXCHANGE_ROOT/ready/batch-002.zip.part"
mv "$NCS_ADS_EXCHANGE_ROOT/ready/batch-002.zip.part" \
   "$NCS_ADS_EXCHANGE_ROOT/ready/batch-002.zip"
touch "$NCS_ADS_EXCHANGE_ROOT/ready/batch-002.zip.ready"

# 立即处理一次；持续监听则运行 watch_ads.sh
./scripts/shell/sync_ads_once.sh
```

不要在文件仍在传输时创建 `.ready`，不要同时运行多个同步进程。Shell 和 Windows 导入使用同一套校验、幂等和发布逻辑。

新 ADS 批次导入后，如果需要刷新 AI 预测，确认模型仍在 `./data_exchange/models/`，然后执行：

```powershell
.\.venv\Scripts\python.exe .\scripts\ensure_prediction_data.py
```

该命令会根据最新已发布的 `load_hourly` 批次重新生成预测；若该批次已有 `PUBLISHED` 预测，则自动跳过。只更新模型、不更新 ADS 数据时，也执行同一命令即可。

导出数据库中全部机器学习数据集：

```powershell
.\export_dataset.cmd
```

默认导出到带时间戳的 `./data_exchange/exports/dataset-YYYYMMDD-HHMMSS/`，并生成同名 ZIP。也可以选择单个数据集或时间范围：

```powershell
.\export_dataset.cmd --dataset load_hourly
.\export_dataset.cmd --dataset station_hour_daily --station-id 369001
.\export_dataset.cmd --dataset all --start-date 2015-01-01 --end-date "2015-12-31 23:59:59"
```

需要指定输出目录或不生成 ZIP 时：

```powershell
.\export_dataset.cmd --output ".\data_exchange\exports\manual-export" --no-zip
```

上述两个脚本都使用当前仓库的 `./.venv/` 和 `./.local/ncs.env`，不写死虚拟机 IP、密码或本机绝对路径。首次使用前至少成功运行一次 `./start_project.cmd`。

要显示 AI 预测，将模型同学交付的模型 ZIP、模型目录或 `.pth` 权重放入 `./data_exchange/models/`。`./start_project.cmd` 会自动安装 NumPy/PyTorch，并检查当前 `load_hourly` 批次是否已有预测；没有预测时会自动验证模型、登记版本、激活并发布未来 24 小时预测。模型缺失时普通统计大屏仍可启动，但 AI 区域会保持不可用。

底层高级命令仍可直接调用：

PowerShell（Windows，在后端仓库根目录）：

```powershell
Get-Content .\.local\ncs.env | ForEach-Object {
  if ($_ -match '^([^#=]+)=(.*)$') {
    Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
  }
}

.\.venv\Scripts\python.exe .\scripts\import_ads_v23.py `
  --package .\data_exchange\packages\ads-v25 `
  --database-url $env:NCS_DATABASE_URL `
  --skip-initialize
```

脚本名称保留 `v23` 是为了兼容旧调用，当前实现会根据 Manifest 识别并导入 ADS v2.5 的 18 个数据集。

### 3.9 启动后端和前端

PowerShell（Windows，在后端仓库根目录）：

```powershell
Test-Path .\.local\ncs.env
.\start_project.cmd
```

启动脚本会先检查 `./.venv/`：不存在时自动使用 Python 3.11/3.12 创建，缺少 Flask、PyMySQL 或项目包时自动安装。首次运行会要求输入当前虚拟机 IP，并将数据库地址保存到 Git 忽略的 `./.local/ncs.env`。前端不在常见相邻目录时会要求输入其目录并保存，后续启动无需重复输入。

- 查询 API：`http://127.0.0.1:5000`；
- Vue 大屏：`http://localhost:5173`。

数据库简易管理窗口按需单独启动：

```powershell
.\.venv\Scripts\python.exe .\scripts\run_db_console.py
```

访问 `http://127.0.0.1:5002/db-console`。窗口只负责连接检查、日志和受控 SQL，不负责远程启动或停止虚拟机 MySQL。

端口 `5000` 或 `5173` 已被占用时，启动脚本会保留已有进程。修改代码或配置后，应先在对应终端按 `Ctrl+C` 停止旧进程，再重新启动。

### 3.10 运行测试

PowerShell（Windows）：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

需要连接真实 MySQL 的环境测试必须使用虚拟机 MySQL；默认测试中的少量跳过项表示未提供真实 MySQL、ADS 包或预测依赖，不代表单元测试失败。

### 3.11 可选：部署虚拟机 Shell 自动同步

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
export NCS_DATABASE_URL='mysql+pymysql://root@127.0.0.1:3306/ncs_analytics'
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

### 3.12 常见错误

`MYSQL_RECOVERY_MODE_REQUIRED`：MySQL 没有按当前实训方案运行。确认有效配置包含 `skip-grant-tables`、不包含 `skip-networking`，重启后验证 `skip_grant_tables=ON`。

`Missing ./.local/ncs.env`：直接重新运行 `./start_project.cmd`，启动脚本会自动调用初始化；仍失败时查看初始化窗口中最早出现的错误。

`Access denied for user`：当前连接串仍带旧账号或密码，或者 MySQL 没有真正进入恢复模式。重新执行 `./setup_new_machine.cmd` 生成 root 无密码配置，并确认 `skip_grant_tables=ON`。

Windows 显示 `TcpTestSucceeded : False`：检查虚拟机 IP、MySQL 服务、`bind-address`、3306 监听和防火墙来源地址。

把 `mysql -h ...` 或 `systemctl` 输入到 `mysql>`：先执行 `exit` 回到 bash/PowerShell。`SELECT`、`CREATE USER`、`GRANT` 才是在 `mysql>` 中运行的 SQL。
