import { adaptEnvelope, ApiProtocolError, assertBusinessDate, assertOffsetTimestamp } from './response.js'
import {
  assertPrecision,
  toDecimalNumber,
  toInteger,
  toNonNegativeDecimalNumber,
  toNonNegativeInteger,
  toPercent,
  toRatio
} from './decimal.js'

const PLATFORM_CODES = new Set(['ANDROID', 'IOS', 'WEB', 'UNKNOWN'])
const QUALITY_STATUS = new Set(['PASSED', 'WARNING', 'FAILED', 'UNKNOWN'])
const STALENESS = new Set(['FRESH', 'STALE', 'UNKNOWN'])
const OVERVIEW_CODES = new Set(['total_order_count', 'total_charging_energy', 'total_charging_fee', 'total_user_count', 'active_station_count'])
const OVERVIEW_UNITS = new Map([
  ['total_order_count', 'count'],
  ['total_charging_energy', 'kWh'],
  ['total_charging_fee', 'CNY'],
  ['total_user_count', 'count'],
  ['active_station_count', 'count']
])
const PROCESS_UNITS = new Map([
  ['average_soc', 'ratio'],
  ['average_current', 'A'],
  ['average_voltage', 'V'],
  ['average_max_temperature', 'celsius']
])
const DURATION_BUCKETS = [
  ['PT0H_PT1H', 0, 60],
  ['PT1H_PT2H', 60, 120],
  ['PT2H_PT3H', 120, 180],
  ['PT3H_PLUS', 180, null]
]
const DAY_TYPES = new Set(['WEEKDAY', 'WEEKEND'])
const WEEKDAY_INDICATORS = [
  ['order_count', 'count'],
  ['charging_energy', 'kWh'],
  ['charging_fee', 'CNY'],
  ['user_count', 'count'],
  ['avg_duration', 'hour']
]
const TREND_GRANULARITY = new Set(['HOUR', 'DAY', 'MONTH'])
const PROCESS_METRICS = new Set(['average_soc', 'average_current', 'average_voltage', 'average_max_temperature'])
const HEATMAP_METRICS = new Map([
  ['kwh', 'kWh'],
  ['orders', 'count'],
  ['fees', 'CNY']
])

function ensureArray(value, field) {
  if (!Array.isArray(value)) throw new ApiProtocolError(`${field} must be an array`)
  return value
}

function ensureObject(value, field) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ApiProtocolError(`${field} must be an object`)
  return value
}

function ensureString(value, field, { nullable = false } = {}) {
  if (value === null && nullable) return null
  if (typeof value !== 'string' || !value.trim()) throw new ApiProtocolError(`${field} must be a non-empty string${nullable ? ' or null' : ''}`)
  return value
}

function ensureBoolean(value, field) {
  if (typeof value !== 'boolean') throw new ApiProtocolError(`${field} must be boolean`)
  return value
}

function ensureEnum(value, allowed, field) {
  if (!allowed.has(value)) throw new ApiProtocolError(`${field} has unsupported value ${String(value)}`)
  return value
}

function parseByUnit(value, unit, field, { nullable = false } = {}) {
  if (unit === 'count') return toNonNegativeInteger(value, field, { nullable })
  if (unit === 'ratio') return toRatio(value, field, { nullable })
  return toDecimalNumber(value, field, { nullable })
}

function ensureTimestamp(value, field) {
  return assertOffsetTimestamp(value, field)
}

function assertHour(hour, field) {
  const parsed = toNonNegativeInteger(hour, field)
  if (parsed > 23) throw new ApiProtocolError(`${field} must be in [0, 23]`)
  return parsed
}

function shanghaiDateHour(value, field) {
  ensureTimestamp(value, field)
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(new Date(value))
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return {
    date: `${map.year}-${map.month}-${map.day}`,
    hour: Number(map.hour)
  }
}

