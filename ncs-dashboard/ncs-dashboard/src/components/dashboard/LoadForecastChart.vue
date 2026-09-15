<template>
  <DashboardPanel
    title="充电负荷趋势与 AI 预测"
    subtitle="左轴：历史订单（单） · 右轴：负荷（kWh）"
    :state="state"
    unavailable-text="预测目标与模型口径尚未确认，当前暂不展示预测曲线。"
  >
    <div ref="chartEl" class="chart chart--hero"></div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { useEChart } from '../../composables/useEChart.js'
import { interpolateSeries } from '../../utils/interpolation.js'

// compact：Batch B 建立 props 通道。本轮的消费范围严格限定为「label 密度」，
// 不触碰任何业务数值 / 插值 / 置信区间逻辑（那些属 Batch C）。
// 触发原因：窄容器下 24 个整点 label 会相互重叠，属布局引入的可读性缺陷。
const props = defineProps({
  state: { type: Object, required: true },
  compact: { type: Boolean, default: false }
})

/** 每段插值采样数：24 小时共 23 段，约 185 点，对 ECharts 无压力 */
const SAMPLES_PER_SEGMENT = 8

const option = computed(() => {
  if (props.state.status !== 'success') return null

  const data = props.state.data
  const hours = Array.from({ length: 24 }, (_, index) => index)
  const actualMap = new Map((data.actual || []).map((point) => [point.hour, point]))
  const forecastMap = new Map((data.forecast || []).map((point) => [point.hour, point]))
  const hasInterval = data.interval?.available === true

  // ── 原始业务点（整点采样，绝不修改，供散点层与 Tooltip 使用） ──
  const actualRaw = hours.map((hour) => ({ x: hour, y: actualMap.get(hour)?.chargingEnergy ?? null }))
  const forecastRaw = hours.map((hour) => ({ x: hour, y: forecastMap.get(hour)?.predictedEnergy ?? null }))
  const lowerRaw = hours.map((hour) => ({ x: hour, y: forecastMap.get(hour)?.lowerBound ?? null }))
  const upperRaw = hours.map((hour) => ({ x: hour, y: forecastMap.get(hour)?.upperBound ?? null }))

  // ── 硬约束 1：历史与实际预测分开插值，不跨越「实际 → AI预测」语义边界 ──
  const actualCurve = interpolateSeries(actualRaw, { samplesPerSegment: SAMPLES_PER_SEGMENT }).displayPoints
  const forecastCurve = interpolateSeries(forecastRaw, { samplesPerSegment: SAMPLES_PER_SEGMENT }).displayPoints

  // ── 硬约束 2：置信区间用「预测值 + 两侧宽度」结构，而非三条独立 PCHIP ──
  // 先算原始整点的宽度，再分别插值，最后重构 —— 包围关系由数学结构保证
  const lowerGapRaw = lowerRaw.map((point, index) => {
    const forecastPoint = forecastRaw[index]
    if (point.y == null || forecastPoint.y == null) return { x: point.x, y: null }
    return { x: point.x, y: forecastPoint.y - point.y }
  })
  const upperGapRaw = upperRaw.map((point, index) => {
    const forecastPoint = forecastRaw[index]
    if (point.y == null || forecastPoint.y == null) return { x: point.x, y: null }
    return { x: point.x, y: point.y - forecastPoint.y }
  })

  const lowerGapCurve = interpolateSeries(lowerGapRaw, { samplesPerSegment: SAMPLES_PER_SEGMENT }).displayPoints
  const upperGapCurve = interpolateSeries(upperGapRaw, { samplesPerSegment: SAMPLES_PER_SEGMENT }).displayPoints

  const lowerCurve = forecastCurve.map((point, index) => ({
    x: point.x,
    y: point.y - Math.max(0, lowerGapCurve[index]?.y ?? 0)
  }))
  const upperCurve = forecastCurve.map((point, index) => ({
    x: point.x,
    y: point.y + Math.max(0, upperGapCurve[index]?.y ?? 0)
  }))

  // ── 置信区间填充带：直接构造闭合多边形 ──
  // 不再使用 stack 间接实现：stack + areaStyle 的组合在此实现下渲染结果不可控
  // （曾被压成贴底窄条）。custom series 直接表达「填充 lower 与 upper 之间」，
  // 语义明确、层级可控，且不受 ECharts 面积基线语义影响。
  // 上界正向 + 下界反向 = 闭合环，与数据层的 gap 结构配合，天然满足 lower ≤ upper。
  const bandPolygon = hasInterval
    ? [
        ...upperCurve.map((point) => [point.x, point.y]),
        ...lowerCurve.slice().reverse().map((point) => [point.x, point.y])
      ]
    : []

  const series = [
    {
      name: '历史订单',
      type: 'bar',
      yAxisIndex: 0,
      barWidth: '34%',
      data: actualRaw.map((point) =>
        point.y == null ? null : [point.x, actualMap.get(point.x)?.orderCount ?? null]
      ),
      itemStyle: {
        color: 'rgba(91, 145, 240, .24)',
        borderColor: 'rgba(91, 145, 240, .16)',
        borderWidth: 1,
        borderRadius: [3, 3, 0, 0]
      },
      tooltip: { valueFormatter: (value) => (value == null ? '—' : `${value[1] ?? '—'} 单`) }
    },
    {
      name: '历史负荷',
      type: 'line',
      yAxisIndex: 1,
      smooth: false,
      showSymbol: false,
      symbol: 'none',
      silent: true,
      tooltip: { show: false },
      data: actualCurve.map((point) => [point.x, point.y]),
      lineStyle: { width: 2.4, color: '#3d7fd3', cap: 'round', join: 'round' },
      itemStyle: { color: '#3d7fd3' },
      areaStyle: { opacity: 0.022, color: '#3d7fd3' },
      z: 3,
      markLine: {
        symbol: 'none',
        label: {
          formatter: 'AI预测',
          color: '#7c8ba1',
          fontSize: 11,
          fontWeight: 500,
          rotate: 0,
          position: 'insideEndTop',
          padding: [2, 5],
          backgroundColor: 'rgba(244, 246, 250, .92)',
          borderRadius: 4
        },
        lineStyle: { color: '#ccd4e0', type: [3, 3], width: 1 },
        data: [{ xAxis: data.cutoffHour }]
      }
    },
    {
      name: '历史负荷（真实节点）',
      type: 'scatter',
      yAxisIndex: 1,
      symbolSize: 7,
      data: actualRaw.filter((point) => point.y != null).map((point) => [point.x, point.y]),
      // 默认完全隐形：平时只有干净的平滑线，不留「串珠」感
      itemStyle: { color: '#3d7fd3', borderColor: '#ffffff', borderWidth: 1.5, opacity: 0 },
      // 命中区不受 opacity 影响，因此悬停仍可精确捕捉真实采样点
      emphasis: { scale: 1.5, itemStyle: { opacity: 1, borderWidth: 2 } },
      tooltip: { valueFormatter: (value) => (value == null ? '—' : `${value[1]} kWh`) },
      z: 6
    }
  ]

  if (hasInterval) {
    series.push({
      name: '置信区间',
      type: 'custom',
      yAxisIndex: 1,
      silent: true,
      tooltip: { show: false },
      renderItem: (params, api) => {
        const points = bandPolygon.map(([x, y]) => [api.coord([x, y])[0], api.coord([x, y])[1]])
        return {
          type: 'polygon',
          shape: { points },
          style: {
            fill: 'rgba(123, 104, 238, .16)',
            stroke: 'rgba(123, 104, 238, .28)',
            lineWidth: 1
          }
        }
      },
      data: [0],
      z: 1
    })
  }

  series.push(
    {
      name: 'AI预测负荷',
      type: 'line',
      yAxisIndex: 1,
      smooth: false,
      showSymbol: false,
      symbol: 'none',
      silent: true,
      tooltip: { show: false },
      data: forecastCurve.map((point) => [point.x, point.y]),
      // 虚线段短、空隙短、整体更密 —— 避免「——  ——  ——」的稀疏感
      // ECharts 的 'dashed' 等价于 [5,5]，此处显式给更密的 [3,2]
      lineStyle: { width: 2.2, type: [3, 2], color: '#7b68ee', cap: 'round', join: 'round' },
      itemStyle: { color: '#7b68ee' },
      z: 5
    },
    {
      name: 'AI预测负荷（真实节点）',
      type: 'scatter',
      yAxisIndex: 1,
      symbolSize: 7,
      data: forecastRaw.filter((point) => point.y != null).map((point) => [point.x, point.y]),
      // 与历史节点一致：默认隐形，悬停才显形
      itemStyle: { color: '#7b68ee', borderColor: '#ffffff', borderWidth: 1.5, opacity: 0 },
      emphasis: { scale: 1.5, itemStyle: { opacity: 1, borderWidth: 2 } },
      tooltip: { valueFormatter: (value) => (value == null ? '—' : `${value[1]} kWh`) },
      z: 7
    }
  )

  return {
    grid: { left: 58, right: 60, top: 48, bottom: 36 },
    tooltip: { trigger: 'item', renderMode: 'richText' },
    legend: {
      top: -2,
      right: 2,
      itemGap: props.compact ? 9 : 14,
      data: ['历史订单', '历史负荷', 'AI预测负荷'],
      textStyle: { color: '#6f7d90', fontSize: props.compact ? 10.5 : 12 }
    },
    xAxis: {
      type: 'value',
      min: 0,
      max: 23,
      // 窄容器下 24 个整点标签必然重叠。compact 时改为 ECharts 自动抽稀
      // （保留全部落点，只减少显示标签），坐标轴语义与曲线数据完全不变。
      ...(props.compact ? { interval: 'auto' } : { interval: 1 }),
      axisLabel: {
        color: '#8390a2',
        fontSize: props.compact ? 10 : 12,
        hideOverlap: true,
        formatter: (value) => `${Math.round(value)}:00`
      },
      axisLine: { lineStyle: { color: '#dfe6ef' } },
      axisTick: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        min: 0,
        splitNumber: 5,
        splitLine: { lineStyle: { color: '#edf1f6' } },
        axisLabel: { color: '#8390a2', fontSize: 12 },
        axisLine: { show: false },
        axisTick: { show: false }
      },
      {
        type: 'value',
        min: 0,
        splitNumber: 5,
        splitLine: { show: false },
        axisLabel: { color: '#8390a2', fontSize: 12 },
        axisLine: { show: false },
        axisTick: { show: false }
      }
    ],
    series
  }
})

const { chartEl } = useEChart(option)
</script>
