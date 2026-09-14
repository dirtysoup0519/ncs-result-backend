# ADS v2.5 自动同步与模型推理设计

> 状态：待实施设计  
> 工作分支：`feature/ads-shell-sync`  
> 业务边界：本项目负责接收上游处理结果、管理结果库、加载已训练模型并执行推理；不负责训练或调参，不执行前端源码修改。

## 1. 结论

项目保留两个数据入口，但共享同一条校验、导入和发布内核：

1. Windows 手动入口用于首次联调、补录和故障恢复。
2. 虚拟机 Shell 自动入口用于发现上游新批次并准实时导入。

预测能力恢复为独立的离线推理子系统：模型同学交付经过登记的模型权重，我们从当前已发布的 `load_hourly` 构造连续 512 小时输入，在 CPU 上生成未来 24 小时预测，事务写入预测结果表，再由现有查询 API 返回给前端。

Shell 自动同步定义为“新批次完成后 30～60 秒内进入结果库”，不是订单级流处理。当前上游交付物是全量 CSV 批次，使用 Kafka、Spark Streaming 或实时训练会增加复杂度且没有数据源支撑。

## 2. 已审查交付物

### 2.1 ADS Spark v2.5

文件：`NCS_下游数据交接包_Spark_v2.5_20260914.zip`

- 批次：`ncs_sim_20260914_192701`
- `schemaVersion`：`2.2.0`
- `metricVersion`：`2.2.0`
- 模式：`FULL_SNAPSHOT`
- 状态：`SUCCESS`
- 时间规则：`YEAR_PLUS_2000`
- 时区：`Asia/Shanghai`
- 数据集：18 个
- Manifest 内 18 个 CSV 的 SHA-256 已全部核对通过。

原有 10 个数据集继续保留，新增：

| 数据集 | 行数 | 用途 |
|---|---:|---|
| `station_top10_snapshot` | 10 | 上游冻结的 Top10 快照 |
| `station_hour_heatmap_profile` | 192 | Top8 站点 × 24 小时完整矩阵 |
| `revenue_monthly` | 21 | 月度订单、电量和费用 |
| `kpi_period_comparison` | 5 | 当前月、上月和环比 |
| `weekday_hour_profile` | 38 | 工作日/周末 × 小时画像 |
| `charge_type_distribution` | 4 | 充电类型对比 |
| `station_charge_type` | 351 | 站点 × 充电类型交叉分析 |
| `process_overview` | 1 | 全周期充电过程概览 |

`load_hourly` 保持 16,872 行连续小时数据，是推理输入的权威来源。
包内 `ml/history.csv` 与 `contract_v2/load_hourly.csv` 的时间戳逐行一致，`kwh` 数值逐行等价；差异仅是小数文本格式。因此正式推理不再重复导入 `history.csv`，统一读取结果库 `load_hourly`。

### 2.2 测试模型

文件：`测试模型.zip`

- 权重：`model_all.pth`
- SHA-256：`e5f9bf8776bd2d0862597b2401d39c3c86fa035b6574673361abac72d3d97838`
- 权重大小：3,801,995 字节
- 架构：多尺度因果卷积 + Transformer Encoder/Decoder
- 输入长度：过去 512 小时
- 输入通道：`kwh`、`hour_sin`、`hour_cos`、`dow_sin`、`dow_cos`
- 输出长度：未来 24 小时
- 目标：小时充电量，单位 `kWh`
- CPU 可推理，不需要 GPU。

权重用 PyTorch `weights_only=True` 安全读取后，包含 `data_cfg`、`model_cfg`、`model_state`、`norm` 和 `test_metrics`。Checkpoint 自报测试指标为 MAE `3.9241`、RMSE `7.3901`，与交接文档中的 `4.21/7.56` 不一致，登记时以权重内元数据为准并保留文档值作为备注。

该模型在峰值样本上的 MAE 为 `15.241`，只能用于趋势展示和教学演示，不能表述成实时容量控制或峰值告警模型。

## 3. 当前代码缺口

### 3.1 v2.5 导入不兼容

当前 `AdsV23PackageReader` 要求 Manifest 数据集集合严格等于 v2.3 的 10 个数据集。v2.5 增加 8 个数据集后会被判定为 `extra`，不能直接导入。

必须先把包解析改成版本化合同：