function ratioLiteralTolerance(value) {
  const text = typeof value === 'string' ? value.trim() : ''
  const match = text.match(/^[+-]?(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/)
  if (!match) return 1e-12

  const fractionDigits = (match[2] ?? match[3] ?? '').length
  const exponent = Number(match[4] ?? 0)
  if (fractionDigits === 0 && exponent === 0) return 1e-12

  const step = 10 ** (exponent - fractionDigits)
  const tolerance = Math.abs(step) / 2
  return Number.isFinite(tolerance) && tolerance > 0 ? tolerance + 1e-12 : 1e-12
}

function assertRatioSumWithinRounding(context, rawRatios, parsedRatios) {
  const sum = parsedRatios.reduce((total, value) => total + value, 0)
  const tolerance = rawRatios.reduce((total, value) => total + ratioLiteralTolerance(value), 0) + 1e-12
  if (Math.abs(sum - 1) > tolerance) {
    throw new ApiProtocolError(`${context} ratio sum ${sum.toFixed(6)} exceeds the rounding tolerance implied by the returned decimal strings`)
  }
}

function assertRatioMatchesCount(context, rawRatio, parsedRatio, count, totalCount) {
  const expected = count / totalCount
  const tolerance = ratioLiteralTolerance(rawRatio)
  if (Math.abs(parsedRatio - expected) > tolerance) {
    throw new ApiProtocolError(`${context} ratio is inconsistent with orderCount/totalOrderCount within returned precision`)
  }
}

function requireEmptyArray(value, field) {
  const array = ensureArray(value, field)
  if (array.length !== 0) throw new ApiProtocolError(`${field} must be empty when meta.empty=true`)
  return array
}

export const adaptDataStatus = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'dataStatus')
  const dataDate = assertBusinessDate(data.dataDate, 'dataStatus.dataDate', { nullable: false })
  const staleness = ensureEnum(data.staleness, STALENESS, 'dataStatus.staleness')
  if (meta.dataDate !== null && meta.dataDate !== dataDate) {
    throw new ApiProtocolError('dataStatus.dataDate must match meta.dataDate when meta.dataDate is present')
  }
  if (meta.staleness !== staleness) {
    throw new ApiProtocolError('dataStatus.staleness must match meta.staleness')
  }
  return {
    ...data,
    dataDate,
    sourceRecordCount: toNonNegativeInteger(data.sourceRecordCount, 'dataStatus.sourceRecordCount'),
    stationCount: toNonNegativeInteger(data.stationCount, 'dataStatus.stationCount'),
    updatedAt: ensureTimestamp(data.updatedAt, 'dataStatus.updatedAt'),
    qualityStatus: ensureEnum(data.qualityStatus, QUALITY_STATUS, 'dataStatus.qualityStatus'),
    staleness
  }
})

export const adaptOverview = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'overview')
  if (meta.empty) return { items: requireEmptyArray(data.items, 'overview.items') }
  const items = ensureArray(data.items, 'overview.items').map((item) => ({
    ...item,
    metricCode: ensureString(item.metricCode, 'overview.metricCode'),
    displayName: ensureString(item.displayName, `overview.${item.metricCode}.displayName`),
    unit: ensureString(item.unit, `overview.${item.metricCode}.unit`),
    precision: assertPrecision(item.precision, `overview.${item.metricCode}.precision`),
    value: (() => {
      const expectedUnit = OVERVIEW_UNITS.get(item.metricCode)
      if (expectedUnit && item.unit !== expectedUnit) throw new ApiProtocolError(`overview.${item.metricCode}.unit must be ${expectedUnit}`)
      if (item.metricCode === 'total_order_count' || item.metricCode === 'total_user_count' || item.metricCode === 'active_station_count') {
        return toNonNegativeInteger(item.value, `overview.${item.metricCode}.value`)
      }
      if (item.metricCode === 'total_charging_energy') {
        return toNonNegativeDecimalNumber(item.value, `overview.${item.metricCode}.value`, { nullable: false })
      }
      return parseByUnit(item.value, item.unit, `overview.${item.metricCode}.value`)
    })()
  }))
  const codes = items.map((item) => item.metricCode)
  if (items.length !== OVERVIEW_CODES.size || new Set(codes).size !== OVERVIEW_CODES.size || codes.some((code) => !OVERVIEW_CODES.has(code))) {
    throw new ApiProtocolError('overview.items must contain the five frozen metric codes exactly once')
  }
  return { items }
})

