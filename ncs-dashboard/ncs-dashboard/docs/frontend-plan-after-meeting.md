# NCS Dashboard V3.5 · 会议后前端修改计划

> 基于 9/14 项目进度会的原始决议，结合对当前 V3.5 代码的实测核对。
> 每项包含：会议原始要求 / 现状核对 / 实现思路 / 风险与边界。

---

## 零、对两个输入材料的处理原则

**会议记录中「元宝会议助手」的点评段落不作为验收依据。** 例如「暴露出前端过度依赖黑盒工具」「这招空间置换巧妙化解」「直接把交付压力拉满」等，是会议助手的自动生成评论，不是组长的正式评价。

本计划只采用会议中形成的**事实性决议**：
- 组长不满意当前 ECharts 自带平滑，要求前端自行实现曲线算法；
- 要求响应式；
- Top10 改为可滚动卡片以释放空间、放大下方图表；
- 增加超链接/弹窗查看详情；
- 热力图色系统一为蓝色。

**ChatGPT 分析中需要修正的一点**：它建议曲线算法用「单调三次插值（PCHIP）」。这个方向是对的，但它在描述「卷积」时把会议原话理解得过于具体。会议原话是组长说「采用**卷积**等算法重构」。实际实现上 **PCHIP 比卷积更适合画曲线**（卷积会改变峰值、属于降噪），因此建议按 PCHIP 落地，同时在向组长汇报时说明「采样点插值 + 可选移动平均」的组合，与会议提法对齐。

**ChatGPT 分析中一项重要提醒应当保留**：模型训练数据集的平滑属于数据侧（李泽宇/盛诗闵），**不是前端任务**，两者不要混为一谈。

---

## 一、任务优先级（会议明确要求）

### P0 · 充电负荷曲线插值算法

**会议原始要求**

> 前端原依赖视图语言平滑程度参数生成曲线，需自行编写插值或卷积算法以确保视觉效果美观。

**现状核对**

`src/components/dashboard/LoadForecastChart.vue` 第 54、119 行：

```js
smooth: 0.62,      // 历史负荷
smooth: 0.48,      // AI 预测负荷
```

两条曲线确实完全依赖 ECharts 内置 `smooth` 参数，没有前端自己的算法。组长的判断准确。

**实现思路**

分三层，保持业务数据与显示数据分离：

```text
原始业务点（hour → kWh，24 个点）
        ↓
新增 src/utils/interpolate.js：单调三次插值 PCHIP
        ↓
生成加密显示序列（每小时 10~20 个点，约 240~480 点）
        ↓
ECharts 以 smooth:false 直接连线（线本身已平滑）
```

核心约束（**必须遵守**）：

1. **原始业务点绝不被篡改。** 插值只生成「显示用的额外点」，`state.data.actual[].chargingEnergy` 的值不参与任何修改。
2. **Tooltip 仍显示原始小时数据。** 因为加密后 x 轴变成细粒度，需要把原始点单独作为一个高优先级散点序列或使用 `axisPointer` 吸附回整点。推荐做法：hist 折线用加密序列，但 **Tooltip 保留按 `hour` 索引原始 map 取值**，即 tooltip formatter 里仍然 `actualMap.get(round(hour))`。
3. **单调性保护**：在峰值和谷值处不能过冲（这是选 PCHIP 而非普通三次样条的原因）。
4. **null 处理**：`actual` 序列中 hour 0～cutoff 是连续的；但 `connectNulls:false` 语义要保留——插值只在有值的相邻点之间进行，不跨越空档。

建议文件：`src/utils/interpolate.js`，导出：

```js
export function monotoneCubicPath(points, samplesPerSegment = 16)
```

`points` 形如 `[{ x: 0, y: 123.4 }, ...]`，返回 `[{ x: 0.0625, y: ... }, ...]`。

**风险与边界**

- 插值算法是纯函数，**不涉及 API/Adapter 合同**，可以独立单测；
- `verify-adapters.mjs` 不受影响（不碰 Adapter）；
- 建议同步在 `scripts/` 加一个 `verify-interpolate.mjs`，断言：返回值穿过原始点、区间单调性保持、无 NaN。

---

### P1 · 响应式布局

**会议原始要求**

> 当前界面尺寸写死，需调整为支持全屏及缩小缩放的响应式布局。

**现状核对**

真正的阻塞点在 `src/styles/global.css` 第 22 行：

```css
html, body, #app { margin: 0; width: 100%; min-width: 1280px; min-height: 720px; }
```

`min-width: 1280px` 意味着**窗口小于 1280px 时直接出现横向滚动条，内容不缩放**，这正是「尺寸写死」的根源。`dashboard.css` 已有 `@media (max-width: 1500px)` 一档，证明作者已开始做适配，但只做了「改变字号与列宽」，没做「整体缩放」。

**实现思路**

推荐**等比缩放方案**，而非重写为传统响应式网站：

```text
设计基准：1920 × 1080
  ↓
CSS transform: scale(k)  其中 k = min(vw/1920, vh/1080)
  ↓
外层容器固定 1920×1080，transformed 居中
```