- v2.3：10 个必需数据集。
- v2.5：18 个必需数据集。
- 相同数据集沿用相同字段合同。
- 新数据集由 v2.5 独立 Schema 描述。
- 不允许通过“忽略所有未知文件”绕过合同校验。

### 3.2 自动同步缺失

现有 `import_ads_v23.py` 只能手动执行，没有：

- 上游完成标记；
- 文件发现与稳定性判断；
- 单实例锁；
- 成功、失败、隔离目录；
- 自动重试；
- Shell 退出码合同；
- 同步运行日志和健康状态。

### 3.3 预测写入链路缺失

已有 `GET /api/v1/predictions/load` 和可选 `api_v1_load_prediction` 查询合同，但缺少：

- 模型登记和激活表；
- 模型文件存储约定；
- 预测运行表；
- 预测结果表；
- 模型加载与推理适配器；
- 预测任务入口；
- `api_v1_load_prediction` 正式视图。

## 4. 双入口总体架构

```text
                          ┌─ Windows 手动命令 / 管理接口
上游 ADS v2.5 交付包 ────┤
                          └─ VM Shell 自动发现
                                   │
                                   ▼
                        Package Intake Service
                  路径安全 / Manifest / SHA-256 / 行数
                                   │
                                   ▼
                         Versioned ADS Importer
                    staging → 对账 → READY → PUBLISHED
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              api_v1_* 视图              load_hourly 发布事件
                    │                             │
                    ▼                             ▼
              Flask 查询 API              Prediction Runner
                                                  │
                                       512 小时 dataset + 模型权重
                                                  │
                                                  ▼
                                      24 小时预测结果原子发布
                                                  │
                                                  ▼
                                      api_v1_load_prediction
```

两个入口不得各写一套导入 SQL。Shell 只负责调度，所有合同校验、幂等、事务和发布逻辑仍由 Python 应用层完成。

## 5. Shell 自动接入方案

### 5.1 目录合同

虚拟机约定目录：

```text
/data/ncs/ads_exchange/
├── incoming/       # 上游正在传输或刚生成的包
├── ready/          # 已完成、等待导入
├── processing/     # 当前正在处理
├── archive/        # 导入成功
├── rejected/       # 合同或质量检查失败
├── logs/
└── locks/
```

上游交付二选一：

1. 先写 `*.zip.part`，完成后原子重命名为 `*.zip`，再创建同名 `*.ready`。
2. 先写临时目录，完成后原子重命名到 `ready/<batchId>/`，目录内必须包含 `_SUCCESS`。

Shell 只处理具有完成标记的对象，绝不通过“文件大小短时间没变化”猜测写入已经结束。

### 5.2 Shell 职责

计划新增：

```text
scripts/shell/sync_ads_once.sh
scripts/shell/watch_ads.sh
scripts/shell/install_ads_sync_cron.sh
scripts/shell/ncs_ads_sync.env.example
```

`sync_ads_once.sh`：

1. 使用 `flock` 获取单实例锁。
2. 按文件名排序取一个 ready 批次。
3. 校验路径、扩展名、完成标记和 ZIP 完整性。
4. 解压到本批次独立临时目录。
5. 调用 Python `validate` 模式读取 Manifest 并核验 18 个数据集。
6. 查询 `sourceBatchId + packageChecksum` 是否已经处理。
7. 调用统一 v2.5 导入命令。
8. 成功移入 `archive`，失败移入 `rejected` 并保存错误原因。
9. 以稳定退出码结束。

退出码合同：

| 退出码 | 含义 | 是否自动重试 |
|---:|---|---|
| 0 | 成功，或没有新批次 | 否 |
| 10 | 锁被其他同步进程占用 | 否 |
| 20 | 包未完成或暂不可读 | 是 |
| 30 | Manifest、字段、校验和或对账失败 | 否，进入 rejected |
| 40 | MySQL 暂时不可用 | 是 |
| 50 | 导入或发布内部错误 | 是，达到上限后 rejected |

`watch_ads.sh` 默认每 30 秒调用一次 `sync_ads_once.sh`。答辩环境优先使用前台 `--watch`，便于展示日志；稳定环境可用 `cron` 每分钟执行一次。不要同时启用 watch 和 cron，`flock` 虽能防并发，但会制造无意义日志。

### 5.3 幂等与发布

幂等键：

```text
sourceBatchId + package SHA-256
```

