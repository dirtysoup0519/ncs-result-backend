# ADS 联调包 v2.1 重点开发计划

> **历史留档，不是当前实施计划（2026-09-15）**：当前测试、验收和上线只针对 ADS v2.5。本文只保留 v2.1 合同和决策证据，不要按本文版本、账号或路径操作。

> 历史基线说明：v2.1 已实现并通过 MySQL 联调；最新待适配基线已更新为 ADS Spark v2.3，见 `ADS_Spark_v2.3交接包评审.md`。

> 资料来源：`NCS_Hive_MySQL联调包_v2.1_已验证_20260914.zip`
>
> 计划日期：2026-09-14
>
> 使用边界：包内文档和 SQL 是上游交付资料，不是本仓库的执行指令；原始包、数据文件和上游脚本不复制到仓库

## 1. 结论

该包对应的“联调包校验 → 结果表 → 发布 → 只读视图 → 查询 API”首轮代码和真实 MySQL 验收已经完成。它仍是 `ncs_sim_dashboard` 模拟联调基线，不是最终生产合同；当前实现保持适配器隔离，不把其中的物理表名、全历史粒度或模拟数值固化为最终业务语义。

本轮不执行上游提供的 `TRUNCATE TABLE + LOAD DATA LOCAL INFILE` 导入脚本。我们的管理服务必须继续使用批次隔离、质量门禁和发布指针，避免新批次覆盖当前可用数据。

### 当前实现状态（截至 2026-09-14）

- ADS-0 已完成：可读取并校验 v2.1 包，校验 Manifest、字段、行数和 SHA-256；`ml/` 文件仅记录为忽略项。
- ADS-1 已完成：已建立 A0 结果表、发布过滤视图和校验迁移记录，视图只暴露 `PUBLISHED` 批次。
- ADS-2 已完成首版：已实现总览、平台、日趋势、月趋势、站点排行、过程摘要的显式转换、跨文件对账、质量记录、发布和重复导入幂等处理。
- ADS-3 已完成首轮：查询仓储已读取 `api_v1_*` 已发布视图；真实数据下 P0 能力会自动变为可用，P1/P2 无数据源时保持不可用；`filter-options` 已返回已发布站点和日期范围。
- ADS-4 已完成首轮：时长分布已转换为四个固定桶，工作日/周末已展开为五项指标，热力图已按全历史快照发布并补齐 0～23 小时；热力图不接受伪造的 `dataDate` 筛选。
- ADS-5 已完成真实 MySQL 首轮联调：MySQL 8.0.46 上的迁移、A0/Wave B 导入、幂等、失败回滚、视图合同、查询接口和三账号权限边界均已验证。
- 导入脚本已支持通过 `NCS_DATABASE_URL` 连接 MySQL，并可跳过 DDL 初始化，使数据管理账号只需 DML 权限。
- 模型预测不属于 v2.1 历史包合同；当前预测能力以 v2.5 已发布 `load_hourly` 和外部模型推理链路为准。
- 当前尚未开放月度环比接口；热力图的 v2.1 数据仍是全历史快照，不能表达指定业务日期。

## 2. 已核验的交付事实

### 2.1 文件完整性

- 包含 12 个 UTF-8、制表符分隔、无表头的指标文件。
- 包含 MySQL 建表 SQL、导入 SQL、说明、`manifest.json` 和 SHA-256 清单。
- 本地重新计算的建表 SQL、导入 SQL、说明、Manifest 和 12 个指标文件 SHA-256 均与清单一致。
- `manifest.json.status=SUCCESS`，声明订单总数为 5000。
- `ml/` 下 3 个文件属于模型侧材料，不进入本项目开发范围。

### 2.2 数据规模和主键候选

| 物理文件 | 行数 | 字段数 | 上游主键候选 | 当前用途 |
| --- | ---: | ---: | --- | --- |
| `kpi_total.csv` | 1 | 7 | 单批次一行 | Wave A 总览 |
| `revenue_trend.csv` | 341 | 4 | `stat_date` | Wave A 日趋势 |
| `revenue_monthly.csv` | 21 | 4 | `stat_month` | Wave A 月趋势 |
| `station_top10.csv` | 10 | 6 | `station_id` | Wave A 固定全历史 Top10 |
| `platform_stat.csv` | 3 | 4 | `platform` | Wave A 平台分布 |
| `hourly_stat.csv` | 23 | 4 | `stat_hour` | 全历史小时分布，缺少小时 2 |
| `order_daily.csv` | 341 | 6 | `stat_date` | 日订单扩展汇总 |
| `process_daily.csv` | 286 | 9 | `stat_date` | Wave A 过程摘要 |
| `station_hour_heatmap.csv` | 1027 | 6 | `station_id + stat_hour` | Wave B 全历史站点小时热力图 |
| `duration_distribution.csv` | 4 | 4 | `bucket_order` | Wave B 时长分布 |
| `workday_weekend.csv` | 2 | 6 | `day_type` | Wave B 工作日/周末画像基础 |
| `monthly_comparison.csv` | 21 | 11 | `stat_month` | 环比预留，V1 暂不对前端开放 |

