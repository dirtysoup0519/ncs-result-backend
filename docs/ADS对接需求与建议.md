# ADS 对接需求与建议

> 对接对象：ADS 负责人、ODS/DWD 负责人、结果库与后端负责人；模型负责人仅确认数据口径
>
> 当前范围：处理后数据接入、结果库存储和大屏查询后端；不包含模型训练、推理和模型管理
> 事实来源：最新版 `交接包(2).zip` 中 ODS/DWD/DWS/ADS 脚本、数据交接说明，以及模型同学提供的测试模型交接信息

## 1. 对接结论

现有 ADS 已能支撑 KPI、营收趋势、平台分布、站点 Top10 和全局小时分布的演示，但还不能直接作为正式结果库输入。下一轮对接的重点不是让 ADS 提供更多脚本，而是冻结以下四类合同：

1. 字段合同：字段名、类型、单位、精度、是否为空、枚举和计算口径。
2. 粒度合同：一行代表什么，主键是什么，是否按日期、站点和小时拆分。
3. 批次合同：数据日期、批次 ID、生成时间、全量/增量方式、行数和校验和。
4. 时间合同：原始时间、修复后时间、逻辑业务时间和时间质量标记如何区分。

ADS 负责输出稳定、可复核的聚合数据；本项目负责导入、质量校验、版本发布、回滚、只读视图和 API。双方以数据集合同衔接，不共享内部表，也不让后端重复计算复杂指标。

## 2. 已知上游事实

最新版交接包给出的真实数据规模为：

| 数据 | 表 | 行数 | 关键关系 |
|---|---|---:|---|
| 订单 | `dwd_charging_order` | 3,395 | `session_id` 为会话标识；含用户、站点、区域、平台、费用、电量和起止时间 |
| 充电过程 | `dwd_charging_process` | 1,594 | `esd = session_id` 关联订单 |
| 站点 | `dwd_charging_station_meta` | 105 | `station_id` 与订单站点 100% 关联 |

现有聚合资产包括 `dws_order_daily`、`dws_order_station_daily`、`dws_order_hourly`、`dws_process_daily`，以及 6 张 ADS 表。现有导出文件为制表符分隔、无表头的静态文件。

必须注意：这些脚本证明链路能运行，但脚本和文档中的口径仍需双方确认，不能直接等同于冻结合同。

## 3. 当前必须先解决的时间问题

### 3.1 年份修复存在口径冲突

ODS 原始 `created/ended` 的年份为 `0014/0015`。现有 DWD 脚本把两者都替换为 `2019`，但模型交接说明按 `+2000` 将它们解释为 `2014/2015`，并指出脱敏年份会导致日期推导的星期不可信，应以原始 `weekday` 为准。

ADS 对接前必须共同决定：

- `0014/0015` 是脱敏年份、截断年份，还是应统一映射到 2019。
- 月、日、小时、分钟和秒是否可信。
- 周几以原始 `weekday` 为准，还是从修复日期重新计算。
- 业务展示年份与模型使用的逻辑时间是否允许不同。

建议 DWD/ADS 同时保留：

| 字段 | 含义 |
|---|---|
| `raw_created` / `raw_ended` | 原始字符串，仅用于追溯 |
| `logical_created_at` / `logical_ended_at` | 经共同确认后用于聚合的逻辑时间 |
| `source_weekday` | 原始星期字段 |
| `time_repair_method` | 如 `YEAR_REMAP_2019`、`YEAR_PLUS_2000` |
| `time_quality` | `ORIGINAL`、`REPAIRED`、`INFERRED`、`UNUSABLE` |

在口径冻结前，ADS 不应把修复后的 2019 时间标记为原始真实时间。

### 3.2 过程数据不是连续时序

原始 `record_time` 精度丢失，现有 DWD 使用订单 `created_ts` 代替。交接说明同时指出每个会话通常只有一条过程采样。因此该表只能用于会话级或日级状态摘要，不能表达一次充电过程中 SOC、电压、电流和温度随时间连续变化。

建议：

