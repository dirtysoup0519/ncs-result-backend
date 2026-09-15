<template>
  <DashboardPanel title="订单平台分布" :state="state">
    <div class="donut-wrapper">
      <div ref="chartEl" class="chart"></div>
      <!-- Batch D-2 Step1：中心 KPI 从 ECharts graphic 改为 HTML 覆盖层（冻结方案 6.2）。
           graphic 用百分比 top（32%/42%）+ 绝对字号（11/21px），两者单位不一致，
           块中心相对环心的偏移 = −0.06H + 10.5，随图表高度线性漂移
           （实测 1715×1401 为 −7.6px）。HTML 用 transform 按自身高度折算 ⇒ 恒居中。
           top 绑定 CENTER.y —— 与 ECharts option 的 series.center 共用同一常量，
           否则「改了 center 忘了改覆盖层」会让环与文字各自漂移。 -->
      <div class="donut-center" :style="{ top: CENTER.y }">
        <!-- Batch D-2 Step2：数字在上、标签在下 —— KPI 惯例（数字是信息，标签是解释），
             与 Process 指标卡、KPI 条的「数值为主视觉」层级一致。 -->
        <strong class="donut-center__value">{{ totalText }}</strong>
        <span class="donut-center__label">总订单</span>
      </div>
    </div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { useEChart } from '../../composables/useEChart.js'

const props = defineProps({ state: { type: Object, required: true } })

// Batch D-2：圆环中心的**唯一真源**。ECharts option 的 series.center
// 与 HTML 覆盖层的 top 共用这一常量 —— 只写一处，防止单独改一边造成漂移。
// y 取 43%（不是 50%）：要给 bottom:0 的图例让位。
const CENTER = { x: '50%', y: '43%' }

const totalText = computed(() => props.state.data?.totalOrderCount?.toLocaleString('zh-CN') ?? '—')

const option = computed(() => {
  if (props.state.status !== 'success') return null
  const items = props.state.data?.items || []
  const totalOrderCount = props.state.data?.totalOrderCount

  return {
    color: ['#4f86ff', '#35b7a4', '#f5a623', '#9aa7b8'],
    tooltip: {
      trigger: 'item',
      renderMode: 'richText',
      formatter: (p) => {
        const item = items[p.dataIndex]
        return `${item.displayName}\n订单：${item.orderCount.toLocaleString('zh-CN')} 单\n占比：${item.orderPercent?.toFixed(1) ?? '—'}%`
      }
    },
    legend: {
      bottom: 0,
      itemWidth: 9,
      itemHeight: 9,
      itemGap: 14,
      textStyle: { color: '#6f7d90', fontSize: 12 }
      // Batch C3：图例只显示平台名。原先的 formatter 会给图例追加百分比，
      // 而环外标签里已经有同一个百分比（如 iOS 65.8% 出现两次）—— 同一信息重复。
      // 删除 formatter 后图例直接显示 data.name；tooltip 里的占比信息不受影响。
    },
    series: [{
      type: 'pie',
      radius: ['57%', '74%'],
      center: [CENTER.x, CENTER.y],
      avoidLabelOverlap: true,
      label: {
        show: true,
        formatter: (p) => `${items[p.dataIndex]?.orderPercent?.toFixed(1) ?? '—'}%`,
        color: '#66758a',
        fontSize: 11
      },
      labelLine: { length: 6, length2: 6 },
      emphasis: { scaleSize: 5 },
      data: items.map((item) => ({ name: item.displayName, value: item.orderCount }))
    }]
  }
})

const { chartEl } = useEChart(option)
</script>
