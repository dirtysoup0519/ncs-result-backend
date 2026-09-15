# NCS 新能源汽车充电桩运营分析大屏 · Frontend V3.5

Vue 3 + Vite + ECharts 前端工程，按 `NCS 大屏接口冻结合同 V1 / 1.0-rc1` 实现。

V3.5 以 V3.4 为唯一基线，API、Adapter、状态模型、Mock 合同与 ECharts 生命周期保持不变；本版只处理第二轮真实浏览器截图暴露出的视觉问题，并继续使用最新数据侧交接包校准开发演示图形。

## V3.5 视觉修复重点

- 订单平台分布恢复稳定的 `graphic` 居中方案，中心总订单数字缩小并严格居中；
- 历史负荷折线改为更接近 Excel 平滑线的连续曲线，隐藏逐点节点；
- AI 预测置信区间改为全预测时段持续可见的连续带，并保证预测值始终位于上下界之间；
- 预测分界仅标记为 `AI预测`，删除开发实现说明；
- Heatmap 明确指定 `visualMap.dimension=2` 与 `encode.value=2`，颜色真正按 kWh 数值映射；
- TOP10 排名徽标缩小并增加行间距；
- 删除多数冗余说明文字、DEMO/质量通过标签与整行 Footer，把空间还给图表；
- 无副标题的卡片使用更紧凑 Header，并放大标题；
- 保留真正有解释价值的副标题：负荷双轴、费用/电量双轴、历史过程口径、运营建议口径。

## V3.5 视觉验收模式

开发环境 `.env.example` 默认：

```env
VITE_USE_MOCK=true
VITE_DEMO_DATA=true
```

因此首次启动仍会直接看到雷达图、AI 预测和站点×时段热力图。V3.5 不再在页面各处重复堆叠 `DEMO` 标签；正式联调时必须将 `VITE_DEMO_DATA=false` 并切换真实 API。

最新数据侧交接包仍用于演示形态校准：真实订单小时高峰集中在 11/12 和 16/17 点，站点订单呈明显长尾，hour=2 没有订单。正式业务结论仍以 `/api/v1` 真实响应为准。

## 1. 快速运行

```bash
npm ci
npm run check
npm run dev
```

开发模式默认使用合同同构 Mock，不依赖 Flask/Hadoop/Hive。

若当前网络环境导致 `npm ci` 无法完成，也可在网络正常时执行：

```bash
npm install
npm run check
npm run dev
```

## 2. 自检命令

```bash
npm run verify          # Mock 合同、严格类型、跨组件守恒
npm run verify:adapters # 正向 fixture、合法边界、反向协议测试
npm run verify:syntax   # JS / Vue <script setup> 静态语法检查
npm run verify:all      # 上述三项
npm run build           # Vite 生产构建
npm run check           # verify:all + build，交付前推荐
```

V3.5 当前 Adapter 验证覆盖：

- 默认完整 fixture；
- legal empty；
- complete-schema partial；
- ratio 正常舍入；
- 平台 ratio 与 `orderCount / totalOrderCount` 一致性；
- 稀疏 Heatmap；
- ISO `Z` / `+08:00` 在 `Asia/Shanghai` 下的等价解释；
- envelope/meta 协议错误的 requestId 追踪；
- **18 个合法边界用例 + 49 个非法 DTO 反例**。

## 3. V3.2 继承的关键收口

### 3.1 empty 与 payload 双向一致

合法空数据使用：

```text
HTTP 200 + code=OK + meta.empty=true
```

集合型接口按各自冻结结构校验：

```text
meta.empty=true  + 合法空结构 -> UI empty
meta.empty=false + 实际空 payload -> protocol error
```

已覆盖 Overview、平台分布、时长、工作日/周末、Ranking、趋势、Process、AVAILABLE Prediction、AVAILABLE Heatmap 等主要组件。

`meta.partial=true` **不会自动放松冻结 schema**。当前含义是“数据覆盖不完整，但响应结构仍完整”；若后端以后希望 partial 允许固定 KPI/metric 缺项，需要双方另行补充合同。

### 3.2 Ratio：允许正常舍入，但拒绝明显矛盾

Ratio 仍必须是 `[0,1]` 内的 decimal string。

V3.2 不再使用固定 `±0.0005` 之类的统一误差，而是根据后端返回 decimal string 自身的小数精度推导舍入容差：

```text
"0.66"   -> 按两位小数舍入容差判断
"0.6580" -> 按四位小数舍入容差判断
```

平台分布还会验证：

