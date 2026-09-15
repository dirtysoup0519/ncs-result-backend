<template>
  <section class="panel dashboard-panel">
    <header class="panel-header" :class="{ 'panel-header--compact': !subtitle }">
      <div class="panel-title-wrap">
        <div class="panel-title">{{ title }}</div>
        <div v-if="subtitle" class="panel-subtitle">{{ subtitle }}</div>
      </div>
      <div class="panel-action">
        <span v-if="state.refreshing" class="status-chip">刷新中</span>
        <span v-if="state.refreshError" class="status-chip status-chip--warning" :title="state.refreshError">沿用上次数据</span>
        <span v-if="state.meta?.partial" class="status-chip status-chip--warning">部分数据</span>
        <slot name="action" />
      </div>
    </header>
    <div class="panel-body">
      <PanelState
        v-if="state.status !== 'success'"
        :status="state.status"
        :error="state.error"
        :unavailable-text="unavailableText"
      />
      <slot v-else />
    </div>
  </section>
</template>

<script setup>
import PanelState from './PanelState.vue'

defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  state: { type: Object, required: true },
  unavailableText: { type: String, default: '当前数据能力暂不可用，等待上游接入。' }
})
</script>
