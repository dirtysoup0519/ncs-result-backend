import { http, useMock } from './client'
import { mockGet } from '../mock/service'

const get = (key, path, params) => useMock ? mockGet(key, params) : http.get(path, { params })

export const dashboardApi = {
  getDataStatus: (params) => get('dataStatus', '/meta/data-status', params),
  getOverview: (params) => get('overview', '/dashboard/overview', params),
  getPlatformDistribution: (params) => get('platformDistribution', '/audience/platform-distribution', params),
  getDurationDistribution: (params) => get('durationDistribution', '/charging/duration-distribution', params),
  getWeekdayWeekend: (params) => get('weekdayWeekendProfile', '/charging/weekday-weekend', params),
  getLoadPrediction: (params) => get('loadPrediction', '/predictions/load', params),
  getStationHourHeatmap: (params = { metric: 'kwh', limit: 8 }) => get('stationHourHeatmap', '/charging/station-hour-heatmap', params),
  getStationRanking: (params = { metric: 'fees', limit: 10 }) => get('stationRanking', '/stations/ranking', params),
  getFeeEnergyTrend: (params = { granularity: 'MONTH' }) => get('feeEnergyTrend', '/revenue/trend', params),
  getProcessSummary: (params) => get('processSummary', '/charging/process-summary', params)
}