- 相同批次、相同校验和：返回既有成功结果。
- 相同批次、不同校验和：拒绝并报警，不能覆盖。
- 新批次校验失败：保留旧的 `PUBLISHED` 批次。
- 18 个数据集必须在同一批次事务中完成；任何必需数据集失败都不切换发布指针。
- 预测失败不回滚 ADS 数据发布，继续保留上一版预测并记录预测状态为失败。

### 5.4 “实时刷新”的准确含义

- Shell 在上游完成标记出现后 30～60 秒内导入。
- MySQL 发布提交后，查询 API 下一次请求立即读取新批次。
- 浏览器当前可通过右上角“刷新”读取新数据。
- 如果要求页面无人操作自动刷新，需要前端根据 `manifest.refreshIntervalSeconds` 增加轮询；这属于前端配置/交互工作，不由 Shell 伪装完成。

## 6. ADS v2.5 结果库设计

### 6.1 保留现有计算与接收上游快照

新包同时提供底层结果和大屏即用快照。为避免重复口径：

- 现有 10 个数据集继续作为稳定接口的数据基础。
- 8 个新数据集全部接收入库，用于对账和后续丰富大屏。
- 当前 Top10、热力图、月度趋势和过程概览可与我们内部聚合结果对账。
- 对账一致后，可优先读取上游快照以减少查询计算；不一致时拒绝发布或标记质量失败，不能静默择一。

### 6.2 新增物理结果表

计划新增与 v2.5 数据集一一对应的 `rpt_*` 表，所有表都必须包含：

```text
batch_id, data_version, generated_at, loaded_at, staleness
```

业务字段完全来自 Manifest，不直接执行交接包附带的建表 SQL。DDL 由本项目迁移系统生成，以兼容 MySQL 5.7 和 SQLite 合同测试。

## 7. 模型接入边界与安全

### 7.1 模型包合同

第一版只支持已经审计的架构：

```text
architectureCode = multiscale_conv_transformer_v1
framework = pytorch
inputLength = 512
horizon = 24
features = [kwh, hour_sin, hour_cos, dow_sin, dow_cos]
target = charging_energy
targetUnit = kWh
```

模型交付目录：

```text
model-package/
├── model_manifest.json
└── model_weights.pth
```

`example.py` 只用于人工审查，不在服务端动态执行。服务端内置经过测试的架构适配器，仅用 `torch.load(..., weights_only=True)` 读取权重和普通元数据。禁止上传任意 Python 文件后 `exec`、`import` 或使用不受限 pickle 加载。

模型登记必须校验：

- 文件 SHA-256；
- 架构代码白名单；
- 输入长度、特征顺序、输出长度和单位；
- `model_state` 参数名、形状与内置架构一致；
- `diff_target=false`、`log1p_target=false`、`use_state_feats=false`；
- 归一化均值和标准差存在且标准差大于 0；
- 模型能用固定探针数据完成 CPU 前向计算，结果数量为 24、有限且非负。

### 7.2 模型存储

权重文件不进入 Git，也不存进 MySQL BLOB。默认存放：

```text
/data/ncs/models/<modelCode>/<modelVersion>/model_weights.pth   # VM
.local/models/<modelCode>/<modelVersion>/model_weights.pth     # Windows 开发
```

MySQL 只登记路径、SHA-256、合同、指标和激活状态。

## 8. 预测内部流程

### 8.1 Dataset 构造

输入只读取当前发布的 `load_hourly`：

1. 取得最新连续 512 小时。
2. 按 `stat_time` 升序。
3. 检查无重复、相邻间隔严格为 1 小时。
4. 检查 `total_kwh` 有限且非负。
5. 保留 `is_observed`、`fill_method` 和 `time_quality` 作为数据质量元信息，但当前五通道模型只将 `total_kwh` 和日历特征送入模型。
6. 如果不足 512 行或出现断点，预测任务失败，旧预测继续有效。

模型交接文档声称日历使用“未脱敏真实星期”，而 ADS v2.5 明确使用 `YEAR_PLUS_2000`，存在口径表述矛盾。当前权重以同包 `history.csv` 训练，应继续从规范化后的 `stat_time` 计算日历特征；下一版模型必须在 Manifest 明确 `calendarRule`。

### 8.2 模型生命周期

```text
REGISTERED → VALIDATED → ACTIVE → RETIRED
                    └→ REJECTED
```