- 当前大屏的“充电过程”仅定义为历史聚合摘要，不称为实时曲线。
- `record_time_ts` 若来自订单开始时间，增加 `record_time_source = ORDER_CREATED_INFERRED`。
- 未获得真实采样时间前，不生成伪造的分钟级连续数据。
- `charge_current` 为负可能是数据采集符号约定，不应直接解释为放电；若计算功率使用绝对值，必须由数据/模型负责人确认。

最新版的变化是：模拟过程数据已将 `record_time` 改为对应订单开始时刻的 2019 年毫秒时间戳，2,328 行样例中的时间戳逐行唯一。这解决了“所有记录使用同一个脱敏常量”的问题，但没有改变“每个命中会话仅一条采样”的粒度，因此不能称为充电过程连续采样。

新增训练导出中，订单仍保留 ODS 的 `0014/0015`，过程数据则使用 DWD 的 2019 时间。模型组如果同时使用两份文件，必须先确认统一映射规则。该问题不阻塞本项目结果库开发，但说明 ADS 的时间字段仍必须带修复方法和质量标记。

## 4. 模型信息对 ADS 的数据要求

模型不属于本项目，但其输入要求会影响 ADS 是否需要提供一个可复用的处理后数据集。测试模型要求：

- 全网小时级负荷序列。
- 连续、等间隔，每小时一行。
- 至少 512 个历史小时，预测未来 24 小时。
- 基础字段为 `ts,kwh`，其中 `kwh` 表示该小时充电量，单位 `kWh/h`。
- 日历特征依赖小时和星期，因此时间口径必须稳定。

现有 `ads_hourly_stat` 只有按“小时编号 0～23”汇总的 23 行，是小时分布，不是连续时间序列，不能作为模型输入。ADS 若要支持模型同学，应另交付 `ads_load_hourly`：

| 字段 | 要求 |
|---|---|
| `stat_time` | 整点时间，统一格式 `YYYY-MM-DD HH:00:00` |
| `total_kwh` | 该自然小时内的充电量，非负 |
| `order_cnt` | 该小时观测到的订单数 |
| `is_observed` | 有真实聚合数据为 1，补齐小时为 0 |
| `fill_method` | `NONE`、`ZERO` 或已批准的其他方式 |
| `time_quality` | 时间是否修复/推断 |

连续化建议采用“完整小时骨架 + 左连接聚合结果 + 缺口显式标记”，不要只补数值而不保留 `is_observed`。对于跨小时订单，`kwh_total` 如何分摊必须由 ADS 与模型负责人冻结：

- 简化方案：全部计入订单创建小时，容易实现但会制造尖峰。
- 建议方案：按订单在各小时的重叠时长按比例分摊，总和必须等于订单 `kwh_total`。
- 无论采用哪种方式，都必须记录 `allocation_method` 和版本。

结果库只把模型产出的预测结果作为普通处理后数据集导入，不调用模型，也不管理权重。

## 5. ADS 需要交付的数据集

以下名称是逻辑合同名，ADS 可使用自己的物理表名，但必须给出一一映射。

| 优先级 | 逻辑数据集 | 建议粒度/主键 | 来源建议 | 对应后端视图/API |
|---|---|---|---|---|
| P0 | `dashboard_overview` | `data_date + metric_code` | 订单和站点汇总 | `api_v1_dashboard_overview` |
| P0 | `platform_distribution` | `data_date + platform_code` | 订单平台聚合 | `api_v1_platform_distribution` |
| P0 | `station_daily` | `data_date + station_id` | 现有 `dws_order_station_daily` 扩展 | `api_v1_station_ranking` |
| P0 | `fee_energy_daily` | `data_date` | 现有 `dws_order_daily` | `api_v1_fee_energy_trend` |
| P0 | `process_daily` | `data_date`，站点可用时增加 `station_id` | 现有 `dws_process_daily` | `api_v1_process_summary` |
| P0 | `station_reference` | `station_id` | 站点 DWD | 筛选项和展示名称 |
| P1 | `duration_distribution` | `start_date + end_date + bucket_code` | 订单时长分桶 | `api_v1_duration_distribution` |
| P1 | `weekday_weekend_profile` | `start_date + end_date + day_type + metric_key` | 订单时间聚合 | `api_v1_weekday_weekend` |
| P1 | `station_hour_daily` | `data_date + station_id + hour` | 订单按日期/站点/小时聚合 | `api_v1_station_hour_heatmap` |
| 可选上游能力 | `load_hourly` | `stat_time` | 连续化小时负荷 | 模型输入；后端历史负荷展示 |
| 可选上游能力 | `load_prediction` | `prediction_run_id + target_time` | 模型同学提供 | `api_v1_load_prediction` |

