<template>
  <div
    class="dashboard-viewport"
    :data-layout="mode"
    :data-tier="tier"
  >
    <div
      class="dashboard-canvas"
      :style="canvasStyle"
    >
      <slot />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  mode: { type: String, default: 'scale' },
  tier: { type: String, default: 'default' },
  scale: { type: Number, default: 1 }
})

/**
 * Scale 模式：画布固定 1920×1080，用纯 transform: scale 缩放。
 *
 * ⚠️ transform 不会改变 layout box —— 因此 .dashboard-canvas 的
 *    布局尺寸始终是 1920×1080，ResizeObserver 不会被触发，ECharts 全程
 *    按 1920×1080 渲染，浏览器统一缩放。这是期望行为，不是 bug，
 *    不要为此去改 useEChart.js 或手动调 chart.resize()。
 *
 * Compact / Reflow 模式：容器尺寸真实变化（100% 宽、高度自适应），
 * Canvas 不参与变换，由 ResizeObserver 驱动 chart.resize() 正常工作。
 *
 * data-tier 只对 compact 有意义（'stack' / 'columns'），用于在其内部
 * 按「纵向是否有富余」再分两档形态；其他模式恒为 'default'。
 */
const canvasStyle = computed(() => {
  if (props.mode !== 'scale') return null
  return {
    width: '1920px',
    height: '1080px',
    transform: `scale(${props.scale})`
  }
})
</script>
