# NCS 数据与协议契约

> 状态：抽象契约草案  
> 适用范围：Hive ADS、机器学习流水线、MySQL 结果库、数据库管理服务、查询后端和 Web 大屏  
> 契约版本：`1.0-draft`

## 1. 契约目标

本文件定义各模块交换数据时必须共同遵守的语义，不规定 Hive SQL、MySQL DDL、Python 类或具体机器学习算法。

核心目标：

- 上游表名、数据库物理结构和前端展示可以分别演进。
- 所有统计和预测结果都能追溯到数据批次、结构版本和模型版本。
- 只有通过校验并正式发布的数据对大屏可见。
- Qt、交易业务和设备控制不属于本契约。

## 2. 参与方与责任

| 参与方 | 生产内容 | 消费内容 | 责任 |
| --- | --- | --- | --- |
| Hive ADS | 统计结果、机器学习特征 | DWS/ADS 上游数据 | 保证指标语义、粒度和分区完整 |
| `ml-pipeline` | 模型元数据、评估结果、离线预测 | ADS 特征数据 | 保证训练可复现、无时间泄漏、预测可追溯 |
| `data-admin-service` | 导入批次、质量结果、发布状态 | ADS/预测数据及 manifest | 校验、入库、发布、回滚和审计 |
| MySQL `ncs_analytics` | `api_v1_*` 稳定视图 | 已发布结果 | 隔离物理表并提供稳定查询合同 |
| `analytics-query-api` | HTTP/JSON DTO | `api_v1_*` 视图 | 参数校验、组合、补零、排序、版本与错误表达 |
| Vue/ECharts 大屏 | 可视化组件 | 查询 API | 展示数据，不重新定义统计口径 |

## 3. 契约分层

```text
业务语义契约：指标是什么意思、粒度是什么
    ↓
数据集契约：字段、类型、主键、版本、交付方式
    ↓
发布契约：批次、质量、活动版本、回滚
    ↓
视图契约：查询后端可见的稳定 snake_case 列
    ↓
API 契约：前端可见的稳定 camelCase 字段
```

下层不得改变上层语义。例如，视图可以重命名底层字段，但不能把“总费用”悄悄改成“平均费用”。

## 4. 通用标识与基础类型

### 4.1 标识符

| 名称 | 含义 | 约束 |
| --- | --- | --- |
| `dataset_code` | 稳定数据集代码 | 小写 `snake_case`，创建后不复用 |
| `schema_version` | 数据结构版本 | `major.minor` |
| `batch_id` | 导入批次标识 | 全局唯一、不可变 |
| `source_batch_id` | 上游批次标识 | 同一来源内唯一 |
| `publication_id` | 发布记录标识 | 全局唯一 |
| `model_code` | 模型用途代码 | 如 `station_load_forecast` |
| `model_version` | 不可变模型版本 | 不使用 `latest` 作为持久值 |
| `feature_version` | 特征结构和计算版本 | 与模型版本分开管理 |
| `training_run_id` | 单次训练运行 | 全局唯一 |
| `prediction_run_id` | 单次预测运行 | 全局唯一 |
| `station_id` | 站点业务标识 | 跨 ADS、预测和 API 保持一致 |
| `charger_id` | 电桩业务标识 | 显示名称不得代替 ID |
| `session_id` | 充电会话标识 | 仅在确需明细追溯时使用 |

### 4.2 时间

- 时区统一为 `Asia/Shanghai`。
- 日期使用 `YYYY-MM-DD`。
- 时间戳使用带时区的 ISO 8601，例如 `2026-09-12T18:30:00+08:00`。
- `data_date` 表示统计归属日期；`generated_at` 表示结果生成时间；`loaded_at` 表示进入结果库时间；三者不得混用。
- 预测结果必须同时包含 `generated_at`、`target_time` 和 `horizon`。
- 无法可靠恢复的时间值不得猜测修复，也不得进入高频时序模型。

### 4.3 数值、单位和空值

- 金额使用定点小数，币种默认 `CNY`，不得使用二进制浮点保存金额。
- 能量统一使用 `kWh`，功率统一使用 `kW`，时长明确使用秒或分钟。
- 比例内部统一使用 `[0, 1]`，API 元数据声明 `unit=ratio`。
- 数量使用整数；平均值、预测值和评估指标允许小数。
- `null` 表示未知或不适用；真实的零必须写 `0`。
- 图表补零属于查询后端展示逻辑，不能反写结果库伪造成原始事实。
- `NaN`、`Infinity` 和 `-Infinity` 不得进入 JSON 或数据库发布数据。