不要只交付“全历史 Top10”。建议交付完整的 `station_daily`，排名、日期范围和 `limit` 由结果视图或后端完成。这样可以支持日期筛选，也避免每换一个 TopN 就重做 ADS。

## 6. 需要冻结的指标口径

### 6.1 总览

- `total_order_count`：订单行数还是去重 `session_id` 数。
- `total_fees`：仅 `charging_fees`，不推导服务费、利润或成本。
- `total_kwh`：`SUM(kwh_total)`，需要明确非法值和空值处理。
- `total_user_count`：去重 `user_id`，说明是否跨日期去重。
- `active_station_count`：建议定义为统计周期内至少一笔有效订单的去重站点数。
- `station_count`：站点维表总数，与活跃站点数分开。

### 6.2 平台分布

前端主要需要订单占比，现有 ADS 只有 `fee_ratio`。应增加：

- `order_count`。
- `order_ratio = platform_order_count / all_order_count`。
- `total_fees` 可保留。
- `fee_ratio` 可选；由于 88.8% 订单费用为 0，必须处理总费用为 0 的分母情况。

### 6.3 站点排行

- 默认指标建议为 `total_fees`，但同时交付 `order_count` 和 `total_kwh`。
- 对同值排名确定稳定次序，例如 `metric DESC, station_id ASC`。
- 必须关联出 `station_name`；关联失败的站点不能静默丢失。

### 6.4 时间与过程指标

- 明确自然日边界和时区，建议固定 `Asia/Shanghai`。
- 明确工作日/周末使用哪个星期来源。
- `avg_current` 保留符号，不在 ADS 擅自取绝对值；如另需功率，新增明确字段。
- 明确 `avg_max_temperature` 是逐记录最高温度的平均值，而不是统计周期最高温度。

## 7. 每个数据集必须随批次提供的 Manifest

建议每个 ADS 交付批次附带一个 Manifest，不再依赖无表头文件的列位置：

```json
{
  "datasetCode": "station_daily",
  "schemaVersion": "1.0.0",
  "batchId": "station_daily_2019_full_v1",
  "dataDate": "2019-09-13",
  "generatedAt": "2026-09-14T14:00:00+08:00",
  "loadMode": "FULL_SNAPSHOT",
  "granularity": ["data_date", "station_id"],
  "timezone": "Asia/Shanghai",
  "rowCount": 2800,
  "checksumAlgorithm": "SHA256",
  "checksum": "...",
  "sourceTables": ["ncs_dws.dws_order_station_daily"],
  "metricVersion": "1.0.0"
}
```

同时交付：

- ADS DDL 和字段字典。
- 每个数据集至少 20 行脱敏样例，包含边界值和空值情况。
- 唯一键、分区、排序和刷新方式说明。
- 指标计算 SQL 或可复核伪代码。
- 本批行数、日期范围、最小/最大值和空值统计。

传输格式建议优先使用带表头 UTF-8 CSV/TSV 或 Parquet。若继续使用无表头 TSV，必须把固定列顺序写入 Schema 合同，并提供校验和；不建议让前端直接读取文件。

## 8. 对账与验收条件

ADS 交付达到以下条件后，结果库才接收并发布：