- 同一时刻每个 `model_code` 只有一个 ACTIVE 版本。
- 模型启动时加载一次并常驻内存，不允许每个 HTTP 请求重新加载 1～2 秒。
- 激活新版本失败时保留旧 ACTIVE 模型。
- 查询 API 不触发模型训练，也不直接触发重量级模型加载。

### 8.3 预测运行

触发方式：

1. `load_hourly` 新批次发布后自动触发一次。
2. 管理命令手动触发，用于联调和故障恢复。
3. 相同 `modelVersion + inputBatchId + cutoffTime + horizon` 幂等。

流程：

```text
读取 ACTIVE 模型
  → 读取最新 512 小时
  → 构造 5 通道 Tensor
  → CPU 前向推理 24 点
  → 非负检查
  → 写入预测 staging
  → 完整性检查
  → 原子发布 prediction_run
```

模型没有置信区间，因此第一版固定：

```text
intervalAvailable = false
confidenceLevel = null
lowerBound = null
upperBound = null
```

## 9. 结果库新增表

### `ctl_model_version`

| 字段 | 用途 |
|---|---|
| `model_code`、`model_version` | 稳定模型身份 |
| `architecture_code` | 内置适配器选择 |
| `artifact_uri`、`artifact_sha256` | 权重位置与完整性 |
| `input_contract_json` | 512×5 输入合同 |
| `metrics_json` | 权重内测试指标 |
| `status` | REGISTERED/VALIDATED/ACTIVE/RETIRED/REJECTED |
| `created_at`、`validated_at`、`activated_at` | 审计时间 |

### `ctl_prediction_run`

| 字段 | 用途 |
|---|---|
| `prediction_run_id` | 单次运行身份 |
| `model_code`、`model_version` | 使用的模型 |
| `input_dataset_code`、`input_batch_id` | 数据血缘 |
| `input_start_at`、`cutoff_at` | 512 小时窗口 |
| `horizon` | 固定 24 |
| `status` | CREATED/RUNNING/SUCCEEDED/FAILED/PUBLISHED |
| `error_code`、`error_message` | 失败原因 |
| `started_at`、`finished_at`、`published_at` | 运行审计 |

### `rpt_load_prediction`

| 字段 | 用途 |
|---|---|
| `prediction_run_id` | 运行血缘 |
| `series_type` | ACTUAL/FORECAST |
| `target_time` | 小时点 |
| `charging_energy` | 实际或预测 kWh |
| `order_count` | 仅 ACTUAL 可用 |
| `lower_bound`、`upper_bound` | 第一版为空 |
| `model_version`、`generated_at` | 模型与生成时间 |

`api_v1_load_prediction` 只暴露最新 PUBLISHED 预测运行以及与其 cutoff 对齐的实际序列。

## 10. 内部接口与命令

第一版优先提供命令行，便于学生项目部署和排错；HTTP 管理接口复用同一服务层。

```bash
python scripts/register_prediction_model.py \
  --weights /data/ncs/incoming-models/model_all.pth \
  --architecture multiscale_conv_transformer_v1 \
  --model-code global_load_forecast \
  --model-version test-20260913

python scripts/activate_prediction_model.py \
  --model-code global_load_forecast \
  --model-version test-20260913

python scripts/run_load_prediction.py \
  --model-code global_load_forecast \
  --horizon 24
```

内部 HTTP 合同：

| 方法与路径 | 用途 |
|---|---|
| `POST /internal/v1/models/register` | 登记并校验服务器本地权重文件 |
| `GET /internal/v1/models` | 查看版本和状态 |
| `POST /internal/v1/models/{modelCode}/{modelVersion}/activate` | 激活已验证版本 |
| `POST /internal/v1/prediction-runs` | 手动触发预测 |
| `GET /internal/v1/prediction-runs/{runId}` | 查询运行结果或错误 |

这些接口只监听 `127.0.0.1`，不对前端开放文件上传。模型文件先通过受控目录放到服务器，再传路径和预期 SHA-256，避免大文件上传和任意路径读取。

## 11. 前端查询合同

继续使用现有接口：

```http
GET /api/v1/predictions/load?date=2015-12-28&cutoffHour=18&horizon=24
```

响应保留：

- `actual[]`：cutoff 之前的小时实际值；
- `forecast[]`：未来 24 小时预测；
- `modelVersion`；
- `predictionRunId`；
- `generatedAt`；
- `interval.available=false`。

