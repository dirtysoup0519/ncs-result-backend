// 公共组件注册表：全工程唯一的组件码来源。
// metadataAdapters 的 capability/manifest 校验与 composables 的编排都以本文件为准。
export const REGISTERED_COMPONENT_CODES = Object.freeze([
  'globalStatus',
  'overview',
  'platformDistribution',
  'durationDistribution',
  'weekdayWeekendProfile',
  'loadPrediction',
  'stationHourHeatmap',
  'stationRanking',
  'feeEnergyTrend',
  'processSummary'
])
