import { computed, reactive, ref } from 'vue'
import { dashboardApi } from '../api/dashboard.js'
import { metadataApi } from '../api/metadata.js'
import { REGISTERED_COMPONENT_CODES } from '../config/componentCodes.js'
import { adaptCapabilities, adaptFilterOptions, adaptManifest } from '../adapters/metadataAdapters.js'
import { predictionRequestParams } from '../config/dashboard.js'
import {
  adaptDataStatus,
  adaptDurationDistribution,
  adaptFeeEnergyTrend,
  adaptLoadPrediction,
  adaptOverview,
  adaptPlatformDistribution,
  adaptProcessSummary,
  adaptStationHourHeatmap,
  adaptStationRanking,
  adaptWeekdayWeekend
} from '../adapters/dashboardAdapters.js'

const componentConfig = {
  globalStatus: { request: dashboardApi.getDataStatus, adapter: adaptDataStatus },
  overview: { request: dashboardApi.getOverview, adapter: adaptOverview },
  platformDistribution: { request: dashboardApi.getPlatformDistribution, adapter: adaptPlatformDistribution },
  durationDistribution: { request: dashboardApi.getDurationDistribution, adapter: adaptDurationDistribution },
  weekdayWeekendProfile: { request: dashboardApi.getWeekdayWeekend, adapter: adaptWeekdayWeekend },
  loadPrediction: {
    request: () => dashboardApi.getLoadPrediction(predictionRequestParams()),
    adapter: adaptLoadPrediction
  },
  stationHourHeatmap: {
    request: () => dashboardApi.getStationHourHeatmap({ metric: 'kwh', limit: 8 }),
    adapter: adaptStationHourHeatmap
  },
  stationRanking: {
    request: () => dashboardApi.getStationRanking({ metric: 'fees', limit: 10 }),
    adapter: adaptStationRanking
  },
  feeEnergyTrend: {
    request: () => dashboardApi.getFeeEnergyTrend({ granularity: 'MONTH' }),
    adapter: adaptFeeEnergyTrend
  },
  processSummary: { request: dashboardApi.getProcessSummary, adapter: adaptProcessSummary }
}

// componentConfig 的 key 即组件码集合；此处与公共注册表做一次开发期一致性检查，
// 确保“公共注册表只有一个”，两处不同步时立即暴露而非抛出不相关的元数据错误。
if (import.meta.env.DEV) {
  const derivedCodes = Object.keys(componentConfig)
  const isSynced = derivedCodes.length === REGISTERED_COMPONENT_CODES.length &&
    derivedCodes.every((code) => REGISTERED_COMPONENT_CODES.includes(code))
  if (!isSynced) {
    console.warn(
      '[NCS Dashboard] componentConfig 与 REGISTERED_COMPONENT_CODES 不同步，请检查 src/config/componentCodes.js'
    )
  }
}

const registeredCodes = REGISTERED_COMPONENT_CODES

const makeState = () => ({
  status: 'loading',
  data: null,
  meta: null,
  error: null,
  refreshing: false,
  refreshError: null,
  lastSuccessData: null,
  lastSuccessMeta: null
})

function errorMessage(error) {
  const suffix = error?.requestId ? `（requestId: ${error.requestId}）` : ''
  return `${error?.message || '数据加载失败'}${suffix}`
}

