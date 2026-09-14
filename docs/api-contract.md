# NCS 抽象接口与通信协议契约

> 状态：公共抽象合同；大屏主要查询路由已实现，管理域的 ADS 专用导入入口和历史 ML 预留未实现
> 契约版本：`1.0-rc1`
> 依赖数据合同：`docs/data-contract.md`
> 前端首屏冻结合同：`docs/大屏接口冻结合同_v1.md`
> 前端首屏字段示例：`docs/前端接口协议.md`
> 本文只定义边界、请求、响应和行为，不给出具体代码实现

> 当前业务与部署结构以 `项目业务架构与代码规划.md` 为准；本文中的机器学习接口全部是未来预留。

> **当前范围覆盖说明（2026-09-14）**：`/internal/v1/ml/*` 与 `/ml-internal/v1/*` 均为历史预留，不在当前实现范围，也不对调用方承诺可用。上游提供的预测结果通过通用数据集导入/发布接口进入结果库。大屏预测查询只有在存在已发布的处理后预测数据集时才启用。详见 `当前范围决策.md`。

## 1. 接口域

接口分为三组，不能混用权限：

| 接口域 | 提供方 | 调用方 | 前缀 | 网络范围 |
| --- | --- | --- | --- | --- |
| 大屏查询 API | `analytics-query-api` | Vue 3 / DataV 投屏页面 | `/api/v1` | 按部署需要开放 |
| 数据管理 API | `data-admin-service` | Windows/虚拟机内部管理工具 | `/internal/v1` | 仅内网 |
| 机器学习作业 API | 未来预留，当前不部署 | 调度器、内部管理工具 | `/ml-internal/v1` | 不可用 |

原则：

- 查询 API 只读 `api_v1_*` 视图。
- 数据管理 API 不训练模型，不提供任意 SQL。
- 机器学习作业 API 不直接写 MySQL 发布表。
- 投屏页面不调用任何 `/internal` 接口。

## 2. 能力等级

| 标记 | 含义 |
| --- | --- |
| `P0` | 基础链路必须具备 |
| `P1` | 建议在首轮联调后补齐 |
| `P2` | 依赖机器学习或额外数据合同，前两波稳定后接入 |
| `P3` | 可由前端本地规则先满足，后端仅预留扩展能力 |
| `R` | 预留能力，数据或需求满足后启用 |

预留接口未启用时返回稳定的 `CAPABILITY_DISABLED`，不能返回假数据。

## 3. HTTP 通信约定

### 3.1 基础协议

- HTTPS；开发环境可使用 HTTP。
- JSON 编码固定 UTF-8。
- 请求和响应使用 `Content-Type: application/json`。
- API 时间使用带时区 ISO 8601，统计日期使用 `YYYY-MM-DD`。
- 为避免金额、比例和预测值的二进制浮点误差，定点小数统一序列化为 JSON 字符串；计数仍使用 JSON 整数。
- URL 路径使用复数资源名和 `kebab-case`；JSON 字段使用 `camelCase`。
- GET、HEAD 不改变服务端状态。
- 管理类 POST 支持 `Idempotency-Key`。

### 3.2 通用请求头

| Header | 必需 | 用途 |
| --- | --- | --- |
| `Authorization: Bearer ...` | 部署决定；内部接口必需 | 身份与权限 |
| `X-Request-ID` | 可选 | 调用方请求标识；未提供则服务端生成 |
| `Idempotency-Key` | 管理写接口必需 | 防止重复创建和发布 |
| `If-None-Match` | 查询接口可选 | ETag 条件请求 |
| `Accept-Language` | 可选 | 显示标签语言，不改变字段名 |

### 3.3 通用响应头

| Header | 用途 |
| --- | --- |
| `X-Request-ID` | 全链路追踪 |
| `ETag` | 查询结果版本 |
| `Cache-Control` | 明确浏览器/代理缓存策略 |
| `Deprecation` | 接口进入弃用期时返回 |
| `Sunset` | 计划停止时间 |

### 3.4 幂等合同

- 相同 `Idempotency-Key` 和相同请求体重复调用，返回第一次调用对应的资源或结果。
- 相同 `Idempotency-Key` 但请求体不同，返回 `409 IDEMPOTENCY_KEY_REUSED`。
- 幂等记录必须覆盖任务创建、发布、回滚、模型登记和模型启用。
- 服务端返回的资源 ID 才是持久标识，幂等键不能代替资源 ID。

