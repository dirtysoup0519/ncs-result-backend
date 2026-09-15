# NCS Dashboard V3.5 · 交叉评审收敛清单

> 综合两轮独立评审与项目实际代码核对后的最终待修改项。
> 每一项包含：问题现象 / 问题成因 / 详细理由 / 具体修改方案 / 预期收益。
> 按「是否应在本阶段动手」排序，而非按严重程度排序。

---

## 定位说明

两轮评审共提出约 9 条问题，经逐条对着真实代码核对后，收敛为 **2 项真实待处理 + 3 项低成本顺手项**，其余 4 项明确判定为「现在不做」。

判断基准统一为：**这个改动是否真的会改善本项目在"答辩 + 真实联调"这一目标下的结果。** 不以"工程完备性"为基准。

---

# 一、真实待处理项

## 1. 生产构建可能被显式启用 Mock

**优先级：高（部署前必须处理）**

### 问题现象

`src/api/client.js` 的 Mock 开关逻辑为：

```js
const mockSetting = import.meta.env.VITE_USE_MOCK

export const useMock = mockSetting == null
  ? import.meta.env.DEV
  : String(mockSetting).toLowerCase() === 'true'
```

即：只要环境变量被显式写入，**生产构建也会走 Mock**。当前 `.env.local` 中确实写着 `VITE_USE_MOCK=true`，而该文件与 `.env.production.example` 内容高度相似，存在被误带入生产构建的风险。

### 问题成因

设计意图是「未配置时按环境推断，显式配置时以配置为准」——这个优先级本身合理。但它把「显式配置」的权限同时开放给了 DEV 和 PROD，且没有任何一层在生产环境下做拦截。

一旦生产走 Mock：
- 页面会正常显示，看不出任何异常；
- 走的是 `mockGet`，其中的参数 fallback 分支（参数不匹配时静默返回 `UNAVAILABLE`）会一起生效；
- 表现是「图表静默不显示、且无任何错误提示」，而不是报错。

### 详细理由

这一项之所以排第一，不是因为概率高，而是因为**失败时不可观测**。答辩现场如果发生，无法现场定位；而其他所有问题最多是"显示不好看"，只有这一项是"看起来正常但数据是假的"。

需要说明的是：这不属于"合同被前端擅自加强"的范畴——它是构建期安全网，不改变任何响应语义，因此不存在与项目「不发明业务语义」原则的冲突。

### 具体修改方案

推荐方案（配置错误即暴露）：

```js
export const useMock = mockSetting == null
  ? import.meta.env.DEV
  : String(mockSetting).toLowerCase() === 'true'

if (import.meta.env.PROD && useMock) {
  throw new Error('[NCS Dashboard] Production build must not enable VITE_USE_MOCK')
}
```

备选方案（静默强制关闭）：

```js
export const useMock = import.meta.env.PROD
  ? false
  : String(mockSetting ?? String(import.meta.env.DEV)).toLowerCase() === 'true'
```

**推荐前者**：答辩部署时，配置错误应当立刻可见，而不是让页面静默展示 Mock 数据。

**执行时机**：真实 API 联调成功、准备封版部署时再落地。当前仍在用 Mock 调 UI，现在封死会导致开发不便。

### 预期收益

- 消除"生产页面看起来正常但展示假数据"这一唯一不可观测的故障模式；
- 部署配置错误在构建/首屏阶段即暴露，而非答辩现场才发现。

---

## 2. 费用趋势 points 的时间顺序无契约保障

**优先级：中（联调检查项，不先改 Adapter）**

### 问题现象

`src/adapters/dashboardAdapters.js` 的 `adaptFeeEnergyTrend()` 校验了 `granularity`、`units`、`meta.empty`、逐点非空与类型，但**不校验 `points` 是否按 `period` 升序**。

而 `src/components/dashboard/FeeEnergyTrend.vue` 直接按数组下标连线：

```js
xAxis: { data: points.map((p) => p.period) },
series: [{ data: points.map((p) => p.totalFees) }, ...]
```

若后端返回 `2019-01 / 2019-03 / 2019-02 / 2019-04`，ECharts 会忠实地按数组顺序 `Jan → Mar → Feb → Apr` 连线。

### 问题成因

冻结合同（README）中明确声明了排序契约的接口只有 TOP10：

> 站点 TOP10：排序 `totalFees DESC, stationId ASC`

费用趋势接口**通篇未提及排序要求**。因此当前 Adapter 不校验顺序，是「严格遵守合同」的结果，而非疏漏。