export const adaptPlatformDistribution = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'platform')
  if (data.subject !== 'ORDER') throw new ApiProtocolError('platform.subject must be ORDER')
  if (data.unit !== 'count') throw new ApiProtocolError('platform.unit must be count')
  const totalOrderCount = toNonNegativeInteger(data.totalOrderCount, 'platform.totalOrderCount')
  const sourceItems = ensureArray(data.items, 'platform.items')
  const items = sourceItems.map((item) => {
    ensureEnum(item.platformCode, PLATFORM_CODES, 'platform.platformCode')
    const ratio = toRatio(item.orderRatio, `platform.${item.platformCode}.orderRatio`, { nullable: false })
    return {
      ...item,
      displayName: ensureString(item.displayName, `platform.${item.platformCode}.displayName`),
      orderCount: toNonNegativeInteger(item.orderCount, `platform.${item.platformCode}.orderCount`),
      totalFees: toDecimalNumber(item.totalFees, `platform.${item.platformCode}.totalFees`, { nullable: true }),
      orderRatio: ratio,
      orderPercent: ratio * 100
    }
  })
  const codes = new Set()
  for (const item of items) {
    if (codes.has(item.platformCode)) throw new ApiProtocolError(`platform duplicate platformCode ${item.platformCode}`)
    codes.add(item.platformCode)
  }
  if (meta.empty) {
    if (totalOrderCount !== 0 || items.length !== 0) throw new ApiProtocolError('empty platform response must have totalOrderCount=0 and items=[]')
    return { ...data, totalOrderCount, items }
  }
  if (totalOrderCount === 0 || items.length === 0) {
    throw new ApiProtocolError('platform payload is empty but meta.empty=false')
  }
  if (items.length) {
    const countSum = items.reduce((sum, item) => sum + item.orderCount, 0)
    if (countSum !== totalOrderCount) throw new ApiProtocolError('platform item orderCount sum must equal totalOrderCount')

    items.forEach((item, index) => {
      assertRatioMatchesCount(
        `platform.${item.platformCode}.orderRatio`,
        sourceItems[index].orderRatio,
        item.orderRatio,
        item.orderCount,
        totalOrderCount
      )
    })
    assertRatioSumWithinRounding(
      'platform',
      sourceItems.map((item) => item.orderRatio),
      items.map((item) => item.orderRatio)
    )
  }
  return { ...data, totalOrderCount, items }
})

export const adaptDurationDistribution = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'duration')
  if (data.subject !== 'ORDER') throw new ApiProtocolError('duration.subject must be ORDER')
  if (data.unit !== 'count') throw new ApiProtocolError('duration.unit must be count')
  const sourceItems = ensureArray(data.items, 'duration.items')
  if (meta.empty) {
    if (sourceItems.length !== 0) throw new ApiProtocolError('empty duration response must use items=[]')
    return { ...data, items: [] }
  }
  if (sourceItems.length !== DURATION_BUCKETS.length) {
    throw new ApiProtocolError('duration.items must contain exactly four frozen buckets')
  }
  const items = sourceItems.map((item, index) => {
    const bucketCode = ensureString(item.bucketCode, 'duration.bucketCode')
    const expected = DURATION_BUCKETS[index]
    const lowerMinutes = toNonNegativeInteger(item.lowerMinutes, `duration.${bucketCode}.lowerMinutes`)
    const upperMinutes = toNonNegativeInteger(item.upperMinutes, `duration.${bucketCode}.upperMinutes`, { nullable: true })
    if (!expected || bucketCode !== expected[0] || lowerMinutes !== expected[1] || upperMinutes !== expected[2]) {
      throw new ApiProtocolError('duration buckets must match the frozen four left-closed/right-open ranges in order')
    }
    return {
      ...item,
      bucketCode,
      label: ensureString(item.label, `duration.${bucketCode}.label`),
      lowerMinutes,
      upperMinutes,
      orderCount: toNonNegativeInteger(item.orderCount, `duration.${bucketCode}.orderCount`),
      ratio: toRatio(item.ratio, `duration.${bucketCode}.ratio`, { nullable: false }),
      percent: toPercent(item.ratio, `duration.${bucketCode}.ratio`, { nullable: false })
    }
  })
  assertRatioSumWithinRounding(
    'duration',
    sourceItems.map((item) => item.ratio),
    items.map((item) => item.ratio)
  )
  return { ...data, items }
})