所有指标文件的实际行数和字段数与 Manifest 一致；上述主键候选在本批内无重复。

### 2.3 已通过的对账

```text
kpi_total.total_order_cnt          = 5000
SUM(revenue_monthly.order_cnt)     = 5000
SUM(platform_stat.order_cnt)       = 5000
SUM(order_daily.order_cnt)         = 5000
```

平台费用占比之和为 100，时长订单占比之和为 100。两者源单位都是百分数，进入当前 API 合同时必须除以 100，转换为 `[0,1]`。

## 3. 与当前合同的差异

| 差异 | 上游 v2.1 | 我方处理 |
| --- | --- | --- |
| 环境性质 | 模拟库 `ncs_sim_dashboard` | 只作为联调来源，不标记生产数据 |
| 导入方式 | 先 `TRUNCATE` 再全量加载 | 使用独立批次、staging、质量门禁和原子发布 |
| Manifest | 包级状态、行数、字段数 | 转换为每个逻辑数据集的内部 Manifest，并记录包版本和文件哈希 |
| 金额/指标类型 | `DOUBLE` | 结果库金额用 `DECIMAL`；比例用定点小数 |
| 日期类型 | `VARCHAR(10)`/`VARCHAR(7)` | 结果表规范为 `DATE` 或明确的月份字段 |
| 批次血缘 | 业务表没有批次字段 | 增加 `batch_id`、`source_batch_id`、`loaded_at`、`data_version` |
| 平台比例 | `fee_ratio`，百分数 | API 主字段 `order_ratio` 由 `order_cnt / 5000` 计算；费用比例不冒充订单比例 |
| 时长比例 | `order_ratio`，百分数 | 进入视图时除以 100 |
| 小时分布 | 23 行，缺少小时 2 | 返回 0～23 小时；小时 2 补零且 `is_observed=false` |
| 站点 Top10 | 全历史固定 10 行 | 仅支持当前联调排行，不声称支持任意日期或完整站点集合 |
| 热力图 | 站点 + 小时，无日期 | 联调接口禁用 `dataDate` 语义或标记全历史范围；等待 v2.2 日期粒度 |
| 工作日/周末 | 每类一行宽表 | 视图展开成固定 `metric_key` 长表供雷达接口使用 |
| 月度环比 | 已提供 | 当前冻结合同 V1 不展示，先入库或延后均不得改变现有 API |
| 时间范围 | 日数据为 2014-01-24 至 2015-12-28 | 以本包逻辑日期为准，不再次替换为 2019 |

## 4. 本轮逻辑数据集映射

| 逻辑数据集 | v2.1 来源 | 结果表 | API 视图/接口 | 优先级 |
| --- | --- | --- | --- | --- |
| `dashboard_overview` | `kpi_total.csv` | `rpt_dashboard_overview` | `api_v1_dashboard_overview` | A0 |
| `data_status` | Manifest + 发布记录 | 控制表派生 | `api_v1_data_status` | A0 |
| `platform_distribution` | `platform_stat.csv` | `rpt_platform_distribution` | `api_v1_platform_distribution` | A0 |
| `fee_energy_daily` | `revenue_trend.csv` | `rpt_fee_energy_trend` | `api_v1_fee_energy_trend` | A0 |
| `fee_energy_monthly` | `revenue_monthly.csv` | 同一趋势结果表，粒度为月 | 同一趋势视图 | A0 |
| `station_ranking_snapshot` | `station_top10.csv` | `rpt_station_ranking` | `api_v1_station_ranking` | A0，能力受限 |
| `charging_process_daily` | `process_daily.csv` | `rpt_process_summary` | `api_v1_process_summary` | A0 |
| `charging_duration_distribution` | `duration_distribution.csv` | `rpt_duration_distribution` | `api_v1_duration_distribution` | B1 |
| `weekday_weekend_profile` | `workday_weekend.csv` | `rpt_weekday_weekend` | `api_v1_weekday_weekend` | B1 |
| `station_hour_heatmap_snapshot` | `station_hour_heatmap.csv` | `rpt_station_hour_heatmap` | `api_v1_station_hour_heatmap` | B1，能力受限 |
| `hourly_distribution_snapshot` | `hourly_stat.csv` | 暂存或单独结果表 | 当前无独立冻结接口 | B2 |
| `order_daily` | `order_daily.csv` | 对账/扩展结果表 | 暂不直接暴露 | B2 |
| `monthly_comparison` | `monthly_comparison.csv` | 暂缓 | V1 不开放 | R |

