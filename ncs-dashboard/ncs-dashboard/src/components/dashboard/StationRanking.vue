<template>
  <DashboardPanel title="站点充电费用 TOP10" :state="state">
    <div class="ranking-list">
      <div v-for="item in state.data.items" :key="item.stationId" class="ranking-row">
        <span class="ranking-index" :class="{ top: item.rank <= 3 }">{{ item.rank }}</span>
        <span class="ranking-station" :title="item.stationName">{{ item.stationName }}</span>
        <span class="ranking-orders">{{ item.orderCount.toLocaleString('zh-CN') }} 单</span>
        <span class="ranking-energy">{{ item.totalKwh.toFixed(1) }} kWh</span>
        <strong class="ranking-fee">¥{{ item.totalFees.toFixed(2) }}</strong>
        <div class="ranking-track"><span :style="{ width: `${barWidth(item.value)}%` }"></span></div>
      </div>
    </div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'

const props = defineProps({ state: { type: Object, required: true } })
const maxValue = computed(() => Math.max(...(props.state.data?.items || []).map((item) => Number(item.value) || 0), 1))
const barWidth = (value) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return 0
  return Math.max(3, Math.min(100, numeric / maxValue.value * 100))
}
</script>