1. 主键唯一，必填字段非空，枚举值在合同范围内。
2. `station_id` 能关联站点维表；不能关联的数量单独报告。
3. 日汇总的订单数、电量和费用与 DWD 在同一过滤口径下相等。
4. 平台订单数之和等于总订单数；`order_ratio` 总和在舍入误差内为 1。
5. 站点汇总之和与全局汇总一致。
6. 小时连续序列覆盖合同日期范围内的全部小时，缺口有 `is_observed/fill_method`。
7. 跨小时分摊后的 `total_kwh` 总和与原订单 `kwh_total` 总和一致。
8. 所有时间修复记录均可通过 `time_quality/time_repair_method` 追溯。
9. 同一个 `batchId` 重复交付内容必须完全一致；内容变化必须产生新批次。
10. 未通过 BLOCKER/ERROR 质量规则的批次不能对查询视图可见。

## 9. 交接包中需要当场核验的问题

1. 旧模拟站点文件 `simdata/nvv2t_md_end.csv` 的重复表头问题已由后续文件 `nvv2t_md_end(1).csv` 修复；新文件包含 105 个唯一 `stationId`。ADS 仍需确认 `facilityType`、`locationId` 和 `device_count` 语义，并提交订单/ADS 到站点维表的关联覆盖率。
2. 现有 `ads_hourly_stat` 只有 23 行，需要确认缺少的是哪个小时；分布表可缺观测小时，但连续序列必须补齐 24 小时骨架。
3. 现有年份统一改为 2019，与模型交接中的 `0014/0015 + 2000` 规则冲突。
4. `record_time` 被订单开始时间替代后，过程数据不再具有真实采样时序语义。
5. `available_energy (kw)` 的名称和注释单位不一致，需要确认是 `kW` 还是 `kWh`。
6. ODS 注释把负电流解释为放电，但业务是充电过程，需要确认传感器符号约定。
7. 现有 `ads_platform_stat.fee_ratio` 不等于前端要求的订单占比。
8. 现有 KPI、Top10 和平台统计是全历史快照，没有 `data_date/batch_id`，不能支持版本发布和日期筛选。
9. 新增训练导出中订单时间保留 `0014/0015`、过程时间使用 2019，跨表时间轴尚未统一。
10. 文档所称模拟时间戳“连续化”实际只是对齐订单开始时刻且逐行唯一，并未形成固定间隔序列。

## 10. 建议的对接会议输出

第一次会议只需关闭以下问题，关闭后即可开始真实结果表和视图实现：

1. 确认 P0 数据集清单及每张表的一行粒度。
2. 确认时间修复规则、星期来源和时区。
3. 冻结六个 P0 指标的公式、过滤条件、单位和精度。
4. 确认 ADS 交付方式：Hive 直连、Sqoop/JDBC，或带 Manifest 的批次文件。
5. 确认全量/增量策略、刷新频率和批次命名。
6. 获取 DDL、字段字典、真实脱敏样例及预期汇总值。
7. 模型负责人确认 `load_hourly` 的跨小时电量分摊、缺口填充和逻辑星期口径。

会议结束应形成一份签字式字段映射表：`ADS 字段 -> 结果表字段 -> api_v1_* 视图字段 -> API 字段`。未确认项明确标为 `UNAVAILABLE`，不得用假数据补齐。

## 11. 双方职责边界

| 事项 | ADS 负责 | 结果库与后端负责 |
|---|---|---|
| ODS/DWD 清洗 | 输出可追溯的清洗结果和质量标记 | 不重复清洗原始数据 |
| 指标计算 | 聚合、分桶、连续化、口径版本 | 校验并按合同导入 |
| 数据交付 | DDL、Schema、Manifest、批次数据、对账基准 | staging、质量门禁、发布和回滚 |
| 查询稳定性 | 不要求暴露 ADS 内部结构 | 通过 `api_v1_*` 视图隔离物理表变化 |
| 前端协议 | 提供业务字段和值域事实 | 统一 JSON、筛选、错误和版本协议 |
| 模型 | 可提供连续小时输入和接收预测结果 | 仅存储/发布预测结果，不运行模型 |