## 4. 通用响应合同

### 4.1 成功响应

```json
{
  "code": "OK",
  "message": "ok",
  "data": {},
  "meta": {
    "requestId": "01J...",
    "dataVersion": "dashboard_snapshot:batch_01J...",
    "dataDate": "2026-09-12",
    "generatedAt": "2026-09-12T18:30:00+08:00",
    "staleness": "FRESH",
    "partial": false
  }
}
```

### 4.2 错误响应

```json
{
  "code": "VALIDATION_INVALID_PARAMETER",
  "message": "dateRange is invalid",
  "data": null,
  "errors": [
    {
      "field": "startDate",
      "reason": "must not be after endDate"
    }
  ],
  "meta": {
    "requestId": "01J..."
  }
}
```

错误代码前缀：

- `VALIDATION_*`
- `AUTH_*`
- `CAPABILITY_*`
- `DATASET_*`
- `IMPORT_*`
- `QUALITY_*`
- `PUBLICATION_*`
- `MODEL_*`
- `PREDICTION_*`
- `QUERY_*`
- `DEPENDENCY_*`
- `INTERNAL_*`

### 4.3 HTTP 状态码

| 状态码 | 使用场景 |
| --- | --- |
| `200` | 查询或同步动作成功 |
| `201` | 资源已创建 |
| `202` | 异步任务已接受 |
| `204` | 无响应体的成功动作 |
| `304` | ETag 未变化 |
| `400` | 请求格式或参数错误 |
| `401` / `403` | 未认证/无权限 |
| `404` | 资源不存在 |
| `409` | 幂等冲突、状态冲突或版本冲突 |
| `422` | 结构正确但业务校验未通过 |
| `429` | 超过限流 |
| `500` | 未预期内部错误 |
| `502` / `503` | 依赖失败或服务暂不可用 |

## 5. 通用查询模型

### 5.1 范围参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `dataDate` | date | 指定统计日期，缺省取最新已发布日期 |
| `startDate` / `endDate` | date | 闭区间日期范围 |
| `stationId` | string | 单站筛选 |
| `stationIds` | string[] | 多站筛选，有最大数量 |
| `regionId` | string | 区域筛选 |
| `granularity` | enum | `hour`、`day`、`week`、`month` |
| `metric` | enum | 服务端白名单指标代码 |
| `limit` | integer | 排行或地图最大返回数 |

前端不能传数据库列名、表名、视图名或 SQL 表达式。

### 5.2 分页

列表接口优先使用游标分页：

```json
{
  "items": [],
  "page": {
    "nextCursor": "opaque-value",
    "hasMore": false,
    "limit": 50
  }
}
```

游标是不透明字符串，调用方不得解析。

### 5.3 指标值

```json
{
  "metricCode": "charging_energy_total",
  "label": "总充电量",
  "value": "87342.00",
  "unit": "kWh",
  "precision": 2,
  "comparison": {
    "type": "PERIOD_OVER_PERIOD",
    "value": "0.1260",
    "unit": "ratio"
  }
}
```

### 5.4 时间序列

```json
{
  "seriesCode": "actual_load",
  "label": "历史实际负荷",
  "seriesType": "ACTUAL",
  "unit": "kW",
  "points": [
    {
      "time": "2026-09-12T18:00:00+08:00",
      "value": "320.40"
    }
  ]
}
```

预测序列额外返回 `modelVersion`、`predictionRunId` 和 `generatedAt`。

## 6. 大屏查询 API 总表

### 6.1 元数据与能力

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| P0 | `GET /api/v1/meta/capabilities` | 无 | 已启用主题、接口、筛选和预测时域 |
| P0 | `GET /api/v1/meta/data-status` | `datasetCode?` | 数据日期、活动批次、质量、新鲜度 |
| P0 | `GET /api/v1/meta/metrics` | `topic?` | 指标代码、名称、单位、精度、口径版本 |
| P0 | `GET /api/v1/meta/filter-options` | `topic`、范围参数 | 可用区域、站点、日期和枚举选项 |
| P1 | `GET /api/v1/meta/versions` | 无 | API、视图、数据和模型版本摘要 |