### 4.4 枚举

枚举使用稳定英文代码；中文只作为显示标签：

```json
{
  "code": "FAULT",
  "label": "故障"
}
```

未知新枚举由消费者按 `UNKNOWN` 处理，不能导致整屏失败。

## 5. 指标定义合同

每个指标必须登记以下内容：

| 字段 | 说明 |
| --- | --- |
| `metric_code` | 稳定代码，如 `charging_energy_total` |
| `display_name` | 中文名称 |
| `definition` | 不依赖实现的业务定义 |
| `formula` | 计算公式或上游字段来源 |
| `unit` | `count`、`kWh`、`CNY`、`ratio`、`minute` 等 |
| `aggregation` | `sum`、`avg`、`max`、`last`、`non_additive` |
| `grain` | 指标有效粒度 |
| `time_basis` | 自然日、自然月、滚动窗口等 |
| `null_policy` | 忽略、按零、不可计算或返回空 |
| `comparison_basis` | 同比/环比的基准定义 |
| `owner` | 口径负责人 |
| `version` | 指标语义版本 |

非可加指标，例如利用率、平均价格和异常率，不能由前端对多个站点结果直接求和。

## 6. 数据集目录

### 6.1 核心统计数据集

| `dataset_code` | 粒度 | 必需维度 | 指标类别 | 优先级 |
| --- | --- | --- | --- | --- |
| `dashboard_snapshot` | 数据日期/发布批次 | 日期、区域可选 | 会话、充电量、费用、站点、异常率 | P0 |
| `revenue_daily` | 日期/区域/站点 | 日期、区域、站点 | 充电费用、充电量、订单；V1 不含服务费/利润 | P0 |
| `charge_hourly` | 日期/小时/区域/站点 | 日期、小时、区域、站点 | 充电量、会话、负荷 | P0 |
| `station_daily` | 日期/站点 | 日期、站点 | 利用率、充电量、费用、在线率 | P0 |
| `station_snapshot` | 发布批次/站点 | 站点、经纬度、坐标系 | 总桩、空闲、占用、故障 | P0 |
| `charger_status` | 发布批次/状态/类型 | 状态、类型、区域/站点 | 数量、占比 | P0 |
| `platform_distribution` | 日期/平台 | 日期、平台 | 订单数、订单占比、可选平台总费用 | P0 |
| `charging_duration_distribution` | 日期/时长桶 | 日期、时长桶 | 订单数、占比 | P1 |
| `weekday_weekend_profile` | 日期范围/日期类型/指标 | 工作日或周末、指标 | 原始值、单位、归一化值 | P1 |
| `station_hour_heatmap` | 日期/站点/小时 | 日期、站点、0～23 小时 | 充电量或已登记指标、观测标记 | P1 |
| `charging_process_summary` | 日期/站点可选 | 日期、站点 | 记录数、会话数、平均 SOC/电流/电压、平均最高温度 | P0，站点粒度待确认 |
| `operation_recommendation` | 生成批次/建议 | 规则、证据指标、适用范围 | 文案、严重度、生成时间 | R，V1 默认前端模板 |
| `user_segment` | 日期/用户分层 | 分层代码 | 人数、次数、时长、消费 | P1，数据可用时启用 |
| `battery_health` | 日期/健康等级/区域 | 健康等级、区域 | 数量、占比、异常率 | P1，数据可用时启用 |

### 6.2 机器学习数据集

| `dataset_code` | 粒度 | 用途 | 优先级 |
| --- | --- | --- | --- |
| `station_load_features` | 站点/特征时间 | 负荷预测训练与推理输入 | P2（前端波次） |
| `load_prediction` | 预测运行/站点/目标时间/时域 | 1h、6h、24h 负荷预测 | P2（前端波次） |
| `load_prediction_actual` | 站点/目标时间 | 预测完成后的实际值回流 | P1 |
| `model_metric_history` | 模型/评估窗口/指标 | 模型效果和漂移展示 | P1 |

### 6.3 系统元数据集

| `dataset_code` | 用途 |
| --- | --- |
| `data_status` | 每个数据集的活动批次、数据日期、质量和新鲜度 |
| `metric_catalog` | 指标定义、单位、精度和可用筛选条件 |
| `capability_catalog` | 当前启用的接口、主题和模型能力 |

## 7. 通用数据集 Manifest

所有 ADS 统计数据、特征数据和预测数据必须随附 manifest：