export function useDashboard() {
  const states = reactive(Object.fromEntries(registeredCodes.map((code) => [code, makeState()])))
  const filters = ref(null)
  const bootstrapError = ref(null)
  const refreshing = ref(false)

  function markUnavailable(code, meta = null) {
    Object.assign(states[code], {
      status: 'unavailable',
      data: null,
      meta,
      error: null,
      refreshing: false,
      refreshError: null,
      lastSuccessData: null,
      lastSuccessMeta: null
    })
  }

  function markMetadataError(code, message) {
    const state = states[code]
    const previousData = state.status === 'success' ? state.data : state.lastSuccessData
    const previousMeta = state.status === 'success' ? state.meta : state.lastSuccessMeta
    if (previousData !== null && previousData !== undefined) {
      Object.assign(state, {
        status: 'success',
        data: previousData,
        meta: previousMeta,
        error: null,
        refreshing: false,
        refreshError: message,
        lastSuccessData: previousData,
        lastSuccessMeta: previousMeta
      })
      return
    }
    Object.assign(state, {
      status: 'error',
      data: null,
      error: message,
      refreshing: false,
      refreshError: null
    })
  }

  async function loadComponent(code) {
    const state = states[code]
    const config = componentConfig[code]
    if (!config) return

    const previousData = state.status === 'success' ? state.data : state.lastSuccessData
    const previousMeta = state.status === 'success' ? state.meta : state.lastSuccessMeta
    const hasPrevious = previousData !== null && previousData !== undefined

    if (hasPrevious) {
      state.status = 'success'
      state.data = previousData
      state.meta = previousMeta
      state.refreshing = true
      state.refreshError = null
    } else {
      state.status = 'loading'
      state.data = null
      state.error = null
      state.refreshing = false
      state.refreshError = null
    }

    try {
      const response = await config.request()
      const adapted = config.adapter(response)
      state.data = adapted.data
      state.meta = adapted.meta
      state.error = null
      state.refreshing = false
      state.refreshError = null

      if (adapted.data?.availability === 'UNAVAILABLE') {
        state.status = 'unavailable'
        state.lastSuccessData = null
        state.lastSuccessMeta = null
      } else if (adapted.meta?.empty) {
        state.status = 'empty'
        state.lastSuccessData = null
        state.lastSuccessMeta = null
      } else {
        state.status = 'success'
        state.lastSuccessData = adapted.data
        state.lastSuccessMeta = adapted.meta
      }
    } catch (error) {
      const message = errorMessage(error)
      state.refreshing = false
      if (hasPrevious) {
        state.status = 'success'
        state.data = previousData
        state.meta = previousMeta
        state.error = null
        state.refreshError = message
        state.lastSuccessData = previousData
        state.lastSuccessMeta = previousMeta
      } else {
        state.status = 'error'
        state.data = null
        state.error = message
        state.refreshError = null
      }
    }
  }

  async function loadFilterOptions(topic = 'overview') {
    try {
      const adapted = adaptFilterOptions(await metadataApi.getFilterOptions(topic), topic)
      filters.value = adapted.data
      return adapted.data
    } catch (error) {
      filters.value = null
      throw error
    }
  }

  async function bootstrap() {
    if (refreshing.value) return
    refreshing.value = true
    bootstrapError.value = null

    try {
      // 当前页面无筛选控件，因此按冻结流程执行 capabilities -> manifest。
      // 一旦页面启用筛选器，应在二者之间调用 loadFilterOptions(topic)。
      const capabilities = adaptCapabilities(await metadataApi.getCapabilities())
      const manifest = adaptManifest(await metadataApi.getManifest())
      const warnings = []
      const jobs = []

      for (const code of registeredCodes) {
        const capability = capabilities.data.map[code] ?? null
        const manifestItem = manifest.data.map[code] ?? null

        // 冻结简表没有明确“遗漏 code”的语义，因此 V3.2 不替后端把缺项猜成 unavailable。
        // 显式 false 才表示不可用；缺项视为元数据未知/不完整，并在已有成功数据时保留旧数据。
        if (capability == null && manifestItem == null) {
          const message = `capabilities 与 manifest 均未声明 ${code}，无法判断组件可用性`
          warnings.push(message)
          markMetadataError(code, message)
          continue
        }
        if (capability == null && manifestItem?.available !== false) {
          const message = `capabilities 未声明 ${code}，无法确认 manifest 的展示声明`
          warnings.push(message)
          markMetadataError(code, message)
          continue
        }
        if (manifestItem == null && capability?.available !== false) {
          const message = `manifest 未声明 ${code}，无法确认页面展示状态`
          warnings.push(message)
          markMetadataError(code, message)
          continue
        }
        if (manifestItem?.available === true && capability?.available !== true) {
          const message = `manifest 声明 ${code} 可用，但 capabilities 未启用该能力`
          warnings.push(message)
          markMetadataError(code, message)
          continue
        }
        if (capability?.available === false || manifestItem?.available === false) {
          markUnavailable(code, manifest.meta)
          continue
        }
        jobs.push(loadComponent(code))
      }

      await Promise.allSettled(jobs)
      if (warnings.length) bootstrapError.value = warnings.join('；')
    } catch (error) {
      bootstrapError.value = errorMessage(error)
      // 元数据整体请求失败时保留已经成功的数据；仅初次仍 loading 的组件进入 error。
      for (const state of Object.values(states)) {
        if (state.status === 'loading') {
          state.status = 'error'
          state.error = bootstrapError.value
        }
      }
    } finally {
      refreshing.value = false
    }
  }

  const batchWarning = computed(() => {
    // 并行刷新期间不同组件会短暂处于新旧批次混合的中间态。
    // 只在整轮 bootstrap/refresh 完成后判断最终批次一致性，避免误报闪烁。
    if (refreshing.value) return null

    const versions = new Set()
    const dates = new Set()
    for (const state of Object.values(states)) {
      if (!['success', 'empty'].includes(state.status) || !state.meta) continue
      if (state.meta.dataVersion) versions.add(state.meta.dataVersion)
      if (state.meta.dataDate) dates.add(state.meta.dataDate)
    }
    if (versions.size > 1 || dates.size > 1) {
      const versionText = versions.size > 1 ? `dataVersion=${[...versions].join(', ')}` : ''
      const dateText = dates.size > 1 ? `dataDate=${[...dates].join(', ')}` : ''
      return `检测到组件数据批次不一致${[versionText, dateText].filter(Boolean).length ? `（${[versionText, dateText].filter(Boolean).join('；')}）` : ''}`
    }
    return null
  })

  const insights = computed(() => {
    const result = []

    const ranking = states.stationRanking
    if (ranking.status === 'success' && ranking.data?.items?.length) {
      const top = ranking.data.items[0]
      result.push({
        level: 'info',
        title: '重点站点',
        content: `${top.stationName} 在当前统计范围内充电费用规模最高，可列为重点运营观察对象。`
      })
    }

    const weekdayWeekend = states.weekdayWeekendProfile
    if (weekdayWeekend.status === 'success') {
      const weekday = weekdayWeekend.data?.series?.find((item) => item.dayType === 'WEEKDAY')
      const weekend = weekdayWeekend.data?.series?.find((item) => item.dayType === 'WEEKEND')
      if (weekday?.rawValues?.[0] != null && weekend?.rawValues?.[0] != null && weekday.rawValues[0] > weekend.rawValues[0] * 2) {
        // Batch C.5：仅重写文案，**触发条件与 level 一律未动**。
        // 原文的问题是它只做了「观察 + 免责」两段，没有行动，读起来像数据分析免责声明：
        //   旧标题「需求分布」= 话题名；旧正文结尾「仍建议结合…进一步判断」= 自我声明无法结论。
        // 新文案补成完整建议结构：观察 → 限制 → 动作。
        // 口径说明：rawValues[0] 是 order_count（该序列按冻结指标顺序排列），是**累计量**，
        //   所以措辞保持「累计订单较高」而不敢写成「需求明显更高」——累计量受天数影响。
        result.push({
          level: 'warning',
          title: '排班参考',
          content: '工作日累计订单较高，但受统计天数影响，暂不宜直接据此增加排班。建议结合工作日、周末日均订单确定人员配置。'
        })
      }
    }

    const process = states.processSummary
    if (process.status === 'success') {
      result.push({
        level: 'note',
        title: '统计口径',
        content: '过程指标来自历史聚合，不代表设备当前实时状态；负电流保留原始方向语义。'
      })
    }

    if (!result.length) {
      result.push({ level: 'note', title: '运营建议', content: '等待相关业务指标加载成功后生成规则化建议。' })
    }
    return result.slice(0, 2)
  })

  return {
    states,
    filters,
    insights,
    bootstrapError,
    batchWarning,
    refreshing,
    bootstrap,
    loadComponent,
    loadFilterOptions
  }
}
