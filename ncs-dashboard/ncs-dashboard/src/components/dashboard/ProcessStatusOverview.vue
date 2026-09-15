<template>
  <DashboardPanel title="充电过程状态概览" subtitle="全站历史过程聚合 · 非实时设备监测" :state="state">
    <template #action><span class="status-chip">历史统计</span></template>
    <div class="process-summary">
      <div class="process-grid">
        <article v-for="metric in metrics" :key="metric.metricCode" class="process-metric" :class="metric.metricCode">
          <span>{{ label(metric) }}</span>
          <!-- Batch C.5：数字要「几何居中」，所以 strong 内不能有空白文本节点 ——
               尾随空格会被一起居中，造成约 3px 的偏移（24px 字号下）。单位已绝对定位，
               不需要任何间隔，因此 `}}` 后紧接 `<small>`，行首 `<strong>` 后紧接 `{{`。
               单位由 CSS 固定到卡片右侧（.process-metric strong small）。 -->
          <strong>{{ formatMetric(metric) }}<small>{{ unit(metric) }}</small></strong>
          <i></i>
        </article>
      </div>
    </div>
  </DashboardPanel>
</template>

<script setup>
import { computed } from 'vue'
import DashboardPanel from './DashboardPanel.vue'

const props = defineProps({ state: { type: Object, required: true } })
const metrics = computed(() => props.state.data?.metrics || [])

const label = (metric) => ({
  average_soc: '平均 SOC',
  average_current: '平均电流',
  average_voltage: '平均电压',
  average_max_temperature: '平均峰值温度'
}[metric.metricCode] || metric.displayName)

const unit = (metric) => ({ ratio: '%', A: 'A', V: 'V', celsius: '℃' }[metric.unit] || metric.unit || '')

function formatMetric(metric) {
  if (metric.value === null || metric.value === undefined) return '—'
  const value = metric.unit === 'ratio' ? metric.value * 100 : metric.value
  // ── 展示层转换：运营大屏只表达「电流大小」，不表达方向 ──
  // 后端提供的平均电流是带符号的均值（如 -32.4A，负号表示方向）。
  // 原始值在数据层完整保留 —— 适配器不修改它，本函数也不回写任何状态，
  // 这里仅对 average_current 取绝对值用于显示。
  //
  // 注意：**刻意不做全局 abs**。电压 / SOC / 温度出现负值属于数据异常，
  // 必须继续显形，否则会把上游的数据错误静默吞掉。
  // 另注：abs(mean(i)) ≠ mean(|i|)，界面上对应的是「平均值的绝对值」，
  // 与「平均电流幅值」这个说法并不等价，故指标名保持「平均电流」不变。
  const display = metric.metricCode === 'average_current' ? Math.abs(value) : value
  return Number(display).toFixed(metric.precision ?? 1)
}
</script>
