<template>
  <DashboardPanel title="工作日 vs 周末画像" :state="state">
    <div v-if="canDrawRadar" ref="chartEl" class="chart"></div>
    <div v-else class="profile-table">
      <div class="profile-table__head"><span>指标</span><span>工作日</span><span>周末</span></div>
      <div
        v-for="(indicator, index) in state.data.indicators"
        :key="indicator.metricCode"
        class="profile-table__row"
      >
        <span>{{ indicator.displayName }}</span>
        <strong>{{ valueFor('WEEKDAY', index) }} <small>{{ unitLabel(indicator.unit) }}</small></strong>
        <strong>{{ valueFor('WEEKEND', index) }} <small>{{ unitLabel(indicator.unit) }}</small></strong>
      </div>
    </div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { useEChart } from '../../composables/useEChart.js'

const props = defineProps({ state: { type: Object, required: true } })

const canDrawRadar = computed(() =>
  props.state.status === 'success'
  && props.state.data?.normalizationAvailable === true
)

const seriesByType = (type) => props.state.data?.series?.find((item) => item.dayType === type)

function valueFor(type, index) {
  const value = seriesByType(type)?.rawValues?.[index]
  return Number.isFinite(value)
    ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
    : '—'
}

const unitLabel = (unit) => ({
  count: '',
  kWh: 'kWh',
  CNY: '元',
  hour: 'h'
}[unit] ?? unit ?? '')

function rawTooltip(series) {
  const lines = [series.displayName]
  props.state.data.indicators.forEach((indicator, index) => {
    const value = series.rawValues[index]
    const display = Number.isFinite(value)
      ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
      : '—'
    const unit = unitLabel(indicator.unit)
    lines.push(`${indicator.displayName}：${display}${unit ? ` ${unit}` : ''}`)
  })
  return lines.join('\n')
}

const option = computed(() => {
  if (!canDrawRadar.value) return null
  const data = props.state.data
  return {
    color: ['#4f86ff', '#f2a33a'],
    tooltip: {
      trigger: 'item',
      renderMode: 'richText',
      textStyle: { fontSize: 12 },
      formatter: (params) => rawTooltip(data.series[params.dataIndex])
    },
    legend: {
      bottom: 0,
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { color: '#65758a', fontSize: 12 }
    },
    radar: {
      center: ['50%', '46%'],
      radius: '67%',
      splitNumber: 4,
      indicator: data.indicators.map((item) => ({ name: item.displayName, max: 1 })),
      axisName: { color: '#5f6f84', fontSize: 12, fontWeight: 600 },
      splitLine: { lineStyle: { color: '#dce5ef' } },
      splitArea: { areaStyle: { color: ['#fbfcfe', '#f4f8fd'] } },
      axisLine: { lineStyle: { color: '#dce5ef' } }
    },
    series: [{
      type: 'radar',
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { width: 2 },
      data: data.series.map((item) => ({
        name: item.displayName,
        value: item.normalizedValues,
        areaStyle: { opacity: 0.11 }
      }))
    }]
  }
})

const { chartEl } = useEChart(option)
</script>