当前前端开发配置仍使用 `2019-09-13 / 16`，而 v2.5 最新业务时间为 `2015-12-28 17:00:00`。联调时应由前端同学修改环境配置为已发布预测的日期和 cutoff；不能由后端伪造 2019 日期，也不能忽略客户端筛选参数返回另一日期的数据。

## 12. 实施阶段

### S1：v2.5 合同与手动导入

- 新增 18 数据集版本化 Schema。
- 新增 8 张结果表和迁移。
- 扩展包校验、跨表对账和导入器。
- 使用本次 v2.5 包完成 SQLite、MySQL 真实导入验收。

验收：18 个 Manifest 校验和、行数、主键和跨表指标全部通过；重复导入幂等。

当前状态：S1 已完成。导入器根据 Manifest 的 `schemaVersion=2.2.x` 自动切换到 v2.5，
已新增 8 张结果表；旧 v2.3 包仅作为兼容输入保留。已用最新 v2.5 包分别在临时
SQLite 和虚拟机 MySQL 完成 18 个数据集的真实导入，批次状态为 `PUBLISHED`。
命令入口仍为 `scripts/import_ads_v23.py`（名称保持兼容，实际支持 v2.3/v2.5）。

### S2：Shell 自动入口

- 实现目录合同、完成标记、`flock`、一次同步和 watch。
- 复用 S1 Python 导入命令。
- 测试半包、坏校验和、数据库断连、重复批次和并发触发。

验收：新包出现后 60 秒内发布；坏包不影响旧数据；日志能定位批次和错误。

### S3：预测结果库与模型注册

- 新增三张模型/预测表和正式预测视图。
- 内置 `multiscale_conv_transformer_v1` 架构。
- 安全读取并验证本次 `model_all.pth`。
- 模型常驻加载和激活回滚。

验收：错误权重、篡改权重、错误输入合同均被拒绝；当前权重探针推理成功。

### S4：Dataset 构造与预测发布

- 从 PUBLISHED `load_hourly` 读取连续 512 小时。
- 生成未来 24 小时预测。
- 保存实际与预测序列并原子发布。
- 接通现有 `/api/v1/predictions/load`。

验收：24 个预测点时间连续、值有限且非负，血缘可追溯到模型版本和 ADS 批次。

### S5：自动串联与前端联调

- 新 `load_hourly` 发布成功后异步触发预测。
- 推理失败保留旧预测。
- 前端环境参数对齐最新预测日期和 cutoff。
- 完成真实页面、日志和故障恢复验收。

## 13. 需要其他同学确认的事项

### 上游 ADS 同学

1. 自动交付使用 ZIP 还是目录。
2. 是否接受 `.part → .zip + .ready` 或 `_SUCCESS` 原子完成协议。
3. 交换目录的绝对路径和执行账号权限。
4. 后续是全量快照还是增量批次；当前 Manifest 为 `FULL_SNAPSHOT`。
5. `calendarRule`：模型日历特征按规范化时间计算，还是另给真实星期字段。
6. v2.5 的 18 个数据集是否必须整体发布，不允许部分成功。

### 模型同学

1. 确认架构固定为 `multiscale_conv_transformer_v1`，以后只换权重还是可能换结构。
2. 解释交接文档与 checkpoint 中 MAE/RMSE 不一致的原因。
3. 确认当前模型以 v2.5 `history.csv` 相同口径训练。
4. 明确模型版本号，不能长期使用 `model_all.pth` 文件名充当版本。
5. 后续权重必须附 `model_manifest.json`、SHA-256 和输入合同。
6. 第一版不提供置信区间是否可接受。

### 前端同学

1. 将预测日期和 cutoff 改为当前已发布预测运行的参数。
2. 确认跨日的未来 24 小时序列能够正常绘制。
3. 数据自动更新如需无人操作刷新，增加基于 `refreshIntervalSeconds` 的轮询。

## 14. 明确不做

- 不训练、重训、调参或宣称模型达到生产精度。
- 不执行模型包中的任意 Python 源码。
- 不允许前端请求即时加载权重或同步执行耗时推理。
- 不把模型权重提交到 Git。
- 不使用数据库 BLOB 保存模型。
- 不把离线批次宣传为设备实时数据。
- 不因预测失败回滚已经验证通过的 ADS 业务数据。