### 6.2 大屏装载与总览

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| P0 | `GET /api/v1/dashboard/manifest` | `dashboardCode?` | 组件数据源、能力状态、建议刷新间隔；不返回布局 |
| P0 | `GET /api/v1/dashboard/overview` | `dataDate?`、`regionId?` | 总览指标卡片 |
| P1 | `POST /api/v1/dashboard/batch` | 已登记组件查询数组 | 分组件结果和局部错误 |
| P1 | `GET /api/v1/dashboard/data-version` | `dashboardCode?` | 当前综合数据版本，用于轻量轮询 |

`dashboard/batch` 不是任意查询接口，只允许白名单组件和每个组件的合法参数。单组件失败时 HTTP 可保持 `200`，同时 `meta.partial=true` 并返回该组件错误。

当前前端原型确认 `dashboard/overview` 首批返回总订单数、总充电量、总充电费用、总用户数和活跃站点数。V1 暂不返回“较上期/环比”；未来启用时再增加对比值、比例和 `comparisonBasis`。截图和 Mock 中的数字不能作为默认响应。

### 6.3 公共维度与筛选

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| P0 | `GET /api/v1/reference/regions` | `dataDate?` | 区域 ID、名称和可用状态 |
| P0 | `GET /api/v1/reference/stations` | 区域、关键字、cursor | 站点 ID、名称和区域，用于选择器 |
| P0 | `GET /api/v1/reference/enums` | `codes` | 状态、类型、健康等级等代码和标签 |
| P1 | `GET /api/v1/reference/date-range` | `datasetCode` | 数据集实际可查询起止日期 |

### 6.4 充电、营收和设备分析

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| P0 | `GET /api/v1/charging/hourly` | 日期、区域/站点 | 24 小时充电量、会话或负荷序列 |
| P0 | `GET /api/v1/charging/trend` | 日期范围、粒度、指标 | 充电趋势序列 |
| P1 | `GET /api/v1/charging/station-hour-heatmap` | 日期、指标、站点范围/上限 | 站点 × 0～23 小时热力值和观测标记 |
| P1 | `GET /api/v1/charging/duration-distribution` | 日期范围、区域/站点 | `0-1h`、`1-2h`、`2-3h`、`3h+` 订单分布 |
| P1 | `GET /api/v1/charging/weekday-weekend` | 日期范围、区域 | 工作日/周末的原始指标及归一化雷达值 |
| P0 | `GET /api/v1/charging/process-summary` | 日期范围、`stationId?` | 平均 SOC、平均最高温度、平均电压、电流及聚合范围 |
| P0 | `GET /api/v1/revenue/trend` | 日期范围、区域/站点 | 充电费用和充电量趋势；V1 不含服务费/利润 |
| P0 | `GET /api/v1/revenue/summary` | 日期范围、区域/站点 | 充电费用、充电量和订单摘要 |
| P0 | `GET /api/v1/chargers/status-distribution` | 日期/批次、区域/站点 | 空闲、占用、故障等数量和比例 |
| P1 | `GET /api/v1/chargers/type-efficiency` | 日期范围、区域 | 不同桩类型使用率和充电量 |
| P1 | `GET /api/v1/charging/peak-periods` | 日期范围、区域/站点 | 高峰时段及负荷摘要 |

### 6.5 站点接口

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| P0 | `GET /api/v1/stations` | 区域、状态、关键字、cursor | 站点摘要列表 |
| P0 | `GET /api/v1/stations/ranking` | 日期范围、`metric`、`limit` | 站点 Top N 和排名 |
| P1 | `GET /api/v1/stations/map` | 区域、状态、地图边界、`limit` | 坐标、坐标系、状态和摘要 |
| P1 | `GET /api/v1/stations/{stationId}` | 日期/批次 | 单站当前摘要 |
| P1 | `GET /api/v1/stations/{stationId}/trend` | 日期范围、粒度、指标 | 单站趋势 |
| P1 | `GET /api/v1/stations/{stationId}/chargers` | 状态、类型、cursor | 电桩聚合/摘要；不提供控制动作 |
| P1 | `GET /api/v1/stations/region-comparison` | 日期范围、指标 | 区域对比和成本收益 |

