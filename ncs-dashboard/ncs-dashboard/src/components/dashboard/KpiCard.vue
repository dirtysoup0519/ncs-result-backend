<template>
  <article class="kpi-card panel" :class="`kpi-card--${tone}`">
    <div class="kpi-icon">{{ icon }}</div>
    <div class="kpi-card__content">
      <span class="kpi-card__label">{{ item.displayName }}</span>
      <strong class="kpi-card__value">{{ formattedValue }} <small>{{ displayUnit }}</small></strong>
      <em>{{ note }}</em>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { formatNumber } from '../../adapters/decimal.js'

const props = defineProps({
  item: { type: Object, required: true },
  tone: { type: String, default: 'blue' }
})

const formattedValue = computed(() => formatNumber(props.item.value, props.item.precision ?? 0))
const displayUnit = computed(() => ({
  total_order_count: '单',
  total_charging_energy: 'kWh',
  total_charging_fee: '元',
  total_user_count: '人',
  active_station_count: '个'
}[props.item.metricCode] || props.item.unit || ''))
const icon = computed(() => ({
  total_order_count: '单',
  total_charging_energy: '⚡',
  total_charging_fee: '¥',
  total_user_count: '人',
  active_station_count: '站'
}[props.item.metricCode] || '•'))
const note = computed(() => ({
  total_order_count: '当前统计范围内累计订单',
  total_charging_energy: '基础单位 kWh',
  total_charging_fee: '统计范围内累计充电费用',
  total_user_count: '统计范围内去重用户',
  active_station_count: '至少产生一笔订单'
}[props.item.metricCode] || ''))
</script>