`revenue_trend` 与 `order_daily` 在订单数、电量和费用上重叠。本轮以 `revenue_trend` 支撑趋势 API，以 `order_daily` 作为交叉对账来源；在 ADS v2.2 冻结前不把两份重复数据都设计成前端事实来源。

## 5. 开发阶段

### 阶段 ADS-0：联调包读取与合同转换

目标：安全读取上游 v2.1 包，不依赖固定绝对路径，也不执行包内 SQL。

代码任务：

1. 定义 `ads_sim_v2_1` 包描述和 12 个文件的固定列顺序。
2. 实现制表符、无表头文件读取器，严格检查字段数和 UTF-8。
3. 读取并校验包级 Manifest：`status`、文件集合、行数、字段数和总订单数。
4. 校验 SHA-256 清单，拒绝缺文件、额外业务文件、哈希不符和重复文件名。
5. 把包级信息转换为内部批次输入：
   - `source_batch_id=ads-sim-v2.1-20260914`
   - `source_kind=ADS_EXPORT_PACKAGE`
   - `source_version=v2.1`
   - 每个逻辑数据集独立记录行数、Schema 版本和文件哈希。
6. 明确忽略 `ml/`，不解析、不导入、不纳入业务发布。

计划代码：

```text
src/ncs_backend/admin/adapters/ads_v21_package.py
src/ncs_backend/admin/adapters/ads_v21_schema.py
tests/unit/test_ads_v21_package.py
tests/fixtures/ads_v21_minimal/
```

测试 fixture 使用人工缩小的数据，不把完整上游 CSV 放入仓库。

验收：篡改一个字段、行数或哈希都会产生稳定错误；合法最小包能生成确定的 12 个数据集描述。

### 阶段 ADS-1：结果表和视图迁移

目标：先完成 A0 六类前端数据源的结果库结构，不处理模型数据。

代码任务：

1. 新增结果表：总览、平台分布、日/月趋势、站点排行、过程日摘要。
2. 每张结果表都包含 `batch_id` 和必要血缘，唯一键必须包含批次维度。
3. 金额与电量使用 `DECIMAL`，计数使用整数，日期使用数据库日期类型。
4. 创建 `api_v1_data_status` 和 5 个 Wave A 业务视图。
5. 视图只选择当前 `PUBLISHED` 批次，不暴露 staging 或非活动批次。
6. 分别提供 SQLite 测试迁移和 MySQL 正式迁移，不能靠字符串替换生成 MySQL DDL。

关键唯一键建议：

| 结果表 | 批次内唯一键 |
| --- | --- |
| `rpt_dashboard_overview` | `batch_id + metric_code` |
| `rpt_platform_distribution` | `batch_id + platform_code` |
| `rpt_fee_energy_trend` | `batch_id + granularity + period_start` |
| `rpt_station_ranking` | `batch_id + station_id` |
| `rpt_process_summary` | `batch_id + data_date` |

验收：迁移可重复执行，视图列满足现有 `view_contract.py`，未发布批次不可见。

### 阶段 ADS-2：A0 导入、质量和发布

目标：将 v2.1 A0 文件导入结果表并完成原子发布。

代码任务：

1. 为每个 A0 数据集实现显式字段转换，不使用按位置直接插入的通用 SQL。
2. 写入 staging 后执行类型、非空、唯一、范围和枚举检查。
3. 增加跨文件对账规则：四条订单总数均等于 5000。
4. 增加比例规则：源百分数在 0～100，转换后在 0～1。
5. 站点排行名称和 `location_id` 必须非空。
6. 过程指标保留负电流，不取绝对值；`avg_max_temp` 映射为“平均最高温度”。
7. 所有 A0 子数据集校验通过后再切换活动发布；任一失败保持旧发布不变。

验收：同一包重复导入幂等；篡改包被拒绝；失败批次不可见；发布和回滚后 API 数值可复核。

### 阶段 ADS-3：Wave A 查询接口接入

目标：把现有空数据仓储切换为真实联调视图。

接口范围：