export const adaptWeekdayWeekend = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'weekdayWeekend')
  if (meta.empty) {
    requireEmptyArray(data.indicators, 'weekdayWeekend.indicators')
    requireEmptyArray(data.series, 'weekdayWeekend.series')
    if (data.normalization !== null) throw new ApiProtocolError('empty weekdayWeekend normalization must be null')
    return { ...data, indicators: [], series: [], normalization: null, normalizationAvailable: false }
  }
  const sourceIndicators = ensureArray(data.indicators, 'weekdayWeekend.indicators')
  if (sourceIndicators.length !== WEEKDAY_INDICATORS.length) {
    throw new ApiProtocolError('weekdayWeekend.indicators must contain the five frozen metrics')
  }
  const indicators = sourceIndicators.map((item, index) => {
    const metricCode = ensureString(item.metricCode, 'weekdayWeekend.metricCode')
    const unit = ensureString(item.unit, `weekdayWeekend.${metricCode}.unit`)
    const expected = WEEKDAY_INDICATORS[index]
    if (!expected || metricCode !== expected[0] || unit !== expected[1]) {
      throw new ApiProtocolError('weekdayWeekend indicators must follow the frozen metric order and units')
    }
    return {
      ...item,
      metricCode,
      displayName: ensureString(item.displayName, `weekdayWeekend.${metricCode}.displayName`),
      unit,
      max: parseByUnit(item.max, unit, `weekdayWeekend.${metricCode}.max`, { nullable: true })
    }
  })

  const series = ensureArray(data.series, 'weekdayWeekend.series').map((entry) => {
    ensureEnum(entry.dayType, DAY_TYPES, 'weekdayWeekend.dayType')
    if (!Array.isArray(entry.rawValues) || entry.rawValues.length !== indicators.length) {
      throw new ApiProtocolError(`${entry.dayType}.rawValues length mismatch`)
    }
    const rawValues = entry.rawValues.map((value, index) =>
      parseByUnit(value, indicators[index].unit, `${entry.dayType}.rawValues[${index}]`)
    )
    let normalizedValues = null
    if (entry.normalizedValues !== null && entry.normalizedValues !== undefined) {
      if (!Array.isArray(entry.normalizedValues) || entry.normalizedValues.length !== indicators.length) {
        throw new ApiProtocolError(`${entry.dayType}.normalizedValues length mismatch`)
      }
      normalizedValues = entry.normalizedValues.map((value, index) =>
        toRatio(value, `${entry.dayType}.normalizedValues[${index}]`, { nullable: false })
      )
    }
    return {
      ...entry,
      displayName: ensureString(entry.displayName, `${entry.dayType}.displayName`),
      rawValues,
      normalizedValues
    }
  })

  if (series.length !== 2 || !series.some((item) => item.dayType === 'WEEKDAY') || !series.some((item) => item.dayType === 'WEEKEND')) {
    throw new ApiProtocolError('weekdayWeekend.series must contain exactly WEEKDAY and WEEKEND')
  }

  const hasNormalization = data.normalization !== null && data.normalization !== undefined
  const allMaxPresent = indicators.every((item) => item.max !== null)
  const allNormalizedPresent = series.every((item) => Array.isArray(item.normalizedValues))

  if (hasNormalization) {
    ensureObject(data.normalization, 'weekdayWeekend.normalization')
    ensureString(data.normalization.method, 'weekdayWeekend.normalization.method')
    ensureString(data.normalization.version, 'weekdayWeekend.normalization.version')
    if (!allMaxPresent || !allNormalizedPresent) {
      throw new ApiProtocolError('weekdayWeekend normalization fields must be returned as a complete group')
    }
  } else if (indicators.some((item) => item.max !== null) || series.some((item) => item.normalizedValues !== null)) {
    throw new ApiProtocolError('weekdayWeekend normalization fields must be null as a group')
  }

  return { ...data, indicators, series, normalizationAvailable: hasNormalization }
})