这里需要精确区分两种说法：
- ✅ 可以确认：合同**没有冻结**「趋势必须有序」这一约束；
- ❌ 不能确认：作者**有意规定**趋势无需有序（也可能是遗漏）。

### 详细理由

**不建议现在直接在 Adapter 加断言。** 原因：

当前接口能接受的合法响应集合 = 所有结构合法的 points 数组。一旦加入升序断言，这个集合会缩小——这是**协议语义的扩张**，与项目核心原则（不用前端发明后端语义）直接冲突。

但**这个风险必须被记录而非忽略**，因为它的视觉后果具有误导性：乱序折线会呈现出"剧烈波动"的形态，可能被误读为业务结论。这比"某个常量定义重复"要显眼得多。

### 具体修改方案

分两步：

**第一步（本次）：写入联调 checklist，不改代码。**

```text
[ ] 向数据侧确认 /revenue/trend 的 points 是否保证按 period 升序
[ ] 要求 Flask 侧明确 ORDER BY period ASC
[ ] 用真实接口返回肉眼确认一次顺序
```

**第二步（仅在第一步确认后）：视团队决定补合同测试。**

若数据侧确认"保证升序"，则在 Adapter 加断言，并同步补一条反向用例进 `verify-adapters.mjs`：

```js
{
  const bad = clone(mockResponses.feeEnergyTrend)
  ;[bad.data.points[1], bad.data.points[2]] = [bad.data.points[2], bad.data.points[1]]
  expectReject('trend points must be chronological', () => adaptFeeEnergyTrend(bad))
}
```

### 预期收益

- 前端不在合同之外擅自扩大拒绝范围，保持契约一致性；
- 同时把真实风险纳入联调验收，不会在乱序数据下产出误导性的趋势图形。

---

# 二、低成本顺手项（不单独开修改轮次）

## 3. `registeredCodes` 存在两处独立定义

**优先级：低**

### 问题现象

```js
// src/composables/useDashboard.js:44
const registeredCodes = Object.freeze(Object.keys(componentConfig))

// src/adapters/metadataAdapters.js:4
export const REGISTERED_COMPONENT_CODES = Object.freeze([...])
```

同一个概念有两个 source of truth，目前内容一致但无任何机制保证同步。

### 问题成因

两个文件是独立演化的：编排层从 `componentConfig` 派生，适配层手写常量。历史上可能各自引入，未统一。

### 详细理由

与第 2 项不同，这一项**不改变任何响应语义**——合并后合法响应集合不变、非法响应集合也不变。它是纯粹的内部去重，因此不受「不发明语义」原则的约束。这是它与第 2 项的关键区别。

若只改其中一处（新增组件时），`adaptCapabilities` 会把新 code 判为未知组件码并报错，但错误信息不会指向"两处定义不同步"这个根因，排查成本较高。

### 具体修改方案

让编排层引用适配层的常量，保持单一来源：

```js
// useDashboard.js
import { REGISTERED_COMPONENT_CODES } from '../adapters/metadataAdapters.js'
```

并在模块加载时加一行一致性断言，使两处不同步时立即失败：

```js
if (import.meta.env.DEV) {
  const derived = Object.keys(componentConfig)
  if (derived.length !== REGISTERED_COMPONENT_CODES.length ||
      derived.some((code) => !REGISTERED_COMPONENT_CODES.includes(code))) {
    console.warn('[NCS Dashboard] componentConfig 与 REGISTERED_COMPONENT_CODES 不同步')
  }
}
```

### 预期收益

- 新增/删除组件时只需改一处；
- 若未来不同步，开发期即可发现，而非在元数据校验处抛出语义不相关的错误。

---

## 4. KPI 卡片配色依赖排序后的数组下标

**优先级：低**

### 问题现象

```js
// Dashboard.vue
const kpiOrder = ['total_order_count', 'total_charging_energy', ...]
const kpiTones = ['blue', 'teal', 'orange', 'purple', 'green']

const orderedKpis = computed(() => [...items].sort((a, b) => kpiOrder.indexOf(a.metricCode) - kpiOrder.indexOf(b.metricCode)))
```

```vue
<KpiCard v-for="(item, index) in orderedKpis" :tone="kpiTones[index]" />
```

颜色通过**排序后的位置下标**关联，而非通过 `metricCode`。

### 问题成因

`kpiTones` 与 `kpiOrder` 是两条平行数组，靠下标隐式对应，没有显式的关联关系。

### 详细理由

**需要精确说明风险边界**：`adaptOverview` 已强制要求五个冻结 KPI 码各出现且仅出现一次：