### 6.6 用户、电池及其他分析

只有数据来源真实存在时才启用：

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| R | `GET /api/v1/audience/segments` | 日期、区域、分层方式 | 用户分层数量与行为指标 |
| R | `GET /api/v1/audience/profile` | 日期、区域 | 聚合画像雷达指标，不返回个人信息 |
| P0 | `GET /api/v1/audience/platform-distribution` | 日期、区域 | Android、iOS、Web 的订单数、订单占比和可选费用 |
| R | `GET /api/v1/batteries/health-distribution` | 日期、区域 | 健康等级数量、比例、异常率 |
| R | `GET /api/v1/sentiment/summary` | 日期范围、区域 | 聚合舆情统计；要求独立可靠来源 |

### 6.7 机器学习预测接口

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| P2 | `GET /api/v1/predictions/load` | `stationId?`、`regionId?`、`horizon`（1h/6h/24h） | 历史订单数、实际/预测充电量、预测上下界、分界时间和模型版本 |
| P2 | `GET /api/v1/predictions/model-info` | `modelCode?` | 当前活动模型公开摘要和评估指标 |
| P2 | `GET /api/v1/predictions/status` | `modelCode?` | 最新预测批次、覆盖率、新鲜度和可用时域 |
| P1 | `GET /api/v1/predictions/accuracy` | 日期范围、站点/区域、指标 | 预测与实际回流后的误差 |
| P1 | `GET /api/v1/predictions/peak-periods` | 站点/区域、预测日期 | 预测高峰时段 |
| R | `GET /api/v1/predictions/free-capacity` | 站点/区域、时域 | 预测空闲桩或可用容量 |
| R | `GET /api/v1/predictions/anomalies` | 日期范围、区域/站点 | 已发布异常检测结果 |

预测不可用时：

- 没有任何可用批次：`200`，`availability=UNAVAILABLE`，序列为空。
- 有旧预测但过期：可返回旧预测，必须标记 `staleness=STALE` 和真实生成时间。
- 请求不支持的时域：`400 PREDICTION_UNSUPPORTED_HORIZON`。

### 6.8 运营建议

| 等级 | 方法与路径 | 抽象输入 | 抽象输出 |
| --- | --- | --- | --- |
| R，来源待确认 | `GET /api/v1/operations/recommendations` | 日期/批次、`stationId?` | 已登记规则产生的建议、证据指标、严重度和生成时间 |

V1 允许前端根据已确认的高峰时段、Top1 站点等字段套用固定模板。查询后端不得临时拼接建议；只有需要统一管理且存在已确认规则来源时才启用该接口。

### 6.9 健康与观测

| 等级 | 方法与路径 | 输出 |
| --- | --- | --- |
| P0 | `GET /health/live` | 进程存活；不访问外部依赖 |
| P0 | `GET /health/ready` | 视图和数据库只读连接是否就绪 |
| P1 | `GET /internal/metrics` | Prometheus 格式，仅内网 |

## 7. 大屏投射专项合同

### 7.1 Manifest

`GET /api/v1/dashboard/manifest` 返回数据能力，不保存前端布局：

```json
{
  "dashboardCode": "ncs-operations-screen",
  "dataVersion": "01J...",
  "recommendedRefreshSeconds": 300,
  "widgets": [
    {
      "widgetCode": "overview",
      "available": true,
      "endpoint": "/api/v1/dashboard/overview",
      "refreshSeconds": 300
    },
    {
      "widgetCode": "loadPrediction",
      "available": true,
      "endpoint": "/api/v1/predictions/load",
      "refreshSeconds": 1800
    }
  ]
}
```

### 7.2 局部失败

- 每个组件独立请求或通过受控 batch 查询。
- 单组件失败不清空其他组件数据。
- 前端保存最后一次成功结果，并显示该结果的 `generatedAt`。
- 全局状态必须分别显示统计数据日期和预测生成时间。
- API 不返回颜色、坐标、动画和投屏分辨率配置。

## 8. 数据管理 API 总表

