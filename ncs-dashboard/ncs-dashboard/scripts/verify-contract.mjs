import { capabilityAvailability, demoResponses, mockResponses } from '../src/mock/data.js'

const errors = []
const requiredMeta = [
  'requestId',
  'dataVersion',
  'dataDate',
  'generatedAt',
  'staleness',
  'empty',
  'partial'
]

const nearlyEqual = (a, b, epsilon = 1e-6) => Math.abs(Number(a) - Number(b)) <= epsilon
const sum = (values) => values.reduce((acc, value) => acc + Number(value), 0)
const isInteger = (value) => typeof value === 'number' && Number.isInteger(value)
const isDecimalString = (value) => typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))

for (const [name, response] of Object.entries(mockResponses)) {
  if (response.code !== 'OK') errors.push(`${name}: code must be OK`)
  if (!response.meta || typeof response.meta !== 'object') {
    errors.push(`${name}: missing meta`)
    continue
  }
  for (const key of requiredMeta) {
    if (!(key in response.meta)) errors.push(`${name}: missing meta.${key}`)
  }
  if (typeof response.meta.empty !== 'boolean') errors.push(`${name}: meta.empty must be boolean`)
  if (typeof response.meta.partial !== 'boolean') errors.push(`${name}: meta.partial must be boolean`)
}

if (capabilityAvailability.loadPrediction !== false) errors.push('loadPrediction must default to unavailable')
if (capabilityAvailability.stationHourHeatmap !== false) errors.push('stationHourHeatmap must default to unavailable')
if (mockResponses.loadPrediction.data.availability !== 'UNAVAILABLE') errors.push('prediction payload must default to UNAVAILABLE')
if (mockResponses.stationHourHeatmap.data.availability !== 'UNAVAILABLE') errors.push('heatmap payload must default to UNAVAILABLE')

const weekdayWeekend = mockResponses.weekdayWeekendProfile.data
if (weekdayWeekend.normalization !== null) errors.push('weekday/weekend normalization must default to null')
if (weekdayWeekend.indicators.some((item) => item.max !== null)) errors.push('weekday/weekend indicator max must default to null')
if (weekdayWeekend.series.some((item) => item.normalizedValues !== null)) errors.push('weekday/weekend normalizedValues must default to null')

const overviewItems = Object.fromEntries(mockResponses.overview.data.items.map((item) => [item.metricCode, item]))
const totalOrders = Number(overviewItems.total_order_count.value)
const totalEnergy = Number(overviewItems.total_charging_energy.value)
const totalFees = Number(overviewItems.total_charging_fee.value)

if (!isInteger(overviewItems.total_order_count.value)) errors.push('overview total_order_count must be JSON integer')
if (!isInteger(overviewItems.total_user_count.value)) errors.push('overview total_user_count must be JSON integer')
if (!isInteger(overviewItems.active_station_count.value)) errors.push('overview active_station_count must be JSON integer')
if (!isDecimalString(overviewItems.total_charging_energy.value)) errors.push('overview total_charging_energy must be decimal string')
if (!isDecimalString(overviewItems.total_charging_fee.value)) errors.push('overview total_charging_fee must be decimal string')

const platform = mockResponses.platformDistribution.data
if (sum(platform.items.map((item) => item.orderCount)) !== totalOrders) errors.push('platform orderCount sum must equal overview total_order_count')
if (!nearlyEqual(sum(platform.items.map((item) => item.orderRatio)), 1, 0.0001)) errors.push('platform orderRatio sum must equal 1')
if (!nearlyEqual(sum(platform.items.map((item) => item.totalFees)), totalFees, 0.01)) errors.push('platform totalFees sum must equal overview total_charging_fee')
for (const item of platform.items) {
  if (!isInteger(item.orderCount)) errors.push(`platform ${item.platformCode}: orderCount must be JSON integer`)
  if (!isDecimalString(item.orderRatio)) errors.push(`platform ${item.platformCode}: orderRatio must be decimal string`)
  if (item.totalFees !== null && !isDecimalString(item.totalFees)) errors.push(`platform ${item.platformCode}: totalFees must be decimal string or null`)
}

const duration = mockResponses.durationDistribution.data
if (sum(duration.items.map((item) => item.orderCount)) !== totalOrders) errors.push('duration orderCount sum must equal overview total_order_count')
if (!nearlyEqual(sum(duration.items.map((item) => item.ratio)), 1, 0.0001)) errors.push('duration ratio sum must equal 1')
for (const item of duration.items) {
  if (!isInteger(item.orderCount)) errors.push(`duration ${item.bucketCode}: orderCount must be JSON integer`)
  if (!isDecimalString(item.ratio)) errors.push(`duration ${item.bucketCode}: ratio must be decimal string`)
}

