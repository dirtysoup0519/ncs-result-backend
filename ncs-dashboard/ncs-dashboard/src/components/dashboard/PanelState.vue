<template>
  <div class="panel-state" :class="`panel-state--${status}`">
    <div v-if="status === 'loading'" class="panel-state__loading">
      <span class="loading-dot"></span>
      <span>正在加载数据</span>
    </div>
    <template v-else>
      <div class="panel-state__icon">{{ icon }}</div>
      <div class="panel-state__title">{{ title }}</div>
      <div class="panel-state__detail">{{ detail }}</div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
  error: { type: String, default: '' },
  unavailableText: { type: String, default: '当前数据能力暂不可用，等待上游接入。' }
})

const icon = computed(() => ({ empty: '—', unavailable: '◇', error: '!' }[props.status] || '·'))
const title = computed(() => ({
  empty: '暂无数据',
  unavailable: '能力暂不可用',
  error: '组件加载失败'
}[props.status] || ''))
const detail = computed(() => {
  if (props.status === 'error') return props.error || '请求或协议处理失败。'
  if (props.status === 'unavailable') return props.unavailableText
  return '请求成功，但当前筛选范围内没有业务数据。'
})
</script>
