<template>
  <DashboardPanel title="充电费用与电量趋势" subtitle="左轴：费用（元） · 右轴：电量（kWh）" :state="state">
    <div ref="chartEl" class="chart"></div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { useEChart } from '../../composables/useEChart'

// compact：Batch B 仅建立 props 通道，本轮不消费（不改变 option）。
// 目的是让 Batch C 的 label 密度适配 diff 聚焦在图表逻辑本身。
const props = defineProps({
  state: { type: Object, required: true },
  compact: { type: Boolean, default: false }
})

const option = computed(() => {
  if (props.state.status !== 'success') return null
  const points = props.state.data?.points || []

  return {
    color: ['#f5a623', '#2faea0'],
    // compact：窄容器下左右轴同时存在，收窄边距并压缩 label 字号，避免绘图区被挤空。
    // Batch C2：上下边距由 38/28 收至 30/22（compact 34/26 → 28/20），回收 14px 给绘图区。
    // 原因是右栏重平衡让 Trend 面板让出了约 26px，而面板里有 40(头) + 6(padding) + 图内边距
    // 约 122px 固定成本（占原 257px 的 47%）—— 面板 -10% 会被放大成绘图区 -19%。
    // 减去 8px 上边距后 legend（top:0，12px/10.5px）下方仍有约 12px 间隔，不会相撞。
    grid: props.compact
      ? { left: 40, right: 44, top: 28, bottom: 20, containLabel: false }
      : { left: 54, right: 58, top: 30, bottom: 22, containLabel: false },
    tooltip: {
      trigger: 'axis',
      renderMode: 'richText',
      formatter: (params) => {
        const index = params?.[0]?.dataIndex ?? 0
        const point = points[index]
        return `${point.period}\n充电费用：¥${point.totalFees.toFixed(2)}\n充电量：${point.totalKwh.toFixed(2)} kWh\n订单：${point.orderCount} 单`
      }
    },
    legend: {
      top: 0,
      right: 2,
      itemGap: props.compact ? 10 : 16,
      textStyle: { color: '#6f7d90', fontSize: props.compact ? 10.5 : 12 },
      data: ['充电费用', '充电量']
    },
    xAxis: {
      type: 'category',
      data: points.map((p) => p.period),
      axisLabel: { color: '#8390a2', fontSize: 11, hideOverlap: true },
      axisLine: { lineStyle: { color: '#dfe6ef' } },
      axisTick: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        min: 0,
        splitNumber: 3,
        axisLabel: { color: '#9b8a6b', fontSize: 10.5, hideOverlap: true },
        splitLine: { lineStyle: { color: '#edf1f6' } },
        axisLine: { show: false },
        axisTick: { show: false }
      },
      {
        type: 'value',
        min: 0,
        splitNumber: 3,
        axisLabel: { color: '#6f9994', fontSize: 10.5, hideOverlap: true },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false }
      }
    ],
    series: [
      {
        name: '充电费用',
        type: 'bar',
        data: points.map((p) => p.totalFees),
        barWidth: '38%',
        itemStyle: { borderRadius: [4, 4, 0, 0] }
      },
      {
        name: '充电量',
        type: 'line',
        yAxisIndex: 1,
        smooth: 0.25,
        smoothMonotone: 'x',
        // Batch C.5：隐藏每个数据点的圆点。
        // 9 个月各画一个 symbol 会让「月趋势」被读成「离散采样点 / 曲线不连续」，
        // 而这张图要表达的是方向与波动。交互不受影响 —— 本图 tooltip trigger 为 'axis'，
        // 鼠标在任意横向位置都能读到该月的费用/电量/订单。
        // （原先的点径配置随之失效，一并删除，不留死配置。）
        showSymbol: false,
        data: points.map((p) => p.totalKwh),
        lineStyle: { width: 2.4 }
      }
    ]
  }
})

const { chartEl } = useEChart(option)
</script>