### 8.1 数据集和 Schema

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `GET /internal/v1/datasets` | 查询数据集目录和状态 |
| P0 | `POST /internal/v1/datasets` | 登记受控数据集，不创建任意表 |
| P0 | `GET /internal/v1/datasets/{datasetCode}` | 查询粒度、负责人、活动批次 |
| P1 | `PATCH /internal/v1/datasets/{datasetCode}` | 修改描述、启用状态等非破坏字段 |
| P0 | `GET /internal/v1/datasets/{datasetCode}/schemas` | 查询结构版本 |
| P0 | `POST /internal/v1/datasets/{datasetCode}/schemas` | 登记新结构版本并执行兼容性检查 |
| P0 | `POST /internal/v1/datasets/{datasetCode}/schemas/validate` | 校验 manifest/schema，不导入数据 |
| P1 | `GET /internal/v1/datasets/{datasetCode}/lineage` | 查询 ADS、结果表、视图和 API 血缘 |

### 8.2 导入任务

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `POST /internal/v1/import-jobs` | 根据 manifest 创建幂等导入任务 |
| P0 | `POST /internal/v1/ads-v21/imports` | 同步校验并导入服务器本地 ADS v2.1 解压包；可选择 `A0`、`B` 波次 |
| P0 | `GET /internal/v1/import-jobs` | 按数据集、日期、状态查询任务 |
| P0 | `GET /internal/v1/import-jobs/{jobId}` | 查询阶段、进度、计数和错误摘要 |
| P0 | `POST /internal/v1/import-jobs/{jobId}/start` | 启动已创建任务 |
| P1 | `POST /internal/v1/import-jobs/{jobId}/cancel` | 取消尚未发布的任务 |
| P1 | `POST /internal/v1/import-jobs/{jobId}/retry` | 对可重试失败创建新尝试 |
| P0 | `POST /internal/v1/import-jobs/{jobId}/validate` | 执行数据质量校验 |
| P0 | `POST /internal/v1/import-jobs/{jobId}/publish` | 发布已通过校验的任务 |
| P1 | `GET /internal/v1/import-jobs/{jobId}/manifest` | 返回脱敏 manifest |
| P1 | `GET /internal/v1/import-jobs/{jobId}/quality-results` | 查询本批质量结果 |

`POST /internal/v1/ads-v21/imports` 请求必须包含 `packagePath`、`actor`，可选 `waves`，默认导入 `A0` 和 `B`。数据库结构必须先由迁移账号初始化；该接口使用管理账号，仅执行包校验和 DML 导入，不执行 DDL。

### 8.3 发布与回滚

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `GET /internal/v1/publications` | 查询当前和历史发布 |
| P0 | `GET /internal/v1/publications/{publicationId}` | 查询发布范围、批次和审计信息 |
| P0 | `GET /internal/v1/datasets/{datasetCode}/active-publication` | 查询当前活动版本 |
| P0 | `POST /internal/v1/datasets/{datasetCode}/rollback` | 回滚到指定已发布批次 |
| P1 | `POST /internal/v1/datasets/{datasetCode}/reconcile` | 对账 ADS、结果表和视图计数 |

回滚请求必须提供目标批次和原因，不接受“回滚到上一个”这种含糊指令。

### 8.4 质量规则

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `GET /internal/v1/quality-rules` | 查询规则、级别和适用数据集 |
| P1 | `POST /internal/v1/quality-rules` | 登记版本化规则，不接受任意 SQL |
| P1 | `PATCH /internal/v1/quality-rules/{ruleCode}` | 修改阈值或启用状态并保留历史 |
| P0 | `GET /internal/v1/quality-results` | 按批次、规则、级别查询结果 |
| P1 | `POST /internal/v1/quality-results/{resultId}/acknowledge` | 记录 WARN/例外处理意见 |

### 8.5 视图和契约

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `GET /internal/v1/views` | 查询 `api_v1_*` 视图、版本和依赖 |
| P0 | `GET /internal/v1/views/{viewName}` | 查询列合同和消费者 |
| P0 | `POST /internal/v1/views/validate` | 验证列、类型、definer、权限和最小查询 |
| P1 | `POST /internal/v1/contracts/compatibility-checks` | 比较新旧 schema/API 合同性 |

视图创建和数据库迁移不通过 HTTP 执行，只允许版本化迁移工具执行。

