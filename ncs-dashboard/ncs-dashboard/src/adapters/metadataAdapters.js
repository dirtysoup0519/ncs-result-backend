import { adaptEnvelope, ApiProtocolError, assertBusinessDate } from './response.js'
import { toNonNegativeInteger } from './decimal.js'
import { REGISTERED_COMPONENT_CODES } from '../config/componentCodes.js'

// 保持既有导出面：组件码的唯一定义在 config/componentCodes.js，此处仅转发。
export { REGISTERED_COMPONENT_CODES }

const REGISTERED_SET = new Set(REGISTERED_COMPONENT_CODES)

function ensureArray(value, field) {
  if (!Array.isArray(value)) throw new ApiProtocolError(`${field} must be an array`)
  return value
}

function ensureString(value, field) {
  if (typeof value !== 'string' || !value.trim()) throw new ApiProtocolError(`${field} must be a non-empty string`)
  return value
}

function ensureRegisteredCode(value, field) {
  const code = ensureString(value, field)
  if (!REGISTERED_SET.has(code)) throw new ApiProtocolError(`${field} has unknown component code ${code}`)
  return code
}

function mapUnique(items, codeField, context) {
  const map = Object.create(null)
  for (const item of items) {
    const code = item[codeField]
    if (code in map) throw new ApiProtocolError(`${context} contains duplicate code ${code}`)
    map[code] = item
  }
  return map
}

function assertUnique(items, field, context) {
  const seen = new Set()
  for (const item of items) {
    const value = item[field]
    if (seen.has(value)) throw new ApiProtocolError(`${context} contains duplicate ${field} ${value}`)
    seen.add(value)
  }
}

export function adaptCapabilities(response) {
  return adaptEnvelope(response, (data) => {
    const items = ensureArray(data?.items, 'capabilities.items').map((item) => {
      if (typeof item.available !== 'boolean') throw new ApiProtocolError('capabilities.available must be boolean')
      return {
        capabilityCode: ensureRegisteredCode(item.capabilityCode, 'capabilities.capabilityCode'),
        available: item.available
      }
    })
    return { items, map: mapUnique(items, 'capabilityCode', 'capabilities.items') }
  })
}

export function adaptManifest(response) {
  return adaptEnvelope(response, (data) => {
    const items = ensureArray(data?.items, 'manifest.items').map((item) => ({
      componentCode: ensureRegisteredCode(item.componentCode, 'manifest.componentCode'),
      available: (() => {
        if (typeof item.available !== 'boolean') throw new ApiProtocolError('manifest.available must be boolean')
        return item.available
      })(),
      refreshIntervalSeconds: toNonNegativeInteger(
        item.refreshIntervalSeconds,
        'manifest.refreshIntervalSeconds',
        { nullable: true }
      )
    }))
    return { items, map: mapUnique(items, 'componentCode', 'manifest.items') }
  })
}

export function adaptFilterOptions(response, expectedTopic = null) {
  return adaptEnvelope(response, (data, meta) => {
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw new ApiProtocolError('filterOptions data must be an object')
    const topic = ensureRegisteredCode(data.topic, 'filterOptions.topic')
    if (expectedTopic !== null && topic !== expectedTopic) {
      throw new ApiProtocolError(`filterOptions.topic must equal requested topic ${expectedTopic}`)
    }

    const regions = ensureArray(data.regions, 'filterOptions.regions').map((item) => ({
      regionId: ensureString(item.regionId, 'filterOptions.regionId'),
      regionName: ensureString(item.regionName, 'filterOptions.regionName')
    }))
    assertUnique(regions, 'regionId', 'filterOptions.regions')
    const regionIds = new Set(regions.map((item) => item.regionId))

    const stations = ensureArray(data.stations, 'filterOptions.stations').map((item) => ({
      stationId: ensureString(item.stationId, 'filterOptions.stationId'),
      stationName: ensureString(item.stationName, 'filterOptions.stationName'),
      regionId: ensureString(item.regionId, 'filterOptions.station.regionId')
    }))
    assertUnique(stations, 'stationId', 'filterOptions.stations')
    for (const station of stations) {
      if (!regionIds.has(station.regionId)) {
        throw new ApiProtocolError(`filterOptions station ${station.stationId} references unknown region ${station.regionId}`)
      }
    }

    if (!('dateRange' in data)) throw new ApiProtocolError('filterOptions.dateRange field is required')
    let dateRange = null
    if (data.dateRange != null) {
      if (typeof data.dateRange !== 'object' || Array.isArray(data.dateRange)) {
        throw new ApiProtocolError('filterOptions.dateRange must be an object or null')
      }
      const minDate = assertBusinessDate(data.dateRange.minDate, 'filterOptions.dateRange.minDate', { nullable: false })
      const maxDate = assertBusinessDate(data.dateRange.maxDate, 'filterOptions.dateRange.maxDate', { nullable: false })
      if (minDate > maxDate) throw new ApiProtocolError('filterOptions.dateRange.minDate must not be after maxDate')
      dateRange = { minDate, maxDate }
    }

    if (meta.empty && (regions.length || stations.length || dateRange !== null)) {
      throw new ApiProtocolError('empty filter-options response must use regions=[], stations=[], dateRange=null')
    }

    return { topic, regions, stations, dateRange }
  })
}