```text
orderRatio ≈ orderCount / totalOrderCount
```

只做一致性检测，**不会重新计算后覆盖后端 ratio**。因此正常舍入可以通过，但平台占比互换、总和只有 0.30 等明显错误会被拒绝。

### 3.3 requestId 覆盖公共 envelope/meta 错误

`adaptEnvelope()` 统一包裹：

```text
assertSuccessEnvelope
+
业务 DTO Adapter
```

因此无论错误发生在 `meta.dataDate / generatedAt / staleness`，还是业务 DTO 内部，都会尽量保留原响应的 `requestId`，便于对应 Flask 日志。

### 3.4 Metadata 缺项采用联调期保守策略

当前冻结简表没有明确“遗漏 componentCode”的正式语义，因此 V3.2 不替后端把缺项静默猜成 unavailable：

```text
显式 available=false
-> unavailable

capabilities / manifest 缺项
-> metadata unknown / error
-> 若已有上次成功数据，则继续展示并提示刷新异常

manifest=true 但 capability!=true
-> metadata contradiction / error
```

这是**联调期的安全默认**，不是对后端合同的新增冻结。真实联调时仍应由后端负责人确认 metadata 是否必须列全，以及遗漏 code 的正式语义。

### 3.5 批次一致性告警

前端轻量比较合法 `success + empty` 响应的：

```text
meta.dataVersion
meta.dataDate
```

若最终页面同时存在多个非空批次/业务日期，给出全局告警，但不直接让所有组件失败。

并行刷新期间新旧组件会短暂混合，因此 **V3.2 在整轮 refresh 完成前暂不显示 batchWarning**，避免中间态误报闪烁。

### 3.6 Heatmap

Heatmap 支持三种清晰语义：

```text
UNAVAILABLE
-> 能力未接入
-> stations=[] / points=[] / valueRange={null,null}

AVAILABLE + meta.empty=true
-> 能力存在，但当前查询范围无数据
-> stations=[] / points=[] / valueRange={null,null}

AVAILABLE + meta.empty=false
-> 正常业务数据
```

V3.2 **允许稀疏 points**，不强制 `stations × 24` 完整笛卡尔积；但继续验证：

- `hours` 为完整 0～23；
- point 引用的 `stationId` 必须已登记；
- `(stationId, hour)` 不重复；
- hour 在 0～23；
- `isObserved` 为 boolean；
- 显式补零点 `isObserved=false` 时 value 必须为 0；
- `valueRange` 合法。

### 3.7 Prediction

预测使用“预测分界点”语义：

```text
actual.hour < cutoffHour
forecastStartAt >= cutoffHour
forecast 第一项从 forecastStartAt 对应小时开始
```

`forecastStartAt` 会先转换到 `Asia/Shanghai` 业务时间，再与 `date/cutoffHour` 比较；不会按 ISO 字符串字面小时判断。

预测参数来自显式配置：

```text
VITE_PREDICTION_DATE=2019-09-13
VITE_PREDICTION_CUTOFF_HOUR=16
```

这只是当前联调入口，不代表最终产品参数来源。算法正式接入后，应再确认参数来自固定答辩场景、筛选器、后端模型元数据或其他正式来源。

### 3.8 Windows 跨平台脚本

`check-syntax.mjs` 使用 Node 官方 `fileURLToPath()` 将 `import.meta.url` 转为文件系统路径，避免 Windows 下：

```text
/D:/...
%20
```

等 URL pathname 与真实路径不一致的问题。

## 4. 已稳定、不要再重构的部分

- ECharts DOM ref / ResizeObserver / dispose 生命周期；
- 已有成功数据后的刷新保留与临时失败回退；
- decimal string 与 JSON integer 的严格类型边界；
- 雷达 normalization 未登记时降级为原始值表格；
- Top10 `totalFees DESC, stationId ASC`；
- Top10 业务 0 显示为 0 宽度，不伪造最小正值条；
- 预测 actual / forecast cutoff 边界及上海时区解释；
- process-summary exactly-once、负电流方向和“平均峰值温度”；
- Mock / DEMO 与真实能力边界；
- Tooltip 使用 ECharts `richText`，避免直接把动态业务字符串拼进 HTML。

## 5. 当前能力策略

开发视觉验收默认：

```text
VITE_USE_MOCK=true
VITE_DEMO_DATA=true
VITE_PREDICTION_DATE=2019-09-13
VITE_PREDICTION_CUTOFF_HOUR=16
```