### 8.6 模型和预测发布

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `POST /internal/v1/ml/models` | 登记已评估模型及制品引用 |
| P0 | `GET /internal/v1/ml/models` | 按模型代码、状态查询版本 |
| P0 | `GET /internal/v1/ml/models/{modelVersion}` | 查询特征版本、指标和制品摘要 |
| P0 | `POST /internal/v1/ml/models/{modelVersion}/activate` | 启用通过门槛的模型 |
| P1 | `POST /internal/v1/ml/models/{modelVersion}/deactivate` | 停用模型但保留历史 |
| P0 | `POST /internal/v1/ml/prediction-runs` | 登记预测 manifest 并创建导入任务 |
| P0 | `GET /internal/v1/ml/prediction-runs/{runId}` | 查询导入、质量和发布状态 |
| P0 | `POST /internal/v1/ml/prediction-runs/{runId}/validate` | 校验预测覆盖、范围和版本 |
| P0 | `POST /internal/v1/ml/prediction-runs/{runId}/publish` | 发布预测结果 |
| P1 | `GET /internal/v1/ml/model-metrics` | 查询模型历史误差和漂移摘要 |

### 8.7 审计和运行状态

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `GET /internal/v1/audit-logs` | 按操作者、动作、对象和时间查询 |
| P0 | `GET /internal/health/live` | 管理进程存活 |
| P0 | `GET /internal/health/ready` | MySQL、导入适配器和迁移版本状态 |
| P1 | `GET /internal/v1/system/status` | 数据集、失败任务、过期数据和模型摘要 |

## 9. 机器学习作业 API 总表

### 9.1 特征与训练

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `GET /ml-internal/v1/feature-sets` | 查询可用特征集和版本 |
| P0 | `POST /ml-internal/v1/feature-sets/validate` | 校验特征结构、时间范围和泄漏风险规则 |
| P0 | `POST /ml-internal/v1/training-jobs` | 创建版本化训练任务 |
| P0 | `GET /ml-internal/v1/training-jobs` | 查询训练任务 |
| P0 | `GET /ml-internal/v1/training-jobs/{jobId}` | 查询阶段、参数摘要、指标和日志引用 |
| P1 | `POST /ml-internal/v1/training-jobs/{jobId}/cancel` | 取消未完成任务 |
| P1 | `POST /ml-internal/v1/training-jobs/{jobId}/retry` | 基于相同配置创建新运行 |
| P0 | `POST /ml-internal/v1/training-jobs/{jobId}/evaluate` | 运行固定评估流程 |
| P0 | `POST /ml-internal/v1/training-jobs/{jobId}/register` | 向管理服务登记合格模型 |

### 9.2 推理与回评

| 等级 | 方法与路径 | 抽象行为 |
| --- | --- | --- |
| P0 | `POST /ml-internal/v1/prediction-jobs` | 使用指定活动模型创建离线预测任务 |
| P0 | `GET /ml-internal/v1/prediction-jobs/{jobId}` | 查询进度、覆盖和输出 manifest |
| P1 | `POST /ml-internal/v1/prediction-jobs/{jobId}/cancel` | 取消未发布预测任务 |
| P0 | `POST /ml-internal/v1/prediction-jobs/{jobId}/submit` | 向管理服务提交预测结果 |
| P1 | `POST /ml-internal/v1/backtests` | 对固定历史窗口执行回测 |
| P1 | `GET /ml-internal/v1/backtests/{backtestId}` | 查询回测指标和分站点误差 |
| P1 | `POST /ml-internal/v1/drift-checks` | 计算数据/预测漂移 |

机器学习接口只接受登记过的特征集、模型、目标和算法配置代码，不接受调用方上传任意可执行代码。

## 10. 异步任务合同

创建异步任务返回：

```json
{
  "code": "ACCEPTED",
  "data": {
    "jobId": "job_01J...",
    "status": "CREATED",
    "statusUrl": "/internal/v1/import-jobs/job_01J..."
  }
}
```

通用作业状态：

```text
CREATED -> QUEUED -> RUNNING -> SUCCEEDED
                         └----> FAILED
CREATED/QUEUED/RUNNING --------> CANCELED
```

领域状态，例如 `VALIDATED`、`PUBLISHED`，由具体资源另外表达，不与执行状态混用。

