import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

export function useEChart(optionSource) {
  const chartEl = ref(null)
  let chart = null
  let resizeObserver = null

  const resolveOption = () => typeof optionSource === 'function' ? optionSource() : optionSource?.value

  function ensureResizeObserver() {
    if (!resizeObserver && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => chart?.resize())
    }
    return resizeObserver
  }

  function disposeChart() {
    if (chart) {
      chart.dispose()
      chart = null
    }
  }

  async function render() {
    await nextTick()
    const element = chartEl.value
    if (!element) return
    if (!chart || chart.getDom() !== element) {
      disposeChart()
      chart = echarts.init(element, null, { renderer: 'canvas' })
    }

    const option = resolveOption()
    if (!option) chart.clear()
    else chart.setOption(option, { notMerge: true, lazyUpdate: true })
    chart.resize()
  }

  watch(
    chartEl,
    async (element, previous) => {
      const observer = ensureResizeObserver()
      if (previous) observer?.unobserve(previous)
      if (!element) {
        disposeChart()
        return
      }
      observer?.observe(element)
      await render()
    },
    { flush: 'post' }
  )

  watch(resolveOption, render, { deep: true, flush: 'post' })

  onBeforeUnmount(() => {
    resizeObserver?.disconnect()
    resizeObserver = null
    disposeChart()
  })

  return { chartEl, render }
}
