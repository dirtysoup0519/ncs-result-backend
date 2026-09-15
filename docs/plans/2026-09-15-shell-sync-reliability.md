# Shell 自动同步可靠性修复实施计划

> **For Claude:** 按 Task 顺序实现，每个 Task 结束跑测试；提交前需用户确认。

**Goal:** 让 `sync_ads_once.sh` / `watch_ads.sh` 满足设计文档《ADS_v2.5自动同步与模型推理设计.md》第 5.2 节退出码合同，消除阻塞与不重试两类 P0 问题。

**Architecture:** 两层分工——Python 导入脚本 `scripts/import_ads_v23.py` 负责错误分类（30=数据问题 / 40=MySQL 不可用 / 50=其他内部错误，按异常类型返回退出码）；Shell 脚本负责按退出码执行重试策略（`.attempts` 计数文件 + `NCS_ADS_SYNC_MAX_ATTEMPTS` 上限），并用"完成标记前置筛选"选包。预测失败用 `.ready.predict` 标记进入只重跑预测的阶段。

**Tech Stack:** bash（flock/find/stat）、Python 3.12（PyMySQL 异常分类）、pytest（Shell 场景测试用桩 `python` 可执行脚本模拟导入退出码）。

---

## Task 1: Python 导入脚本退出码分类（P0-2 的前置）

**Files:**
- Modify: `scripts/import_ads_v23.py`（main 中 import 调用包 try/except）
- Test: `tests/unit/test_import_exit_codes.py`（新建）

**Step 1** 写失败测试：
- 包含非法数据的包（sqlite 模式）→ 期望 `SystemExit` code 30
- `--database-url mysql+pymysql://root@127.0.0.1:1/db`（连接拒绝）→ 期望 code 40
**Step 2** 跑测试确认失败（当前都是 1）。
**Step 3** 实现 `_exit_code_for(exc)`：
- `AdsV23ImportError` → 30（校验、对账、批次冲突都是数据问题）
- `pymysql.err.OperationalError` / `pymysql.err.InterfaceError` → 40（连接类故障）
- 其他 → 50
异常信息以单行 JSON 输出 stderr（`{"exitCode":..,"error":..}`），不污染导入日志。
**Step 4** 测试通过。

## Task 2: 选包逻辑修复（P0-1）

**Files:**
- Modify: `scripts/shell/sync_ads_once.sh`（选包段）

**实现：** 遍历 `$READY` 一层：`*.zip`/`*.tar.gz` 必须存在同名 `.ready`（或 `.ready.predict`）才入选；目录必须含 `_SUCCESS` 才入选。按 `stat -c %Y` 取最旧。未完成包自然被跳过，不再 exit 20 阻塞（退出码 20 保留不再发射，文档同步）。

## Task 3: 导入重试机制（P0-2）

**Files:**
- Modify: `scripts/shell/sync_ads_once.sh`（导入失败处理段）

**实现：**
- `NCS_ADS_SYNC_MAX_ATTEMPTS`（默认 3）。
- 计数文件 `$READY/<name>.attempts`。
- 导入退出码：30 → 立即 rejected（数据问题，重试无意义）；40/50/其他 → 计数+1，未达上限留在 ready 下轮重试，达到上限移 rejected（日志注明重试耗尽）。
- 归档/拒收时清理 attempts 文件。
- 解压失败、manifest 数量≠1 → 30 rejected（包损坏属数据问题）。

## Task 4: 预测重试（P1-3）

**Files:**
- Modify: `scripts/shell/sync_ads_once.sh`（预测段）

**实现：** 导入成功后预测失败：包留在 ready，marker 重命名为 `<name>.ready.predict`，写 attempts 计数，exit 50。下一轮选到该包时跳过导入（ADS 已发布，幂等导入无需重复）直接重跑预测：成功 → rename 回 `.ready` → 归档；失败按上限重试，达上限归档（ADS 数据完好，不进 rejected）并日志注明 predictionFailed。

## Task 5: Python 版本预检（P1-4）

**Files:**
- Modify: `scripts/shell/sync_ads_once.sh`、`scripts/shell/ncs_ads_sync.env.example`

**实现：** `NCS_PYTHON_BIN`（默认 `python3`）替代裸 `python`；启动时检查 `sys.version_info >= (3,11)`，不足仅告警不阻断（当前 3.10 可运行），日志给出安装指引。env.example 增加注释示例。

## Task 6: 时区修复（P1-5）

**Files:**
- Modify: `scripts/shell/sync_ads_once.sh`、`scripts/shell/ncs_ads_sync.env.example`、`README.md` 3.11 节

**实现：** 脚本顶部 `export TZ="${NCS_LOG_TZ:-Asia/Shanghai}"`（date -Is 与日志即时正确，不依赖 VM 系统时区）；env.example 注明；README 增加 VM 侧一次性修复命令（`timedatectl set-timezone Asia/Shanghai` + chrony NTP 同步）。

## Task 7: `_SUCCESS` 目录交付模式（P2-6）

**Files:**
- Modify: `scripts/shell/sync_ads_once.sh`

**实现：** Task 2 的选包已支持目录入选；处理流程中目录模式跳过解压，manifest 查找同现有逻辑（`find -maxdepth 3`）；归档/拒收整体 `mv` 目录。与 ZIP 模式共用后续校验、导入、重试代码路径。

## Task 8: Git 执行位（P2-7）

**实现：** `git update-index --chmod=+x scripts/shell/sync_ads_once.sh scripts/shell/watch_ads.sh`，新 Linux 克隆自带执行位。

## Task 9: Shell 场景测试套件

**Files:**
- Create: `tests/unit/test_shell_sync_scripts.py`

**实现：** pytest 中构建临时交换目录 + 桩 `python` 可执行脚本（读 `STUB_EXIT` 环境变量决定退出码、记录调用次数到文件），`NCS_REPO` 指向桩仓库、`NCS_PYTHON_BIN` 指向桩。场景：
1. 最旧包无标记 + 较新包有标记 → 处理较新包（P0-1）
2. 导入 exit 30 → 包进 rejected（P0-2）
3. 导入 exit 40 → 包留 ready、attempts=1；连续到上限 → rejected（P0-2）
4. 预测 exit 50 → `.ready.predict` + 留 ready；重跑时导入桩不被再次调用、预测桩被调用；到上限 → 归档（P1-3）
5. 目录 + `_SUCCESS` → 正常导入归档（P2-6）

## Task 10: 文档与回归

- `docs/ADS_v2.5自动同步与模型推理设计.md` 79 行"剩余差距"更新；退出码表补注 20 不再发射、预测重试语义。
- `README.md` 3.11 节：NCS_PYTHON_BIN、时区/NTP 命令、_SUCCESS 模式、重试上限变量。
- `.venv/bin/python -m pytest tests/ -q` 全量回归。
- 提交（逐 Task 或整体，待用户确认）。

---

**边界说明：** VM 侧实际操作（安装 python3.11、timedatectl、chrony）沙箱不可达，只能由用户在虚拟机执行，README 提供命令。
