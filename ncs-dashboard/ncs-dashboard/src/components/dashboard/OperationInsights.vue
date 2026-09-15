<template>
  <section class="panel insights-panel">
    <header class="panel-header">
      <div class="panel-title-wrap">
        <div class="panel-title">运营建议</div>
        <div class="panel-subtitle">基于当前已加载统计指标生成</div>
      </div>
      <span class="status-chip">规则分析</span>
    </header>
    <div class="insight-list">
      <article
        v-for="(item, index) in insights"
        :key="`${item.title}-${index}`"
        class="insight-item"
        :class="`insight-item--${item.level}`"
      >
        <span class="insight-item__index">{{ String(index + 1).padStart(2, '0') }}</span>
        <div class="insight-item__body">
          <strong>{{ item.title }}</strong>
          <p>{{ item.content }}</p>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
defineProps({ insights: { type: Array, required: true } })
</script>