优点：所有现有 px 尺寸、grid 比例、图表布局**全部不用改**，一次性解决 1600×900 / 1366×768 / 全屏切换。

具体做法：

1. 新增一个缩放容器（在 `App.vue` 或 `Dashboard.vue` 外层）：
   ```js
   // composables/useViewportScale.js
   const scale = Math.min(innerWidth / 1920, innerHeight / 1080)
   ```
   设置 `transform: scale(k)` + `transform-origin: center center`，外层 `overflow:hidden`。
2. 移除 `global.css` 的 `min-width: 1280px`（这是缩放方案的前提；保留它会导致小窗口仍然横向滚动）。
3. **保留** `@media (max-width:1500px)` 一档作为兜底——等比缩放后其实不再需要它，但保留无害。
4. `useEChart` 已监听 `ResizeObserver`，缩放时容器尺寸变化会触发图表 resize，**无需额外处理**。这是现有架构的红利。

**备选方案（不推荐但可谈）**

纯 CSS `clamp()` + `vw/vh` 字体流式方案。改动面大、图表仍会因容器变化而重排，收益不如等比缩放。

**风险与边界**

- 明确**不追求手机端**，1366×768 不重叠不错位即可；
- 全屏切换时 `resize` 事件要触发重新计算 `scale`，建议监听 `window.resize`；
- 投影/答辩环境如果是超宽屏（21:9），等比缩放会左右留白——这是可接受的，比拉伸变形好。

---

### P1 · Top10 可滚动 + 释放右栏空间

**会议原始要求**

> Top10 列表改为可滚动的小卡片，柱状折线图适当放大。

**现状核对**

`dashboard.css` 第 113-119 行，`.ranking-list` 用：

```css
grid-template-rows: repeat(10, minmax(0, 1fr));
```

**10 行全部硬塞进一屏**，导致每行被压到不足 17px（第 124 行 `grid-template-rows: minmax(17px, 1fr) 2px`），这就是之前一直在压缩字号/行距的根源。组长的判断同样准确。

右栏当前是四段式（`dashboard.css` 第 85 行）：

```css
.dashboard-column--right { grid-template-rows: 1.45fr 1.10fr .85fr .74fr; }
```

Top10 占了最大比重，但视觉价值最低（10 行小字）。

**实现思路**

```css
.ranking-list {
  height: 100%;
  overflow-y: auto;                 /* 关键：内部滚动 */
  display: flex; flex-direction: column;
  gap: 4px;
}
.ranking-row { flex: 0 0 auto; min-height: 30px; }  /* 固定行高，不再压缩 */
```

再调整右栏比例，把省下的高度给趋势图：

```css
.dashboard-column--right { grid-template-rows: 1.02fr 1.32fr .82fr .68fr; }
/*                                  ↑Top10↓  ↑趋势图↑ */
```

默认可见约 5～6 行，剩余滚动查看。

**细节要求**

- 滚动条需美化（`::-webkit-scrollbar`），否则默认滚动条在大屏上很突兀；
- 滚动区域需 `overscroll-behavior: contain`，避免滚到底后带动整页；
- 行高从 17px 提到 ~30px 后，排名徽标、站点名、金额的字号可以**恢复**到更舒展的值（此前是被迫压缩的）。

**风险与边界**

- 只改 CSS + 极少模板结构，**不动 `StationRanking.vue` 的数据逻辑**；
- `maxValue` 与 `barWidth` 计算逻辑保持不变（第 21-26 行）。

---

### P2 · 详情交互（超链接/弹窗）

**会议原始要求**

> 界面设计需与大屏拉开差异，避免照搬影响打分；增加超链接跳转查看详情功能。

**现状核对**

当前 Top10 每行是纯展示，无任何点击交互。整个项目没有 Modal 组件，也没有路由（`package.json` 无 `vue-router`）。

**实现思路**

**不建议引入 vue-router**——为一个详情弹窗增加路由依赖，属于不必要的架构扩张，且会与「单页大屏」定位冲突。

推荐：**纯组件 Modal，无路由**。

```text
src/components/dashboard/StationDetailModal.vue
```

- 在 `StationRanking.vue` 行上绑定 `@click`；
- 点击后 `emit('select', item)` → 父级或组件内 `ref` 控制 Modal 显隐；
- Modal 内容：站点名、排名、订单量、充电量、充电费用；
- 可选：一个 24h 分布小图（复用 `useEChart`）；
- 关闭方式：点遮罩、按 ESC、点关闭按钮。

**是否需要新接口**

**不需要。** 当前 `ranking.items` 已包含 `stationId / stationName / rank / orderCount / totalFees / totalKwh / value`，足够填充详情卡主体。

> ⚠️ 若要做「24h 分布小图」，则需要新增按站点查询的接口（当前 `stationHourHeatmap` 是聚合的 Top-N，不是单站点）。**建议第一版不做 24h 小图**，用现有字段即可，避免为一个装饰性图表引入新的接口依赖和联调风险。

**风险与边界**