export const adaptStationRanking = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'ranking')
  if (data.metricCode !== 'total_fees') throw new ApiProtocolError('ranking.metricCode must be total_fees')
  if (data.unit !== 'CNY') throw new ApiProtocolError('ranking.unit must be CNY')

  const sourceItems = ensureArray(data.items, 'ranking.items')
  if (meta.empty) {
    if (sourceItems.length !== 0) throw new ApiProtocolError('empty ranking response must use items=[]')
    return { ...data, items: [] }
  }
  if (sourceItems.length === 0) throw new ApiProtocolError('ranking payload is empty but meta.empty=false')

  const items = sourceItems.map((item) => ({
    ...item,
    stationId: ensureString(item.stationId, 'ranking.stationId'),
    stationName: ensureString(item.stationName, `ranking.${item.stationId}.stationName`),
    rank: toNonNegativeInteger(item.rank, `ranking.${item.stationId}.rank`),
    orderCount: toNonNegativeInteger(item.orderCount, `ranking.${item.stationId}.orderCount`),
    totalFees: toDecimalNumber(item.totalFees, `ranking.${item.stationId}.totalFees`, { nullable: false }),
    totalKwh: toNonNegativeDecimalNumber(item.totalKwh, `ranking.${item.stationId}.totalKwh`, { nullable: false }),
    value: toDecimalNumber(item.value, `ranking.${item.stationId}.value`, { nullable: false })
  }))

  if (items.length > 10) throw new ApiProtocolError('ranking.items must not exceed 10 rows in V1')
  const rankingStationIds = new Set()
  for (const item of items) {
    if (rankingStationIds.has(item.stationId)) throw new ApiProtocolError(`ranking duplicate stationId ${item.stationId}`)
    rankingStationIds.add(item.stationId)
  }
  for (let index = 0; index < items.length; index += 1) {
    const current = items[index]
    if (current.rank !== index + 1) throw new ApiProtocolError('ranking.rank must be continuous from 1')
    if (Math.abs(current.value - current.totalFees) > 1e-9) throw new ApiProtocolError('ranking.value must equal totalFees')
    if (index === 0) continue
    const previous = items[index - 1]
    if (previous.totalFees < current.totalFees) throw new ApiProtocolError('ranking items must be sorted by totalFees DESC')
    if (previous.totalFees === current.totalFees && previous.stationId.localeCompare(current.stationId) > 0) {
      throw new ApiProtocolError('ranking tie-break must be stationId ASC')
    }
  }
  return { ...data, items }
})

export const adaptFeeEnergyTrend = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'trend')
  ensureEnum(data.granularity, TREND_GRANULARITY, 'trend.granularity')
  ensureObject(data.units, 'trend.units')
  if (data.units.fees !== 'CNY' || data.units.energy !== 'kWh' || data.units.orders !== 'count') {
    throw new ApiProtocolError('trend.units must be CNY/kWh/count')
  }
  const sourcePoints = ensureArray(data.points, 'trend.points')
  if (meta.empty) {
    if (sourcePoints.length !== 0) throw new ApiProtocolError('empty trend response must use points=[]')
    return { ...data, points: [] }
  }
  if (sourcePoints.length === 0) throw new ApiProtocolError('trend payload is empty but meta.empty=false')

  return {
    ...data,
    points: sourcePoints.map((point) => ({
      ...point,
      period: ensureString(point.period, 'trend.period'),
      orderCount: toNonNegativeInteger(point.orderCount, `trend.${point.period}.orderCount`),
      totalFees: toDecimalNumber(point.totalFees, `trend.${point.period}.totalFees`, { nullable: false }),
      totalKwh: toNonNegativeDecimalNumber(point.totalKwh, `trend.${point.period}.totalKwh`, { nullable: false })
    }))
  }
})

