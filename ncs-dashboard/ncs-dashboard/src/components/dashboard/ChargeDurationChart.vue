<template>
  <DashboardPanel title="充电时长分布" :state="state">
    <div ref="chartEl" class="chart"></div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { useEChart } from '../../composables/useEChart'

const props = defineProps({ state: { type: Object, required: true } })

const option = computed(() => {
  if (props.state.status !== 'success') return null
  const items = props.state.data?.items || []
  return {
    grid: { left: 44, right: 16, top: 20, bottom: 34 },
    tooltip: {
      trigger: 'axis',
      renderMode: 'richText',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const index = params?.[0]?.dataIndex ?? 0
        const item = items[index]
        return `${item.label}\n订单：${item.orderCount.toLocaleString('zh-CN')} 单\n占比：${item.percent?.toFixed(1) ?? '—'}%`
      }
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.label),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#dfe6ef' } },
      // Batch C3：x 轴标签 13 → 12。13 是本屏唯一越过常规上限（12）的字号，
      // 属于「去异常值」而非压缩密度 —— 与 yAxis 的 12 拉平，不影响可读性。
      axisLabel: { color: '#7a8798', fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#edf1f6' } },
      axisLabel: { color: '#93a0b1', fontSize: 12 }
    },
    series: [{
      type: 'bar',
      barWidth: '46%',
      data: items.map((item) => item.orderCount),
      itemStyle: { color: '#4f86ff', borderRadius: [5, 5, 0, 0] },
      label: {
        show: true,
        position: 'top',
        color: '#6f7d90',
        fontSize: 12,
        formatter: ({ dataIndex }) => `${items[dataIndex].percent?.toFixed(0) ?? 0}%`
      }
    }]
  }
})

const { chartEl } = useEChart(option)
</script>
