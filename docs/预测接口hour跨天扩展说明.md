# 预测接口 hour 字段支持跨天 —— 变更说明

> 目的：让「充电负荷趋势与 AI 预测」图能显示跨天预测（如 17 点预测到次日 17 点）。
> 方案已在组内确认：**放宽 hour 上限，用 ≥ 24 表示次日小时**，不改字段名、不改时间格式。

## 一、字段语义变更

| 字段 | 变更前 | 变更后 |
| --- | --- | --- |
| `forecast[].hour` | 当天小时，0–23 | **从当天 0 点起的小时偏移，0–(cutoffHour+24)** |
| `actual[].hour` | 当天小时，0–23 | **不变**（历史都在当天） |
| `cutoffHour` | 当天分界点，0–23 | **不变** |

编码约定：`24` = 次日 0 点，`25` = 次日 1 点，依此类推。

## 二、后端需要改的内容

1. **`forecast[].hour` 允许 ≥ 24**，按「当天 0 点起的连续小时偏移」输出。
   - 示例：`cutoffHour = 17`、`horizon = 24`
     → `forecast[].hour = 17, 18, 19, …, 40`（共 24 个点）
2. **`forecastStartAt` 保持为当天的 ISO 时间戳**，不随跨天变化。
   - 示例：`2026-09-15T17:00:00+08:00`（业务日期仍是 09-15）
3. **其余字段（`date` / `interval` / `modelVersion` 等）不变。**

## 三、校验规则（前端适配器会照此校验）

| 规则 | 说明 |
| --- | --- |
| `cutoffHour` | 必须为 `0–23` 的整数 |
| `actual[].hour` | 必须 `< cutoffHour`，且 `≤ 23` |
| `forecast[].hour` | 必须 `≥ forecastStartAt` 所在小时，且 `≤ cutoffHour + 24` |
| 重复 | `actual` / `forecast` 各自不得有重复 hour |
| `forecastStartAt` | 转 Asia/Shanghai 后，业务日期必须等于 `date` |

## 四、前端配套改动（本次一并做）

1. `src/adapters/dashboardAdapters.js`：仅放宽 `forecast[].hour` 的上限校验
   （`cutoffHour`、`actual[].hour`、热力图 `hour` 仍严格 `0–23`，不受影响）
2. `src/components/dashboard/LoadForecastChart.vue`：
   - 横轴范围由数据最大 hour 决定（不再写死 0–23）
   - 横轴标签：`hour ≥ 24` 显示为 **「次日 X:00」**（不显示 `24:00`）
   - 跨天处增加视觉分界标记（可选）

## 五、响应示例

```json
{
  "code": "OK",
  "data": {
    "availability": "AVAILABLE",
    "date": "2026-09-15",
    "cutoffHour": 17,
    "forecastStartAt": "2026-09-15T17:00:00+08:00",
    "energyUnit": "kWh",
    "orderCountUnit": "count",
    "actual": [
      { "hour": 0, "orderCount": 3, "chargingEnergy": "16.80" },
      { "hour": 16, "orderCount": 404, "chargingEnergy": "2714.90" }
    ],
    "forecast": [
      { "hour": 17, "predictedEnergy": "2750.10", "lowerBound": "2475.09", "upperBound": "3025.11" },
      { "hour": 23, "predictedEnergy": "2380.40", "lowerBound": "2142.36", "upperBound": "2618.44" },
      { "hour": 24, "predictedEnergy": "2100.30", "lowerBound": "1890.27", "upperBound": "2310.33" },
      { "hour": 40, "predictedEnergy": "1560.80", "lowerBound": "1404.72", "upperBound": "1716.88" }
    ],
    "interval": { "available": true, "confidenceLevel": "0.90" },
    "modelVersion": "v1.0.0",
    "predictionRunId": "run-20260915-01",
    "generatedAt": "2026-09-15T17:05:00+08:00"
  },
  "meta": {
    "requestId": "...",
    "dataVersion": "...",
    "dataDate": "2026-09-15",
    "generatedAt": "2026-09-15T17:05:00+08:00",
    "staleness": "FRESH",
    "empty": false,
    "partial": false
  }
}
```

> `hour: 24` 表示次日 0 点，`hour: 40` 表示次日 16 点（17 + 24 − 1）。

## 六、注意事项

1. **仅预测接口的 `forecast[].hour` 扩展**；热力图、时长分布等其他接口的 `hour`
   保持 `0–23` 不变，不得混用。
2. `actual[].hour` **不需要**扩展（历史数据都在 cutoff 之前，属当天）。
3. 若 `horizon` 为 `1h` / `6h`，`forecast[].hour` 相应变短，上限规则不变。