export const adaptProcessSummary = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'process')
  const scope = ensureString(data.scope, 'process.scope')
  const recordCount = toNonNegativeInteger(data.recordCount, 'process.recordCount')
  const sessionCount = toNonNegativeInteger(data.sessionCount, 'process.sessionCount')
  if (meta.empty) {
    requireEmptyArray(data.metrics, 'process.metrics')
    if (recordCount !== 0 || sessionCount !== 0) throw new ApiProtocolError('empty process response must use zero record/session counts')
    return { ...data, scope, recordCount, sessionCount, metrics: [] }
  }
  const metrics = ensureArray(data.metrics, 'process.metrics').map((metric) => {
    ensureEnum(metric.metricCode, PROCESS_METRICS, 'process.metricCode')
    return {
      ...metric,
      displayName: ensureString(metric.displayName, `process.${metric.metricCode}.displayName`),
      unit: (() => {
        const unit = ensureString(metric.unit, `process.${metric.metricCode}.unit`)
        const expected = PROCESS_UNITS.get(metric.metricCode)
        if (unit !== expected) throw new ApiProtocolError(`process.${metric.metricCode}.unit must be ${expected}`)
        return unit
      })(),
      precision: assertPrecision(metric.precision, `process.${metric.metricCode}.precision`),
      value: parseByUnit(metric.value, metric.unit, `process.${metric.metricCode}.value`, { nullable: true })
    }
  })
  if (metrics.length !== PROCESS_METRICS.size || new Set(metrics.map((metric) => metric.metricCode)).size !== PROCESS_METRICS.size) {
    throw new ApiProtocolError('process.metrics must contain the four frozen metric codes exactly once')
  }
  return {
    ...data,
    scope,
    recordCount,
    sessionCount,
    metrics
  }
})

