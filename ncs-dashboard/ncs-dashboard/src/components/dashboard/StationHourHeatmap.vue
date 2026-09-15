<template>
  <DashboardPanel
    title="站点 × 时段热力图"
    :state="state"
    unavailable-text="站点小时粒度数据暂未接入，组件结构已保留。"
  >
    <template #action>
      <span v-if="state.status === 'success'" class="status-chip">Top {{ state.data.stations.length }}</span>
    </template>
    <div ref="chartEl" class="chart"></div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { useEChart } from '../../composables/useEChart.js'

// compact：Batch B 仅建立 props 通道，本轮不消费（不改变 option）。
// 目的是让 Batch C 的 label 密度适配 diff 聚焦在图表逻辑本身。
const props = defineProps({
  state: { type: Object, required: true },
  compact: { type: Boolean, default: false }
})

// ── Batch D-1/D-1b：热力图统一蓝色系（sequential palette）──
// 原色板是「蓝渐变 + 一个橙色 + 一个靛色」。
// 橙色在这套大屏里语义是「告警 / 重点」，而热力图中的橙只表示「高值」——语义冲突。
//
// ★ D-1b 用户看图后定稿：「清透蓝为主、钢蓝收尾」，7 档。
//   不是两套方案的简单平均，而是分段取舍：
//   低值：浅冰蓝但不近纯白（#F7FBFF 在白底上太淡，低值区显得空）；
//   中值：清透蓝，略收青色与饱和度（保留层次，不向鲜艳科技蓝偏移）；
//   高值：稳重钢蓝，不用过暗靛蓝（高峰突出但不压迫）。
//   七个色值是**连续渐变的停靠点**，不是把数据离散成七档。
//
//   层级  色值      含义
//   1    #EEF5FB   低值 —— 浅冰蓝，白底上看得见
//   2    #DCEAF7
//   3    #BCD5EC
//   4    #8DB7DD
//   5    #6098CC
//   6    #3C78B2
//   7    #285B91   峰值 —— 钢蓝，突出但不压迫
//
// 边界：**只改 inRange.color 这一个数组**。visualMax 的 90 分位策略、
// 分桶、tooltip、无观测格样式、响应式分支全部不动。
// 不抽 chartTokens.js：目前只有这一个消费方，为一个数组造抽象层不值得。
const HEATMAP_COLORS = ['#EDF4FC', '#DBE9FA', '#BBD3F3', '#91B7E8', '#6597D8', '#3E78C2', '#24579B']

function percentile(values, ratio) {
  if (!values.length) return 1
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * ratio)))
  return sorted[index]
}

const option = computed(() => {
  if (props.state.status !== 'success') return null

  const data = props.state.data
  const stationIndex = new Map(data.stations.map((station, index) => [station.stationId, index]))
  const observedValues = data.points.filter((point) => point.isObserved).map((point) => point.value)
  const visualMax = Math.max(1, percentile(observedValues, 0.90))

  const points = data.points.map((point) => ({
    value: [point.hour, stationIndex.get(point.stationId), point.value, point.isObserved],
    itemStyle: point.isObserved
      ? undefined
      // 无观测格：#f3f6fa → #eceff4。新色板最低档 #F7FBFF 接近白色，
      // 若无观测格也停在同亮度的浅蓝，会与「低值」混淆（无数据 ≠ 低负载）。
      // 略加深、偏灰，保持「空白格」与「低值蓝」的区分。
      : { color: '#eceff4', borderColor: '#ffffff', borderWidth: 1 }
  }))

  return {
    tooltip: {
      renderMode: 'richText',
      textStyle: { fontSize: 12 },
      formatter: (p) => {
        const [hour, sIndex, value, observed] = p.value || p.data?.value || []
        const station = data.stations[sIndex]
        return `${station?.stationName ?? ''}\n${hour}:00\n${observed ? `${value} ${data.unit}` : '无观测'}`
      }
    },
    // compact：窄容器下左侧 132px 站点名留白会吃掉近半宽度，收窄并把站点名截断宽度调小。
    // 仅调整绘图区几何，不改色板 / visualMax 分位策略 / 数据。
    grid: props.compact
      ? { left: 84, right: 12, top: 10, bottom: 40 }
      : { left: 132, right: 22, top: 14, bottom: 46 },
    xAxis: {
      type: 'category',
      data: data.hours.map((hour) => `${hour}`),
      axisLabel: { color: '#748399', interval: props.compact ? 3 : 2, fontSize: props.compact ? 10 : 12 },
      axisLine: { lineStyle: { color: '#dfe6ef' } },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'category',
      data: data.stations.map((station) => station.stationName),
      axisLabel: {
        color: '#5f6f84',
        width: props.compact ? 72 : 116,
        overflow: 'truncate',
        fontSize: props.compact ? 10 : 11.5
      },
      axisLine: { show: false },
      axisTick: { show: false }
    },
    visualMap: {
      type: 'continuous',
      dimension: 2,
      min: 0,
      max: visualMax,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemWidth: 18,
      itemHeight: 160,
      precision: 0,
      inRange: {
        color: HEATMAP_COLORS
      },
      text: ['高', '低'],
      textGap: 7,
      textStyle: { color: '#6f7d90', fontSize: 11 }
    },
    series: [{
      type: 'heatmap',
      data: points,
      encode: { x: 0, y: 1, value: 2 },
      itemStyle: { borderColor: 'rgba(255, 255, 255, 0.5)', borderWidth: 1 },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(30,60,90,.22)' } }
    }]
  }
})

const { chartEl } = useEChart(option)
</script>