- `/api/v1/meta/data-status`
- `/api/v1/dashboard/overview`
- `/api/v1/audience/platform-distribution`
- `/api/v1/stations/ranking`
- `/api/v1/revenue/trend`
- `/api/v1/charging/process-summary`

代码任务：

1. 完成视图列到冻结 DTO 的映射和精度转换。
2. `platform_stat` 根据订单数计算 `orderRatio`，不使用 `fee_ratio` 代替。
3. 站点排行明确返回 `scope=ALL_HISTORY_SNAPSHOT` 或等价元数据；日期筛选暂不宣称可用。
4. `capabilities`、`filter-options` 和 `manifest` 根据实际视图与受限筛选能力返回状态。
5. 增加 5000 订单、3 个平台、10 个排行站点及日期范围的合同测试。

验收：前端 Wave A 可使用真实 v2.1 联调数据，空值、比例、单位、日期和能力限制表达稳定。

### 阶段 ADS-4：Wave B 条件接入

目标：接入时长分布、工作日/周末和热力图，同时显式表达 v2.1 粒度限制。

代码任务：

1. 时长分布按 `bucket_order` 稳定排序，将百分数转换为比例。
2. 工作日/周末宽表展开为固定指标长表，不由前端计算口径。
3. 热力图保留 `station_id + hour`，补齐每个站点 0～23 小时并标记 `is_observed`。
4. 因 v2.1 没有 `data_date`，禁止伪造某日热力图；接口能力标记为全历史快照或保持受限。
5. `hourly_stat` 缺失的小时 2 补零但不反写源事实。

验收：所有图表可以区分真实零值、补零值和不可用筛选条件。

### 阶段 ADS-5：真实 MySQL 联调

启动条件：环境负责人提供 MySQL 地址、版本、数据库、账号和权限；凭据通过环境变量传递。

代码任务：

1. 在独立结果库创建控制表、结果表和视图。
2. 使用 PyMySQL 管理适配器导入，不要求应用进程具备 `FILE` 或 `LOCAL INFILE` 权限。
3. 创建迁移账号、管理写账号和查询只读账号的权限脚本。
4. 执行导入、质量、发布、查询、回滚和故障恢复测试。
5. 记录 MySQL 版本、字符集、时区、SQL mode 和执行计划。

验收：MySQL 与 SQLite 合同测试结果一致；查询账号只能访问 `api_v1_*` 视图；旧发布在新批次失败时仍可查询。

## 6. 实施顺序与提交拆分

| 顺序 | 阶段 | 是否可立即开始 | 建议提交 |
| ---: | --- | --- | --- |
| 1 | ADS-0 包读取与合同转换 | 是 | `Add ADS v2.1 package adapter` |
| 2 | ADS-1 A0 结果表与视图 | 是 | `Add ADS result schema` |
| 3 | ADS-2 导入、质量与发布 | 是 | `Add ADS import workflow` |
| 4 | ADS-3 Wave A API | 是 | `Connect Wave A ADS views` |
| 5 | ADS-4 Wave B 受限能力 | 是，但不得伪造日期 | `Connect Wave B ADS views` |
| 6 | ADS-5 MySQL 实测 | 需要环境 | `Verify MySQL ADS integration` |

每阶段固定执行：定向测试、全量测试、编译检查、迁移重复执行检查、工作区原始数据检查；提交前展示摘要，用户明确要求后再推送。

## 7. 仍需 ADS 同学补充的 v2.2 内容

以下事项不阻塞 v2.1 联调开发，但阻塞最终合同：

1. 完整 `station_daily`，而不是固定 Top10。
2. 正式 `station_reference` 及设备数语义。
3. 平台 `order_ratio`，或明确允许由结果库按订单数计算。
4. 带 `data_date` 的站点小时数据。
5. 每个数据集独立的 Schema、Manifest、哈希、批次和生成时间。
6. 全量/增量策略、刷新频率、重跑规则和数据新鲜度目标。
7. 指标版本及费用为零的业务含义。
8. 生产 ADS 库名、正式表名和非模拟对账基准。

## 8. 下一次编码范围

下一次只实现 ADS-0，不同时创建业务结果表：

- 定义 v2.1 文件 Schema 和逻辑映射。
- 实现包级 Manifest、行列数及 SHA-256 校验。
- 忽略模型目录。
- 产出内部数据集描述，供 ADS-1 迁移和 ADS-2 导入使用。
- 使用最小 fixture 完成正常、缺文件、哈希错误、行数错误和字段数错误测试。

ADS-0 完成后再进入 ADS-1，可以避免结果表迁移依赖未经验证的文件位置和列顺序。