```json
{
  "contractVersion": "1.0",
  "datasetCode": "station_daily",
  "schemaVersion": "1.0",
  "sourceBatchId": "ads_station_daily_20260912",
  "dataDate": "2026-09-12",
  "grain": ["data_date", "station_id"],
  "source": {
    "kind": "HIVE_PARTITION",
    "uri": "hive://ncs_ads/ads_station_day/dt=2026-09-12"
  },
  "format": "PARQUET",
  "compression": "SNAPPY",
  "rowCount": 105,
  "checksum": {
    "algorithm": "SHA-256",
    "value": "optional-when-source-can-provide"
  },
  "generatedAt": "2026-09-12T18:00:00+08:00",
  "producer": "hive-ads-job",
  "traceId": "01J..."
}
```

约束：

- `source.uri` 仅允许已配置的 `hive://`、`hdfs://` 或受控文件源，不接受任意本地路径。
- `rowCount` 必填；可计算校验值的交付方式必须提供 `checksum`。
- manifest 与数据结构不一致时整批拒绝，不做静默列映射。
- 同一 `datasetCode + sourceBatchId` 重复提交必须幂等。

## 8. 统计结果抽象行模型

每行结果可抽象为：

```json
{
  "dimensions": {
    "dataDate": "2026-09-12",
    "stationId": "S001",
    "regionId": "R01"
  },
  "metrics": {
    "chargingEnergyKwh": "87342.00",
    "sessionCount": 14826,
    "utilizationRatio": "0.7880"
  },
  "lineage": {
    "datasetCode": "station_daily",
    "schemaVersion": "1.0",
    "sourceBatchId": "ads_station_daily_20260912"
  }
}
```

实际存储采用列式字段；此模型只表达维度、指标和血缘的逻辑分区。

## 9. 机器学习特征合同

`station_load_features` 必须包含：

| 类别 | 抽象字段 | 约束 |
| --- | --- | --- |
| 主键 | `station_id + feature_time` | 唯一、非空、时间连续性可检查 |
| 标签 | `target_value` | 明确目标是功率、充电量、会话或空闲桩 |
| 历史特征 | 充电量、会话数、占用数、空闲数 | 只能使用预测时刻之前可获得的信息 |
| 站点特征 | 容量、桩类型、区域 | 记录有效时间或版本 |
| 日历特征 | 小时、星期、节假日 | 生成规则版本化 |
| 外部特征 | 天气等 | 训练和预测两端都必须稳定可得 |
| 血缘 | `feature_version`、来源批次 | 必填 |

禁止：

- 随机切分时序数据造成未来信息泄漏。
- 训练时使用预测时刻之后才产生的字段。
- 在代码中临时修复时间或缺失值却不记录规则版本。
- 特征列变化但仍沿用旧 `feature_version`。

## 10. 模型登记合同

```json
{
  "modelCode": "station_load_forecast",
  "modelVersion": "station_load_forecast_20260912_01",
  "featureVersion": "station_load_features_1.0",
  "algorithm": "abstract-regressor",
  "trainingRange": {
    "start": "2026-01-01T00:00:00+08:00",
    "end": "2026-08-31T23:00:00+08:00"
  },
  "evaluation": {
    "metrics": {
      "mae": "0.0",
      "rmse": "0.0",
      "mape": "0.0"
    },
    "baselineMetrics": {},
    "passed": true
  },
  "artifact": {
    "uri": "artifact://models/station_load_forecast/version",
    "sha256": "required"
  },
  "createdAt": "2026-09-12T18:00:00+08:00"
}
```

- 模型版本不可覆盖。
- 评估未通过的模型可以登记，但不能设为活动模型。
- 制品 URI 只引用受信位置；结果库不存放模型二进制。
- 评估指标必须同时注明数据窗口和聚合方式。

## 11. 预测结果合同

`load_prediction` 每行至少包含：

```json
{
  "predictionRunId": "pred_01J...",
  "modelVersion": "station_load_forecast_20260912_01",
  "featureVersion": "station_load_features_1.0",
  "stationId": "S001",
  "generatedAt": "2026-09-12T18:00:00+08:00",
  "targetTime": "2026-09-12T19:00:00+08:00",
  "horizon": "1h",
  "targetCode": "charging_load_kw",
  "predictedValue": "325.40",
  "lowerBound": "290.00",
  "upperBound": "360.80",
  "unit": "kW"
}
```

约束：

- `horizon` 首批只允许 `1h`、`6h`、`24h`。
- `targetCode`、`unit` 和模型训练目标必须一致。
- 上下界如果模型不支持可为空，但不得伪造。
- 同一预测运行内，主键为 `station_id + target_time + horizon + target_code`。
- 发布前检查站点覆盖率、目标时间连续性、重复值、负值和异常跃迁。
- 查询 API 必须区分 `ACTUAL`、`PREDICTED` 和 `CONFIDENCE_BOUND` 序列。