```js
if (items.length !== OVERVIEW_CODES.size || ...) throw new ApiProtocolError(...)
```

因此在现有合同下，**不会实际发生颜色错位**——缺项会在进入视图层之前就被拦截。

但这是**跨层的隐式假设**：视图层依赖了适配层的一个不变量，而视图层自身并不知道这个前提。若未来放宽 overview 校验（例如允许 `partial` 时缺项），视图层会静默错色而非报错。

### 具体修改方案

改为显式映射，与 `KpiCard` 内部已有的写法保持一致（该组件本就用 `metricCode` 查表取图标和单位）：

```js
const kpiToneMap = {
  total_order_count: 'blue',
  total_charging_energy: 'teal',
  total_charging_fee: 'orange',
  total_user_count: 'purple',
  active_station_count: 'green'
}
```

```vue
:tone="kpiToneMap[item.metricCode] ?? 'blue'"
```

### 预期收益

- 消除跨层隐式假设，视图层不再依赖适配层不变量；
- 与 `KpiCard.vue` 内部风格统一，后续新增 KPI 时无需同时维护两条平行数组。

---

## 5. `OperationInsights` 重复截断

**优先级：极低（纯洁净项）**

### 问题现象

同一次截断发生两次：

```js
// useDashboard.js — 已在源头上限制
return result.slice(0, 2)
```

```vue
<!-- OperationInsights.vue — 再次限制 -->
<article v-for="(item, index) in insights.slice(0, 2)" ...>
```

### 问题成因

编排层为保证输出形状稳定做了截断，视图层为防御空数组又做了一次，属于各自实现时的重叠防护。

### 详细理由

无功能风险，仅是可读性问题——两处限制值分散在不同文件，未来若调整显示条数需要改两个地方，且容易漏改。

### 具体修改方案

保留编排层的 `slice(0, 2)` 作为数据契约的收口点，删除组件内的重复截断：

```vue
<article v-for="(item, index) in insights" :key="`${item.title}-${index}`" ...>
```

或反向统一（由组件负责展示条数、编排层不限）。**推荐前者**，因为数据形状收口在编排层更符合本项目现有的分层习惯。

### 预期收益

- 展示条数只有单一控制点，调整时不会漏改；
- 消除"这里为什么又截一次"的阅读疑问。

---

# 三、明确判定为「现在不做」

以下项均已确认**风险真实存在**，但在当前阶段（课程答辩 + 固定数据域 + 单页大屏）修改的投入产出比为负。记录在此以便未来复核。

| 项目 | 判定 | 理由 |
|---|---|---|
| 自动刷新（`refreshIntervalSeconds` 未消费） | 不做 | 手动刷新已满足答辩；贸然引入会带来并发刷新、定时器清理、图表闪动三类新问题 |
| E2E（Playwright / Cypress） | 不做 | 已有 contract + adapter + syntax + build 四重验证 + 人工冒烟；为工程完整性引入是典型负收益 |
| `useEChart` 的 `deep: true` 监听 | 不做 | 当前最大数据量为热力图 8×24=192 点，开销可忽略；数据量上到万级才值得讨论 |
| Mock `requestId` 用 `Math.random()` | 不做 | requestId 的语义就是区分请求，随机完全合理；现有测试不依赖其取值 |
| Heatmap `valueRange` 强校验 | 不做 | 允许后端给视觉范围是有意设计，强校验会扩大协议拒绝范围 |
| `adaptFeeEnergyTrend` 直接加排序断言 | 不做（改为联调确认） | 见第 2 项：会构成协议语义扩张，需先确认合同 |

---

# 四、行动顺序建议

```text
当前：继续小修页面视觉
  ↓
联调前：
  - 确认 /revenue/trend 是否保证 period 升序（第 2 项）
  - 顺手完成第 3、4、5 项（均为局部小改，可与页面修改合并）
  ↓
真实 Flask 联调：
  - 跑通整条数据链
  - 核对 capabilities / manifest 缺项语义
  ↓
封版部署前：
  - 落地生产禁用 Mock 保险（第 1 项）
  ↓
答辩
```

---

# 五、结论

两轮评审的核心价值不在于列出了多少问题，而在于交叉验证后确认了两件事：

1. **V3.5 不存在架构级故障、协议漏洞或联调阻断项**——三套 verification 全部通过，两轮独立阅读均未推翻现有结构；
2. **当前主要矛盾是投入产出比，而非代码质量**——继续在协议层做完备性建设，会挤出真正需要的页面打磨与联调时间。

因此本清单刻意保持短：**2 项真实待处理 + 3 项顺手洁净，其余 6 项明确不做。**
