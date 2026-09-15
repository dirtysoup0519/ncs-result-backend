import { demoResponses, mockResponses, ok } from './data.js'
import { useDemoData } from '../api/client.js'

const clone = (value) => JSON.parse(JSON.stringify(value))
const delay = (ms = 90) => new Promise((resolve) => setTimeout(resolve, ms))

function applyDemoAvailability(result, key) {
  if (!useDemoData) return result
  if (key === 'capabilities') {
    for (const item of result.data.items) {
      if (item.capabilityCode === 'loadPrediction' || item.capabilityCode === 'stationHourHeatmap') {
        item.available = true
      }
    }
  }
  if (key === 'manifest') {
    for (const item of result.data.items) {
      if (item.componentCode === 'loadPrediction' || item.componentCode === 'stationHourHeatmap') {
        item.available = true
      }
    }
  }
  return result
}

export async function mockGet(key, params = {}) {
  await delay()
  const source = useDemoData && demoResponses[key] ? demoResponses[key] : mockResponses[key]
  if (!source) return ok(null, { empty: true })

  const result = applyDemoAvailability(clone(source), key)
  result.meta.requestId = `mock-${Math.random().toString(36).slice(2, 10)}`

  if (key === 'filterOptions') result.data.topic = params?.topic || 'overview'

  if (key === 'loadPrediction' && result.data?.availability === 'AVAILABLE') {
    const requestedDate = params?.date || result.data.date
    const requestedCutoff = Number(params?.cutoffHour ?? result.data.cutoffHour)
    if (requestedDate !== result.data.date || requestedCutoff !== result.data.cutoffHour) {
      return clone(mockResponses.loadPrediction)
    }
  }

  if (key === 'stationHourHeatmap' && result.data?.availability === 'AVAILABLE') {
    const metric = params?.metric || 'kwh'
    if (metric !== 'kwh') return clone(mockResponses.stationHourHeatmap)

    const limit = Math.max(1, Math.min(Number(params?.limit) || 8, 10))
    result.data.stations = result.data.stations.slice(0, limit)
    const allowed = new Set(result.data.stations.map((item) => item.stationId))
    result.data.points = result.data.points.filter((point) => allowed.has(point.stationId))
  }

  return result
}