此时 `loadPrediction`、`stationHourHeatmap` 与工作日/周末雷达使用开发 fixture 直接出图，便于视觉验收。V3.5 为减少界面噪声，不再在每张卡片和 Header 中重复显示 DEMO 标签；这些数据仍然不是正式业务结论。

真实 Flask 联调时应切换：

```text
VITE_USE_MOCK=false
VITE_DEMO_DATA=false
```

正式能力状态继续由 `/meta/capabilities` 与 `/dashboard/manifest` 决定。

## 6. 对接 Flask

开发联调 `.env.local`：

```text
VITE_USE_MOCK=false
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:5000
```

Vite dev server 会通过 proxy 转发 `/api`。

### 生产 / 答辩部署

Vite proxy 只存在于开发服务器。生产构建后应由 Nginx/部署服务器把 `/api/v1` 反向代理到 Flask，或者把 `VITE_API_BASE_URL` 配成可访问的完整 API 前缀并正确配置 CORS。

生产环境默认真实 API；若没有显式设置 `VITE_USE_MOCK`，不会静默携带 Mock。参考 `.env.production.example`。

## 7. 页面业务语义

- KPI：不显示未经定义的同比/环比和假 sparkline。
- 平台分布：主体为订单；占比使用后端 `orderRatio`，前端只做一致性校验。
- 时长分布：固定 `[0,60) / [60,120) / [120,180) / [180,+∞)`。
- 工作日/周末：归一化未启用时展示原始值表格，不由前端发明尺度。
- 站点 TOP10：标题明确为“站点充电费用 TOP10”，排序 `totalFees DESC, stationId ASC`。
- 费用趋势：只表达充电费用与充电量，不表达利润、收益或 `serviceFee`。
- 过程指标：历史聚合、非实时；负电流保留方向；`average_max_temperature` 显示为“平均峰值温度”。
- 运营建议：只做保守、可追溯的规则化表述，不把相关性包装成设备故障或实时 AI 结论。
- 时间：按 `Asia/Shanghai` 展示。

## 8. 安全与依赖

业务图 Tooltip 使用 ECharts `richText` 渲染，不把站点名、平台名、分桶文字等后端动态字符串直接拼进 HTML Tooltip。

当前 ECharts 5.x 的依赖审计风险作为已知依赖项记录。课程项目联调稳定后再单独评估 6.x 大版本升级，避免在真实联调阶段引入无关回归。

ECharts 当前仍采用全量导入，因此 Vite 可能提示主 chunk 偏大。对于本机/局域网答辩不是阻断项；真实联调和视觉验收结束后，如有余量再改按需加载。

## 9. 当前明确不做的事情

- 自动刷新：manifest 的 `refreshIntervalSeconds` 已解析，但 V3.2 不启用定时刷新；当前使用手动刷新。
- ECharts 大版本升级 / 按需打包：不是真实接口联调前阻断项。
- 浏览器 E2E 框架：当前以 `npm run check` + 人工刷新/resize 冒烟为主；课程项目无需为了测试框架继续增加工程复杂度。

建议至少人工验证：

```text
首次进入
连续刷新 3~5 次
窗口 resize
单接口临时失败后恢复
empty 响应
DEMO prediction/heatmap 开关
1920×1080 与 1366×768
```

## 10. 工程结构

```text
src/
├─ api/                 # Axios、领域 API、元数据 API
├─ adapters/            # envelope、严格数值类型、业务 / metadata DTO
├─ config/              # 预测显式配置
├─ mock/                # 合同同构 Mock + 可选 DEMO fixture
├─ composables/         # Dashboard 编排、刷新状态、ECharts 生命周期
├─ components/dashboard/
├─ views/Dashboard.vue
└─ styles/
scripts/
├─ verify-contract.mjs
├─ verify-adapters.mjs
└─ check-syntax.mjs
```

## 11. 下一阶段：停止静态大改，进入真实联调

V3.5 完成后，不建议继续做大规模 Mock/Adapter 架构重构。优先：

1. 在 Windows 开发机执行 `npm ci && npm run check`；
2. 接真实 Flask P0 接口；
3. 与后端确认 capabilities / manifest 的**缺项语义**；
4. 确认 `partial` 仅表示数据覆盖不完整、固定 schema 仍完整；
5. 核对真实 `dataVersion/dataDate` 与 empty 行为；
6. 优先推动真实 `stationHourHeatmap`，保证中央主视觉至少有一张真实核心图；
7. prediction 未完成时继续保持 `UNAVAILABLE`；
8. 最后做 1920×1080、1366×768 和投影环境人工视觉验收。
