<template>
  <header class="dashboard-header panel">
    <div class="dashboard-brand">
      <div class="dashboard-brand__mark"><span></span><span></span><span></span></div>
      <div>
        <p>NCS · NEW ENERGY CHARGING</p>
        <h1>新能源汽车充电桩运营分析大屏</h1>
      </div>
    </div>

    <div class="header-meta">
      <template v-if="state.status === 'success'">
        <div class="header-meta__item">
          <span>业务数据日期</span>
          <strong>{{ state.data.dataDate || '—' }}</strong>
        </div>
        <div class="header-meta__item">
          <span>订单记录</span>
          <strong>{{ formatInteger(state.data.sourceRecordCount) }}</strong>
        </div>
        <div class="header-meta__item">
          <span>覆盖站点</span>
          <strong>{{ formatInteger(state.data.stationCount) }}</strong>
        </div>
        <div class="header-meta__item header-meta__wide">
          <span>数据集更新时间</span>
          <strong>{{ formatTime(state.data.updatedAt) }}</strong>
        </div>
        <span v-if="showQualityBadge" class="quality-badge" :class="qualityClass">{{ qualityText }}</span>
        <span v-if="state.data.staleness && state.data.staleness !== 'FRESH'" class="stale-badge">
          {{ state.data.staleness === 'STALE' ? '数据可能陈旧' : '新鲜度未知' }}
        </span>
        <span v-if="state.meta?.partial" class="status-chip status-chip--warning">部分数据</span>
        <span v-if="state.refreshing" class="status-chip">刷新中</span>
        <span v-if="state.refreshError" class="status-chip status-chip--warning" :title="state.refreshError">沿用上次数据</span>
      </template>
      <span v-else class="header-state">{{ stateText }}</span>

      <button class="refresh-button" :disabled="refreshing" @click="$emit('refresh')">
        <span :class="{ spinning: refreshing }">↻</span>{{ refreshing ? '刷新中' : '刷新' }}
      </button>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: { type: Object, required: true },
  refreshing: { type: Boolean, default: false }
})

defineEmits(['refresh'])

const showQualityBadge = computed(() => ['WARNING', 'FAILED'].includes(props.state.data?.qualityStatus))
const qualityText = computed(() => ({
  WARNING: '质量校验警告',
  FAILED: '质量校验失败'
}[props.state.data?.qualityStatus] || ''))
const qualityClass = computed(() => String(props.state.data?.qualityStatus || '').toLowerCase())

const stateText = computed(() => ({
  loading: '正在读取数据状态…',
  empty: '暂无数据状态',
  unavailable: '数据状态能力暂不可用',
  error: props.state.error || '数据状态读取失败'
}[props.state.status] || ''))

function formatInteger(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN') : '—'
}

function formatTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai'
  }).format(date)
}
</script>