## 12. 发布与可见性合同

批次状态：

```text
CREATED -> IMPORTING -> IMPORTED -> VALIDATING -> VALIDATED
        -> PUBLISHING -> PUBLISHED

任一步失败 -> FAILED
已发布但不再活动 -> SUPERSEDED 或 ROLLED_BACK
```

规则：

- 只有 `PUBLISHED` 且为活动版本的数据可被 `api_v1_*` 视图读取。
- 快照型数据通过活动批次指针切换；日期型数据按日期事务发布。
- 发布失败不改变旧活动版本。
- 回滚只移动活动指针或恢复旧日期版本，不删除历史批次。
- 同一数据集同一可见范围只能有一个活动版本。
- 统计结果和预测结果分别发布，互不阻塞；API 在元数据中说明各自版本。

## 13. 质量合同

质量规则严重级别：

| 级别 | 含义 | 是否允许发布 |
| --- | --- | --- |
| `BLOCKER` | 主键、结构、行数或核心口径错误 | 不允许 |
| `ERROR` | 重要范围、关联或覆盖率错误 | 默认不允许，可配置审批例外 |
| `WARN` | 可解释的偏差或新鲜度问题 | 允许，但必须在状态接口展示 |
| `INFO` | 统计信息 | 允许 |

最低规则集合：

- schema、必填列、类型和枚举校验。
- 粒度主键唯一性和非空校验。
- manifest 行数与实际行数一致。
- 金额、充电量、时长、SOC、比例、预测值范围校验。
- 站点维度关联覆盖率。
- ADS 汇总值与 MySQL 结果值对账。
- 预测时间连续性、站点覆盖率、模型/特征版本一致性。
- 数据和预测新鲜度。

## 14. Schema 演进合同

- 兼容新增可选字段：提升 `minor` 版本。
- 删除字段、改名、改类型、改变粒度或指标语义：提升 `major` 版本。
- 生产者先提供新版本，消费者完成兼容后再停止旧版本。
- `api_v1_*` 视图不得出现破坏性变更；需要破坏性变更时新建 `api_v2_*`。
- 所有 schema 必须有机器可比较的字段清单和 `schema_hash`。
- 不认识的非必填字段由消费者忽略；不认识的必填字段版本必须拒绝。

## 15. 下游视图合同

查询后端只能依赖以下视图类别：

- `api_v1_dashboard_overview`
- `api_v1_revenue_trend_daily`
- `api_v1_charge_hourly`
- `api_v1_charger_status`
- `api_v1_station_rank`
- `api_v1_station_map`
- `api_v1_station_detail`
- `api_v1_user_segment`
- `api_v1_battery_health`
- `api_v1_prediction_load`
- `api_v1_prediction_model_info`
- `api_v1_data_status`

每个视图必须有：列名、类型、可空性、业务含义、单位、主键候选、支持筛选和排序字段、数据来源、版本和测试样例。

## 16. 安全与隐私

- 不向结果库导入手机号、账户余额、密码、Token 等非大屏必需数据。
- 用户画像优先使用聚合分层，不使用可识别个人身份的明细。
- manifest 不包含密码、JDBC 完整连接串或密钥。
- 模型制品必须校验哈希，禁止加载来源不明的序列化对象。
- 查询账号只读视图；机器学习流水线不能直接写发布表。
- 审计日志记录操作者、动作、对象和结果，不记录密钥及完整敏感载荷。

## 17. 契约验收

一个数据集可以进入实现阶段前，必须具备：

- `dataset_code`、负责人、粒度、schema 和版本。
- 指标定义、单位、空值与聚合规则。
- manifest 样例和不少于 10 行的脱敏样例数据。
- 主键、质量规则和发布方式。
- 对应结果表、视图和 API 消费者。
- 兼容性及回滚方案。

机器学习数据集还必须具备：预测目标、特征版本、时间切分、基线模型、验收指标、预测时域和模型制品管理方式。

## 18. 待确认项

- 负荷预测目标是功率、充电量、会话数还是空闲桩数量。
- ADS 实际表名、字段、分区、数据范围和刷新频率。
- 成本、用户分层、电池健康、平台偏好和舆情是否有可靠来源。
- 地图坐标系。
- 预测评估指标、聚合范围及合格阈值。
- 大屏数据和预测的最大可接受延迟。