export const adaptLoadPrediction = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'prediction')
  if (data.availability === 'UNAVAILABLE') {
    if (!Array.isArray(data.actual) || !Array.isArray(data.forecast)) {
      throw new ApiProtocolError('UNAVAILABLE prediction must keep actual/forecast arrays')
    }
    if (data.actual.length || data.forecast.length) {
      throw new ApiProtocolError('UNAVAILABLE prediction must return empty actual/forecast arrays')
    }
    if (data.date !== null || data.cutoffHour !== null || data.forecastStartAt !== null) {
      throw new ApiProtocolError('UNAVAILABLE prediction date/cutoff/forecastStartAt must be null')
    }
    if (data.energyUnit !== 'kWh' || data.orderCountUnit !== 'count') {
      throw new ApiProtocolError('UNAVAILABLE prediction must keep frozen kWh/count units')
    }
    const interval = ensureObject(data.interval, 'prediction.interval')
    if (interval.available !== false || interval.confidenceLevel !== null) {
      throw new ApiProtocolError('UNAVAILABLE prediction interval must be available=false with null confidenceLevel')
    }
    if (data.modelVersion !== null || data.predictionRunId !== null || data.generatedAt !== null) {
      throw new ApiProtocolError('UNAVAILABLE prediction model/run/generatedAt must be null')
    }
    return { ...data, actual: [], forecast: [] }
  }
  if (data.availability !== 'AVAILABLE') throw new ApiProtocolError('prediction availability must be AVAILABLE or UNAVAILABLE')

  const date = assertBusinessDate(data.date, 'prediction.date', { nullable: false })
  const cutoffHour = assertHour(data.cutoffHour, 'prediction.cutoffHour')
  const forecastStartAt = ensureTimestamp(data.forecastStartAt, 'prediction.forecastStartAt')
  const forecastStartBusiness = shanghaiDateHour(forecastStartAt, 'prediction.forecastStartAt')
  if (forecastStartBusiness.date !== date) throw new ApiProtocolError('prediction.forecastStartAt must resolve to prediction.date in Asia/Shanghai')
  const forecastStartHour = forecastStartBusiness.hour
  if (forecastStartHour < cutoffHour) throw new ApiProtocolError('prediction.forecastStartAt must not be before cutoffHour')
  if (data.energyUnit !== 'kWh' || data.orderCountUnit !== 'count') {
    throw new ApiProtocolError('prediction units must be kWh/count')
  }

  const actualHours = new Set()
  const actual = ensureArray(data.actual, 'prediction.actual').map((point) => {
    const hour = assertHour(point.hour, 'prediction.actual.hour')
    if (hour >= cutoffHour) throw new ApiProtocolError(`prediction actual hour ${hour} must be before cutoff ${cutoffHour}`)
    if (actualHours.has(hour)) throw new ApiProtocolError(`prediction actual contains duplicate hour ${hour}`)
    actualHours.add(hour)
    return {
      ...point,
      hour,
      orderCount: toNonNegativeInteger(point.orderCount, `prediction.actual.${hour}.orderCount`, { nullable: true }),
      chargingEnergy: toNonNegativeDecimalNumber(point.chargingEnergy, `prediction.actual.${hour}.chargingEnergy`, { nullable: false })
    }
  })

  const interval = ensureObject(data.interval, 'prediction.interval')
  const intervalAvailable = ensureBoolean(interval.available, 'prediction.interval.available')
  if (!intervalAvailable && interval.confidenceLevel != null) {
    throw new ApiProtocolError('prediction confidenceLevel must be null when interval is unavailable')
  }

  const forecastHours = new Set()
  const forecast = ensureArray(data.forecast, 'prediction.forecast').map((point) => {
    const hour = assertHour(point.hour, 'prediction.forecast.hour')
    if (hour < forecastStartHour) throw new ApiProtocolError(`prediction forecast hour ${hour} is before forecastStartAt`)
    if (forecastHours.has(hour)) throw new ApiProtocolError(`prediction forecast contains duplicate hour ${hour}`)
    forecastHours.add(hour)
    const base = {
      ...point,
      hour,
      predictedEnergy: toNonNegativeDecimalNumber(point.predictedEnergy, `prediction.forecast.${hour}.predictedEnergy`, { nullable: false })
    }
    if (intervalAvailable) {
      base.lowerBound = toNonNegativeDecimalNumber(point.lowerBound, `prediction.forecast.${hour}.lowerBound`, { nullable: false })
      base.upperBound = toNonNegativeDecimalNumber(point.upperBound, `prediction.forecast.${hour}.upperBound`, { nullable: false })
      if (base.lowerBound > base.predictedEnergy || base.predictedEnergy > base.upperBound) {
        throw new ApiProtocolError(`prediction interval must contain predictedEnergy at hour ${hour}`)
      }
    } else {
      if (point.lowerBound != null || point.upperBound != null) {
        throw new ApiProtocolError('prediction bounds must be null when interval is unavailable')
      }
      base.lowerBound = null
      base.upperBound = null
    }
    return base
  })

  if (meta.empty) {
    if (actual.length !== 0 || forecast.length !== 0) {
      throw new ApiProtocolError('empty AVAILABLE prediction must use actual=[] and forecast=[]')
    }
  } else {
    if (forecast.length === 0) throw new ApiProtocolError('prediction forecast is empty but meta.empty=false')
    const firstForecastHour = Math.min(...forecast.map((point) => point.hour))
    if (firstForecastHour !== forecastStartHour) {
      throw new ApiProtocolError('prediction forecast must start at forecastStartAt hour')
    }
  }

  const modelVersion = ensureString(data.modelVersion, 'prediction.modelVersion')
  const predictionRunId = ensureString(data.predictionRunId, 'prediction.predictionRunId')
  const generatedAt = ensureTimestamp(data.generatedAt, 'prediction.generatedAt')

  return {
    ...data,
    date,
    cutoffHour,
    forecastStartAt,
    modelVersion,
    predictionRunId,
    generatedAt,
    interval: {
      ...interval,
      confidenceLevel: intervalAvailable
        ? toRatio(interval.confidenceLevel, 'prediction.interval.confidenceLevel', { nullable: false })
        : null
    },
    actual,
    forecast
  }
})