## 11. 事件与回调预留

基础阶段可以轮询；需要异步联动时启用事件或签名 Webhook。事件名称：

- `dataset.import.completed`
- `dataset.quality.failed`
- `dataset.published`
- `dataset.rolled_back`
- `model.evaluation.completed`
- `model.activated`
- `prediction.completed`
- `prediction.published`
- `data.stale.detected`

事件抽象结构：

```json
{
  "eventId": "evt_01J...",
  "eventType": "prediction.published",
  "eventVersion": "1.0",
  "occurredAt": "2026-09-12T18:30:00+08:00",
  "subject": "prediction_run/pred_01J...",
  "data": {},
  "traceId": "01J..."
}
```

事件至少投递一次，消费者必须按 `eventId` 幂等；不得假设严格顺序。Webhook 必须签名并设置重放时间窗。

## 12. 鉴权与授权合同

### 12.1 查询 API

- 公共展示环境可匿名只读，但必须有限流和严格查询范围。
- 如有登录要求，使用 Bearer Token；Token 中只放稳定身份和角色标识。
- 不在请求参数中接受数据库账号或数据表权限。

### 12.2 内部 API

- 数据管理与机器学习 API 必须认证。
- 权限按动作拆分：`dataset.read`、`import.execute`、`publication.publish`、`publication.rollback`、`model.register`、`model.activate`、`audit.read`。
- 发布、回滚和启用模型必须记录操作者、原因、目标版本和 requestId。
- 服务间身份与人员身份分开，不共用长期静态 Token。

## 13. 限流、超时与重试

- 查询 API 对调用方和接口分别限流。
- 地图、批量查询和长时间范围接口设置更严格上限。
- 查询超时不自动无限重试；投屏端使用退避并保留最后成功数据。
- 管理写接口只在幂等键存在时允许安全重试。
- 质量失败、模型评估不合格和 schema 不兼容不得自动重试。
- 具体超时数值在性能测试后确定，合同只保证失败可识别。

## 14. 版本与弃用

- URL 主版本只在不兼容 API 变更时升级。
- 兼容新增字段不升级 `/api/v1`，但消费者必须忽略未知可选字段。
- 字段不得复用为不同语义。
- 弃用接口至少提供 `Deprecation`、`Sunset` 和替代接口说明。
- API、视图、数据 schema、指标和模型分别版本化，不使用一个版本号代替全部版本。

## 15. 契约测试要求

### 15.1 上游生产者测试

- manifest 满足 schema。
- 样例数据字段、类型、粒度与版本一致。
- 行数、唯一键和校验值正确。
- 新版本兼容性检查通过。

### 15.2 查询 API 测试

- 正常、空数据、过期数据、非法参数和依赖失败行为稳定。
- JSON 类型、字段、单位、精度、枚举和排序符合合同。
- 未启用能力返回 `CAPABILITY_DISABLED`。
- ETag 未变化时正确返回 `304`。
- 预测结果明确包含模型版本和生成时间。

### 15.3 内部 API 测试

- 幂等键重复调用不重复导入或发布。
- 非法状态转换返回 `409`。
- 未通过质量校验不能发布。
- 回滚后视图恢复目标版本，历史记录仍保留。
- 无权限主体不能发布、回滚或启用模型。

## 16. 接口实现前必须确认

1. ADS 数据集和真实字段。
2. 大屏组件清单及 P0/P1/R 优先级。
3. 每个指标的口径、单位、精度和范围。
4. 负荷预测目标、时间粒度、时域和评估阈值。
5. 匿名投屏还是登录投屏。
6. 数据刷新周期和预测生成频率。
7. 地图坐标系和最大点位数。
8. 调度器使用 HTTP、CLI 还是两者都支持。
9. 哪些内部动作需要人工审批。

## 17. 明确禁止的接口

为保持解耦和安全，不设计以下接口：

- 前端执行 SQL、指定表名或视图名。
- 通过 HTTP 执行任意数据库迁移、建表或删表。
- 上传并执行任意 Python/模型代码。
- 查询请求实时触发训练或推理。
- 大屏调用 Qt、交易业务或设备控制接口。
- 返回密码、连接串、模型本地路径或完整内部异常堆栈。