const weekday = weekdayWeekend.series.find((item) => item.dayType === 'WEEKDAY')
const weekend = weekdayWeekend.series.find((item) => item.dayType === 'WEEKEND')
if (!weekday || !weekend) {
  errors.push('weekday/weekend series must contain WEEKDAY and WEEKEND')
} else {
  if (!nearlyEqual(weekday.rawValues[0] + weekend.rawValues[0], totalOrders)) errors.push('weekday/weekend orders must equal overview total_order_count')
  if (!nearlyEqual(Number(weekday.rawValues[1]) + Number(weekend.rawValues[1]), totalEnergy, 0.01)) errors.push('weekday/weekend energy must equal overview total_charging_energy')
  if (!nearlyEqual(Number(weekday.rawValues[2]) + Number(weekend.rawValues[2]), totalFees, 0.01)) errors.push('weekday/weekend fees must equal overview total_charging_fee')
  if (!isInteger(weekday.rawValues[0]) || !isInteger(weekend.rawValues[0])) errors.push('weekday/weekend order_count raw values must be JSON integer')
  if (!isInteger(weekday.rawValues[3]) || !isInteger(weekend.rawValues[3])) errors.push('weekday/weekend user_count raw values must be JSON integer')
  for (const pair of [[weekday, 'WEEKDAY'], [weekend, 'WEEKEND']]) {
    const [series, label] = pair
    for (const index of [1, 2, 4]) if (!isDecimalString(series.rawValues[index])) errors.push(`${label} continuous rawValues[${index}] must be decimal string`)
  }
}

const trend = mockResponses.feeEnergyTrend.data.points
if (!nearlyEqual(sum(trend.map((point) => point.orderCount)), totalOrders)) errors.push('trend orderCount sum must equal overview total_order_count')
if (!nearlyEqual(sum(trend.map((point) => point.totalKwh)), totalEnergy, 0.01)) errors.push('trend totalKwh sum must equal overview total_charging_energy')
if (!nearlyEqual(sum(trend.map((point) => point.totalFees)), totalFees, 0.01)) errors.push('trend totalFees sum must equal overview total_charging_fee')

const ranking = mockResponses.stationRanking.data
if (ranking.metricCode !== 'total_fees' || ranking.unit !== 'CNY') errors.push('station ranking must use total_fees/CNY')
for (let index = 0; index < ranking.items.length; index += 1) {
  const item = ranking.items[index]
  if (!isInteger(item.orderCount)) errors.push(`ranking row ${index}: orderCount must be JSON integer`)
  if (!isDecimalString(item.totalFees) || !isDecimalString(item.totalKwh) || !isDecimalString(item.value)) errors.push(`ranking row ${index}: continuous values must be decimal strings`)
  if (index > 0) {
    const previous = ranking.items[index - 1]
    if (Number(previous.totalFees) < Number(item.totalFees)) errors.push('station ranking must be totalFees DESC')
    if (Number(previous.totalFees) === Number(item.totalFees) && previous.stationId.localeCompare(item.stationId) > 0) errors.push('station ranking tie-break must be stationId ASC')
  }
}

const trendText = JSON.stringify(mockResponses.feeEnergyTrend)
for (const forbidden of ['serviceFee', 'profit']) if (trendText.includes(forbidden)) errors.push(`feeEnergyTrend contains forbidden field: ${forbidden}`)

const processMetrics = Object.fromEntries(mockResponses.processSummary.data.metrics.map((item) => [item.metricCode, item]))
if (!processMetrics.average_max_temperature) errors.push('process summary missing average_max_temperature')
if (Number(processMetrics.average_current?.value) >= 0) errors.push('average_current mock must preserve negative direction semantics')

// Demo prediction must obey the frozen cutoff semantics: actual < cutoff, forecast >= forecastStartAt, no overlap.
const prediction = demoResponses.loadPrediction.data
if (prediction.availability !== 'AVAILABLE') errors.push('demo prediction fixture must be AVAILABLE')
for (const point of prediction.actual) if (point.hour >= prediction.cutoffHour) errors.push('demo prediction actual must be strictly before cutoffHour')
const startHour = Number(prediction.forecastStartAt.slice(11, 13))
if (startHour < prediction.cutoffHour) errors.push('demo prediction forecastStartAt must not be before cutoffHour')
for (const point of prediction.forecast) if (point.hour < startHour) errors.push('demo prediction forecast point before forecastStartAt')
const actualHours = new Set(prediction.actual.map((point) => point.hour))
if (prediction.forecast.some((point) => actualHours.has(point.hour))) errors.push('demo prediction actual/forecast hours must not overlap')

if (errors.length) {
  console.error('Contract verification FAILED')
  for (const error of errors) console.error(`- ${error}`)
  process.exit(1)
}

console.log('Contract verification PASSED')
console.log(`Checked ${Object.keys(mockResponses).length} mock responses, strict types and cross-component invariants.`)