- Modal 的 `z-index` 要高于 `.dashboard-global-warning`（当前 20）与 `.kpi-strip__notices`（当前 3）；
- Modal 内图表需在关闭时 `dispose`（复用 `useEChart` 的 `onBeforeUnmount` 即可，注意 Modal 用 `v-if` 控制以触发正确的生命周期）；
- 这是**本次会议唯一的「新增功能」**，其余四项都是改造，因此建议放在最后做，避免挤占联调时间。

---

### P2 · 热力图统一蓝色

**会议原始要求**

> 热力图色系统一替换为蓝色以提升视觉观感。

**现状核对**

`StationHourHeatmap.vue` 第 81 行：

```js
color: ['#edf5ff', '#cbdcff', '#91b8ff', '#5a8ff0', '#686adf', '#f1a33b']
```

**前 5 个已经是蓝色系，第 6 个 `#f1a33b` 是橙色高亮**——这正是会议要改掉的。改动量极小。

**实现思路**

```js
color: ['#edf5ff', '#cbdcff', '#91b8ff', '#5a8ff0', '#4169d8', '#28409b']
```

纯蓝渐变（极浅蓝 → 深蓝 → 靛蓝）。可保留末端一个略深的靛蓝以拉开高档位区分度，但不使用任何暖色。

**注意**：`visualMax` 当前取 90 分位数（第 34 行 `percentile(observedValues, 0.90)`），这是刻意的压制高值策略，**本次不要动**——只改色板。

---

## 二、建议的落地顺序

```text
1. 曲线插值算法（P0）
   - 新增 utils/interpolate.js + 单测
   - 改 LoadForecastChart.vue 数据源
   - 影响面：单一组件，可独立验证
        ↓
2. 响应式等比缩放（P1）
   - 新增 useViewportScale.js
   - 改 global.css 去掉 min-width
   - 影响面：全局，但机制集中
        ↓
3. Top10 滚动 + 右栏比例（P1）
   - 纯 CSS + 少量模板
        ↓
4. 热力图蓝色（P2）
   - 一行色板
        ↓
5. 详情 Modal（P2）
   - 新增组件，最后做
```

**为什么插值排第一**：它是会上唯一点名的技术项、技术含量最高、影响面最小（单组件）、最适合独立完成并单独讲解。先做完它，答辩时有一个能讲清「我实现了什么算法」的亮点。

---

## 三、明确不受影响的既有资产

以下全部**无需改动**，是本轮改造的重要前提：

| 资产 | 原因 |
|---|---|
| API 合同 / 10 个 DTO Adapter | 本次无接口结构变化 |
| `verify-contract` / `verify-adapters` | 不碰 Adapter 与 Mock |
| 6 态状态机 / `useDashboard.js` 编排 | 与视觉层解耦 |
| `useEChart` 生命周期 | 缩放方案反而依赖它的 ResizeObserver |
| Mock 数据与 DEMO fixture | 无需为视觉改造调整 |
| 三栏 grid 框架 | 等比缩放使其免于重写 |

---

## 四、关于会议中「待办」归属的说明

会议待办里前端只列了曹睿一项：

> 将前端界面调整为响应式布局，重写曲线绘制算法（采用插值或卷积），统一热力图颜色，并补充超链接跳转功能。

对照本计划，四项全部覆盖。**会议待办未单独提及 Top10 滚动**（这是会上口头讨论形成的方案），但它已被组长明确认可，且属于达成「放大下方图表」目标的手段，建议一并做。

其余待办（Python 定时刷新、Record Time 清洗、Shell 自动化、ADS→MySQL、模型数据集平滑、权重推理流程）**均为数据侧/后端/模型侧任务，与本前端工程无关**。

---

## 五、需要向上游确认的两件事

1. **AI 预测接口的真实输出形态。** 会议明确由盛诗闵跑通模型、输出「时间+负载」JSON，再经后端 `/predictions/load` 给前端。当前 Adapter 已按冻结合同实现（`availability / actual / forecast / interval`），**在真实数据接入前无需改动**；但接入时需要确认：模型输出的 JSON 是否能映射到现有 `actual[].chargingEnergy` 与 `forecast[].predictedEnergy` 结构。若不匹配，需要后端做一次映射，而不是前端改 Adapter。

2. **曲线"卷积"表述的对齐。** 组长原话是「卷积等算法」。前端实际会采用 PCHIP 插值（更适合画曲线）。建议在下次汇报时主动说明选择理由，避免被认为「没按会上的要求做」。这是沟通问题，不是技术问题。

---

## 六、结论

会议对前端提出了 5 项实质要求，**没有一项需要推翻现有架构**：

- 响应式 → CSS 缩放机制；
- 曲线算法 → 新增一个纯函数工具 + 改一个组件的数据源；
- Top10 滚动 → CSS；
- 热力图蓝色 → 一行色板；
- 详情交互 → 新增一个无路由 Modal 组件。

API、Adapter、状态机、Mock、页面框架**全部保留**。因此这是**在 V3.5 基线上的继续演进，而非重做前端**。

按 ChatGPT 的估计，会议后前端完成度从 85~90% 下调到 75~80%——**这个下调是合理的**，因为验收标准提高了，而不是已做的工作失效了。