export const adaptStationHourHeatmap = (response) => adaptEnvelope(response, (data, meta) => {
  ensureObject(data, 'heatmap')
  const expectedUnit = HEATMAP_METRICS.get(data.metricCode)
  if (!expectedUnit) throw new ApiProtocolError('heatmap.metricCode must be kwh, orders or fees')
  if (data.unit !== expectedUnit) throw new ApiProtocolError(`heatmap.unit must be ${expectedUnit} for metric ${data.metricCode}`)

  const hours = ensureArray(data.hours, 'heatmap.hours').map((hour) => assertHour(hour, 'heatmap.hour'))
  if (hours.length !== 24 || hours.some((hour, index) => hour !== index)) {
    throw new ApiProtocolError('heatmap.hours must contain 0..23 exactly')
  }

  if (data.availability === 'UNAVAILABLE') {
    if (!Array.isArray(data.stations) || !Array.isArray(data.points)) throw new ApiProtocolError('UNAVAILABLE heatmap must keep stations/points arrays')
    if (data.stations.length || data.points.length) throw new ApiProtocolError('UNAVAILABLE heatmap must return empty stations/points arrays')
    const unavailableRange = ensureObject(data.valueRange, 'heatmap.valueRange')
    if (unavailableRange.min !== null || unavailableRange.max !== null) {
      throw new ApiProtocolError('UNAVAILABLE heatmap valueRange must be {min:null,max:null}')
    }
    return { ...data, hours, stations: [], points: [], valueRange: { min: null, max: null } }
  }
  if (data.availability !== 'AVAILABLE') throw new ApiProtocolError('heatmap availability must be AVAILABLE or UNAVAILABLE')

  const sourceStations = ensureArray(data.stations, 'heatmap.stations')
  const sourcePoints = ensureArray(data.points, 'heatmap.points')
  if (meta.empty) {
    if (sourceStations.length !== 0 || sourcePoints.length !== 0) {
      throw new ApiProtocolError('empty AVAILABLE heatmap must use stations=[] and points=[]')
    }
    const emptyRange = ensureObject(data.valueRange, 'heatmap.valueRange')
    if (emptyRange.min !== null || emptyRange.max !== null) {
      throw new ApiProtocolError('empty AVAILABLE heatmap valueRange must be {min:null,max:null}')
    }
    return { ...data, hours, stations: [], points: [], valueRange: { min: null, max: null } }
  }
  if (sourceStations.length === 0 || sourcePoints.length === 0) {
    throw new ApiProtocolError('heatmap payload is empty but meta.empty=false')
  }

  const stations = sourceStations.map((station) => ({
    stationId: ensureString(station.stationId, 'heatmap.stationId'),
    stationName: ensureString(station.stationName, `heatmap.${station.stationId}.stationName`)
  }))
  if (stations.length > 10) throw new ApiProtocolError('heatmap.stations must not exceed 10')
  const stationIds = new Set()
  for (const station of stations) {
    if (stationIds.has(station.stationId)) throw new ApiProtocolError(`heatmap duplicate stationId ${station.stationId}`)
    stationIds.add(station.stationId)
  }

  const pointKeys = new Set()
  const points = sourcePoints.map((point) => {
    const stationId = ensureString(point.stationId, 'heatmap.point.stationId')
    if (!stationIds.has(stationId)) throw new ApiProtocolError(`heatmap point references unknown station ${stationId}`)
    const hour = assertHour(point.hour, `heatmap.${stationId}.hour`)
    const key = `${stationId}:${hour}`
    if (pointKeys.has(key)) throw new ApiProtocolError(`heatmap duplicate point ${key}`)
    pointKeys.add(key)
    const value = expectedUnit === 'count'
      ? toNonNegativeInteger(point.value, `heatmap.${key}.value`)
      : toDecimalNumber(point.value, `heatmap.${key}.value`, { nullable: false })
    return {
      ...point,
      stationId,
      hour,
      value,
      isObserved: ensureBoolean(point.isObserved, `heatmap.${key}.isObserved`)
    }
  })

  ensureObject(data.valueRange, 'heatmap.valueRange')
  const valueRange = expectedUnit === 'count'
    ? {
        min: toNonNegativeInteger(data.valueRange.min, 'heatmap.valueRange.min'),
        max: toNonNegativeInteger(data.valueRange.max, 'heatmap.valueRange.max')
      }
    : {
        min: toDecimalNumber(data.valueRange.min, 'heatmap.valueRange.min', { nullable: false }),
        max: toDecimalNumber(data.valueRange.max, 'heatmap.valueRange.max', { nullable: false })
      }
  if (valueRange.min > valueRange.max) throw new ApiProtocolError('heatmap.valueRange.min must not exceed max')
  for (const point of points) {
    if (!point.isObserved && point.value !== 0) throw new ApiProtocolError('heatmap isObserved=false points must use补零 value 0')
    if (point.value < valueRange.min || point.value > valueRange.max) {
      throw new ApiProtocolError('heatmap point value must stay inside valueRange')
    }
  }
  // 冻结合同允许稀疏 points；缺失槽位不是业务 0，图表层保留为空白。
  return { ...data, hours, stations, points, valueRange }
})
