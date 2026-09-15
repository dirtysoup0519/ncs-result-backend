import { mockResponses, demoResponses } from '../src/mock/data.js'
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
} from '../src/adapters/dashboardAdapters.js'
import { adaptCapabilities, adaptFilterOptions, adaptManifest } from '../src/adapters/metadataAdapters.js'

const clone = (value) => JSON.parse(JSON.stringify(value))
const adapters = {
  dataStatus: adaptDataStatus,
  overview: adaptOverview,
  platformDistribution: adaptPlatformDistribution,
  durationDistribution: adaptDurationDistribution,
  weekdayWeekendProfile: adaptWeekdayWeekend,
  loadPrediction: adaptLoadPrediction,
  stationHourHeatmap: adaptStationHourHeatmap,
  stationRanking: adaptStationRanking,
  feeEnergyTrend: adaptFeeEnergyTrend,
  processSummary: adaptProcessSummary
}

let negativeCases = 0
let positiveBoundaryCases = 0

function expectReject(label, fn, check = null) {
  negativeCases += 1
  let caught = null
  try {
    fn()
  } catch (error) {
    caught = error
  }
  if (!caught) throw new Error(`negative adapter case was accepted: ${label}`)
  if (check) check(caught)
}

function expectAccept(label, fn, check = null) {
  positiveBoundaryCases += 1
  let result
  try {
    result = fn()
  } catch (error) {
    throw new Error(`positive boundary case was rejected: ${label}: ${error.message}`)
  }
  if (check) check(result)
  return result
}

// Baseline positive fixtures.
for (const [key, adapter] of Object.entries(adapters)) adapter(mockResponses[key])
adaptLoadPrediction(demoResponses.loadPrediction)
adaptStationHourHeatmap(demoResponses.stationHourHeatmap)
adaptCapabilities(mockResponses.capabilities)
adaptManifest(mockResponses.manifest)
adaptFilterOptions(mockResponses.filterOptions, 'overview')

// Legal empty semantics: stable containers remain present, but collection payloads can be empty.
{
  const empty = clone(mockResponses.overview)
  empty.meta.empty = true
  empty.data.items = []
  expectAccept('overview legal empty response', () => adaptOverview(empty), (result) => {
    if (result.data.items.length !== 0) throw new Error('overview empty adapter did not preserve items=[]')
  })
}
{
  const empty = clone(mockResponses.durationDistribution)
  empty.meta.empty = true
  empty.data.items = []
  expectAccept('duration legal empty response', () => adaptDurationDistribution(empty))
}
{
  const empty = clone(mockResponses.weekdayWeekendProfile)
  empty.meta.empty = true
  empty.data.indicators = []
  empty.data.series = []
  empty.data.normalization = null
  expectAccept('weekday/weekend legal empty response', () => adaptWeekdayWeekend(empty))
}
{
  const empty = clone(mockResponses.processSummary)
  empty.meta.empty = true
  empty.data.recordCount = 0
  empty.data.sessionCount = 0
  empty.data.metrics = []
  expectAccept('process legal empty response', () => adaptProcessSummary(empty))
}

// partial=true does not loosen the frozen schema: a complete DTO is still accepted and UI can mark it as partial.
{
  const partial = clone(mockResponses.overview)
  partial.meta.partial = true
  expectAccept('overview complete partial response', () => adaptOverview(partial), (result) => {
    if (!result.meta.partial) throw new Error('partial flag was lost')
  })
}
{
  const partial = clone(mockResponses.processSummary)
  partial.meta.partial = true
  expectAccept('process complete partial response', () => adaptProcessSummary(partial))
}

// Ratio validation follows the precision carried by the returned decimal strings.
// Correct two-decimal rounding remains legal; obviously inconsistent ratios must fail below.
{
  const rounded = clone(mockResponses.platformDistribution)
  rounded.data.items[0].orderRatio = '0.66'
  rounded.data.items[1].orderRatio = '0.34'
  rounded.data.items[2].orderRatio = '0.00'
  expectAccept('platform ratios with valid two-decimal rounding', () => adaptPlatformDistribution(rounded))
}
{
  const rounded = clone(mockResponses.durationDistribution)
  rounded.data.items[0].ratio = '0.12'
  rounded.data.items[1].ratio = '0.15'
  rounded.data.items[2].ratio = '0.32'
  rounded.data.items[3].ratio = '0.40'
  expectAccept('duration rounded ratios summing to 0.99', () => adaptDurationDistribution(rounded))
}

// Heatmap points may be sparse under the current frozen contract.
{
  const sparse = clone(demoResponses.stationHourHeatmap)
  sparse.data.points.pop()
  expectAccept('sparse heatmap points', () => adaptStationHourHeatmap(sparse))
}

// ISO timestamps are compared in Asia/Shanghai business time, not by literal offset/hour text.
{
  const zulu = clone(demoResponses.loadPrediction)
  zulu.data.forecastStartAt = '2019-09-13T08:00:00Z' // 16:00 Asia/Shanghai
  expectAccept('prediction forecastStartAt with equivalent Z timestamp', () => adaptLoadPrediction(zulu))
}

// Metadata responses are allowed to list only a subset of registered codes.
{
  const capabilities = clone(mockResponses.capabilities)
  capabilities.data.items = capabilities.data.items.slice(0, 2)
  expectAccept('partial capabilities listing', () => adaptCapabilities(capabilities))
}
{
  const manifest = clone(mockResponses.manifest)
  manifest.data.items = manifest.data.items.slice(0, 2)
  expectAccept('partial manifest listing', () => adaptManifest(manifest))
}


{
  const empty = clone(mockResponses.filterOptions)
  empty.meta.empty = true
  empty.data.regions = []
  empty.data.stations = []
  empty.data.dateRange = null
  expectAccept('filter-options legal empty response', () => adaptFilterOptions(empty, 'overview'))
}

// Contract-negative cases: these must fail instead of being silently coerced.
// partial=true does not authorize structural field loss unless the backend contract is explicitly revised.
{
  const bad = clone(mockResponses.overview)
  bad.meta.partial = true
  bad.data.items.pop()
  expectReject('partial overview missing frozen KPI', () => adaptOverview(bad))
}

{
  const bad = clone(mockResponses.overview)
  bad.data.items.find((item) => item.metricCode === 'total_charging_energy').value = 21876.42
  expectReject('continuous value as JSON number', () => adaptOverview(bad))
}
{
  const bad = clone(mockResponses.overview)
  bad.data.items.find((item) => item.metricCode === 'total_order_count').value = '3395'
  expectReject('count as string', () => adaptOverview(bad))
}
{
  const bad = clone(mockResponses.overview)
  bad.data.items.find((item) => item.metricCode === 'total_order_count').value = -1
  expectReject('negative order count', () => adaptOverview(bad))
}
{
  const bad = clone(mockResponses.overview)
  bad.data.items[0].precision = -1
  expectReject('negative precision', () => adaptOverview(bad))
}
{
  const bad = clone(mockResponses.platformDistribution)
  bad.data.items[0].orderRatio = null
  expectReject('required platform orderRatio is null', () => adaptPlatformDistribution(bad))
}
{
  const bad = clone(mockResponses.platformDistribution)
  const first = bad.data.items[0].orderRatio
  bad.data.items[0].orderRatio = bad.data.items[1].orderRatio
  bad.data.items[1].orderRatio = first
  expectReject('platform orderRatio does not match orderCount/totalOrderCount', () => adaptPlatformDistribution(bad))
}
{
  const bad = clone(mockResponses.durationDistribution)
  bad.data.items[0].ratio = '0.10'
  bad.data.items[1].ratio = '0.10'
  bad.data.items[2].ratio = '0.10'
  bad.data.items[3].ratio = '0.00'
  expectReject('duration ratios are clearly inconsistent with a complete distribution', () => adaptDurationDistribution(bad))
}
{
  const bad = clone(mockResponses.durationDistribution)
  bad.data.items[0].ratio = null
  expectReject('required duration ratio is null', () => adaptDurationDistribution(bad))
}
{
  const bad = clone(mockResponses.durationDistribution)
  bad.data.items[0].upperMinutes = 61
  expectReject('duration bucket boundary drift', () => adaptDurationDistribution(bad))
}
{
  const bad = clone(mockResponses.weekdayWeekendProfile)
  ;[bad.data.indicators[0], bad.data.indicators[1]] = [bad.data.indicators[1], bad.data.indicators[0]]
  expectReject('weekday/weekend frozen indicator order drift', () => adaptWeekdayWeekend(bad))
}
{
  const bad = clone(mockResponses.weekdayWeekendProfile)
  bad.data.normalization = {}
  expectReject('normalization object missing method/version', () => adaptWeekdayWeekend(bad))
}
{
  const bad = clone(demoResponses.loadPrediction)
  bad.data.actual.push({ hour: bad.data.cutoffHour, orderCount: 1, chargingEnergy: '1.0' })
  expectReject('actual at cutoff boundary', () => adaptLoadPrediction(bad))
}
{
  const bad = clone(demoResponses.loadPrediction)
  bad.data.forecastStartAt = '2019-09-13T07:00:00Z' // 15:00 Asia/Shanghai
  expectReject('forecast starts before cutoff in business timezone', () => adaptLoadPrediction(bad))
}
{
  const bad = clone(demoResponses.loadPrediction)
  bad.data.actual.push(clone(bad.data.actual[0]))
  expectReject('duplicate actual hour', () => adaptLoadPrediction(bad))
}
{
  const bad = clone(demoResponses.stationHourHeatmap)
  bad.data.points[0].stationId = 'unknown-station'
  expectReject('heatmap point references unknown station', () => adaptStationHourHeatmap(bad))
}
{
  const bad = clone(demoResponses.stationHourHeatmap)
  bad.data.points.push(clone(bad.data.points[0]))
  expectReject('heatmap duplicate station/hour point', () => adaptStationHourHeatmap(bad))
}
{
  const bad = clone(demoResponses.stationHourHeatmap)
  bad.data.valueRange.min = '9999'
  expectReject('heatmap valueRange min exceeds max', () => adaptStationHourHeatmap(bad))
}
{
  const bad = clone(mockResponses.stationHourHeatmap)
  delete bad.data.valueRange
  expectReject('UNAVAILABLE heatmap missing valueRange', () => adaptStationHourHeatmap(bad))
}
{
  const bad = clone(mockResponses.stationRanking)
  bad.data.items[0].value = '999.00'
  expectReject('ranking value differs from totalFees', () => adaptStationRanking(bad))
}
{
  const bad = clone(mockResponses.stationRanking)
  bad.data.items[1].totalFees = bad.data.items[0].totalFees
  bad.data.items[1].value = bad.data.items[0].totalFees
  bad.data.items[0].stationId = '200'
  bad.data.items[1].stationId = '100'
  expectReject('ranking tie-break is not stationId ASC', () => adaptStationRanking(bad))
}
{
  const bad = clone(mockResponses.feeEnergyTrend)
  bad.data.granularity = 'WEEK'
  expectReject('unsupported trend granularity', () => adaptFeeEnergyTrend(bad))
}
{
  const bad = clone(mockResponses.processSummary)
  bad.data.metrics.find((item) => item.metricCode === 'average_voltage').unit = 'kV'
  expectReject('process metric unit drift', () => adaptProcessSummary(bad))
}
{
  const bad = clone(mockResponses.processSummary)
  bad.data.metrics.push(clone(bad.data.metrics[0]))
  expectReject('process duplicate metric code', () => adaptProcessSummary(bad))
}
{
  const bad = clone(mockResponses.overview)
  delete bad.meta.generatedAt
  expectReject('missing required meta.generatedAt', () => adaptOverview(bad))
}
{
  const bad = clone(mockResponses.overview)
  bad.meta.generatedAt = '2026-09-13 18:30:00'
  expectReject('timestamp without timezone', () => adaptOverview(bad))
}
{
  const bad = clone(mockResponses.overview)
  bad.meta.dataDate = '2019-02-30'
  expectReject('invalid calendar business date', () => adaptOverview(bad))
}
{
  const bad = clone(mockResponses.overview)
  bad.data.items[0].value = '3395'
  expectReject('protocol error retains requestId', () => adaptOverview(bad), (error) => {
    if (error.requestId !== bad.meta.requestId) throw new Error('requestId was not preserved on protocol error')
  })
}
{
  const bad = clone(mockResponses.manifest)
  bad.data.items.push(clone(bad.data.items[0]))
  expectReject('duplicate manifest component code', () => adaptManifest(bad))
}
{
  const bad = clone(mockResponses.manifest)
  bad.data.items[0].available = 'false'
  expectReject('manifest available as string', () => adaptManifest(bad))
}
{
  const bad = clone(mockResponses.manifest)
  bad.data.items[0].refreshIntervalSeconds = -1
  expectReject('negative refreshIntervalSeconds', () => adaptManifest(bad))
}
{
  const bad = clone(mockResponses.capabilities)
  bad.data.items[0].available = 'false'
  expectReject('capability available as string', () => adaptCapabilities(bad))
}
{
  const bad = clone(mockResponses.capabilities)
  bad.data.items[0].capabilityCode = 'unknownComponent'
  expectReject('unknown capability code', () => adaptCapabilities(bad))
}
{
  const bad = clone(mockResponses.filterOptions)
  bad.data.dateRange.minDate = '2019/01/01'
  expectReject('filter-options invalid date format', () => adaptFilterOptions(bad, 'overview'))
}
{
  const bad = clone(mockResponses.filterOptions)
  bad.data.dateRange.minDate = '2019-02-30'
  expectReject('filter-options invalid calendar date', () => adaptFilterOptions(bad, 'overview'))
}
{
  const bad = clone(mockResponses.filterOptions)
  bad.data.dateRange.minDate = '2020-01-01'
  expectReject('filter-options minDate after maxDate', () => adaptFilterOptions(bad, 'overview'))
}
{
  const bad = clone(mockResponses.filterOptions)
  bad.data.topic = 'stationRanking'
  expectReject('filter-options topic mismatches requested topic', () => adaptFilterOptions(bad, 'overview'))
}
{
  const bad = clone(mockResponses.filterOptions)
  bad.data.regions = [{ regionId: 'r1', regionName: 'R1' }]
  bad.data.stations = [{ stationId: 's1', stationName: 'S1', regionId: 'missing' }]
  expectReject('filter-options station references unknown region', () => adaptFilterOptions(bad, 'overview'))
}

{
  const bad = clone(mockResponses.filterOptions)
  delete bad.data.regions
  expectReject('filter-options missing regions field', () => adaptFilterOptions(bad, 'overview'))
}
{
  const bad = clone(mockResponses.filterOptions)
  delete bad.data.dateRange
  expectReject('filter-options missing dateRange field', () => adaptFilterOptions(bad, 'overview'))
}


// V3.2: meta.empty must agree with the actual collection payload.
{
  const empty = clone(mockResponses.platformDistribution)
  empty.meta.empty = true
  empty.data.totalOrderCount = 0
  empty.data.items = []
  expectAccept('platform legal empty response', () => adaptPlatformDistribution(empty))
}
{
  const empty = clone(mockResponses.stationRanking)
  empty.meta.empty = true
  empty.data.items = []
  expectAccept('ranking legal empty response', () => adaptStationRanking(empty))
}
{
  const empty = clone(mockResponses.feeEnergyTrend)
  empty.meta.empty = true
  empty.data.points = []
  expectAccept('trend legal empty response', () => adaptFeeEnergyTrend(empty))
}
{
  const empty = clone(demoResponses.loadPrediction)
  empty.meta.empty = true
  empty.data.actual = []
  empty.data.forecast = []
  expectAccept('AVAILABLE prediction legal empty response', () => adaptLoadPrediction(empty))
}
{
  const empty = clone(demoResponses.stationHourHeatmap)
  empty.meta.empty = true
  empty.data.stations = []
  empty.data.points = []
  empty.data.valueRange = { min: null, max: null }
  expectAccept('AVAILABLE heatmap legal empty response', () => adaptStationHourHeatmap(empty))
}
{
  const bad = clone(mockResponses.platformDistribution)
  bad.data.totalOrderCount = 0
  bad.data.items = []
  expectReject('platform empty payload with meta.empty=false', () => adaptPlatformDistribution(bad))
}
{
  const bad = clone(mockResponses.stationRanking)
  bad.data.items = []
  expectReject('ranking empty payload with meta.empty=false', () => adaptStationRanking(bad))
}
{
  const bad = clone(mockResponses.feeEnergyTrend)
  bad.data.points = []
  expectReject('trend empty payload with meta.empty=false', () => adaptFeeEnergyTrend(bad))
}
{
  const bad = clone(demoResponses.loadPrediction)
  bad.data.actual = []
  bad.data.forecast = []
  expectReject('AVAILABLE prediction empty payload with meta.empty=false', () => adaptLoadPrediction(bad))
}
{
  const bad = clone(demoResponses.stationHourHeatmap)
  bad.data.stations = []
  bad.data.points = []
  bad.data.valueRange = { min: null, max: null }
  expectReject('AVAILABLE heatmap empty payload with meta.empty=false', () => adaptStationHourHeatmap(bad))
}
{
  const bad = clone(demoResponses.loadPrediction)
  bad.data.forecast.shift()
  expectReject('prediction forecast does not start at forecastStartAt', () => adaptLoadPrediction(bad))
}

// Envelope/meta validation errors must keep requestId too.
{
  const bad = clone(mockResponses.overview)
  bad.meta.generatedAt = '2026-09-13 18:30:00'
  expectReject('meta protocol error retains requestId', () => adaptOverview(bad), (error) => {
    if (error.requestId !== bad.meta.requestId) throw new Error('requestId was not preserved on meta protocol error')
  })
}

// data-status duplicates common metadata semantics; detect self-contradictory responses.
{
  const bad = clone(mockResponses.dataStatus)
  bad.meta.dataDate = '2019-09-12'
  expectReject('data-status body/meta dataDate mismatch', () => adaptDataStatus(bad))
}
{
  const bad = clone(mockResponses.dataStatus)
  bad.meta.staleness = 'STALE'
  expectReject('data-status body/meta staleness mismatch', () => adaptDataStatus(bad))
}

console.log('Adapter verification PASSED')
console.log(`Positive fixtures + ${positiveBoundaryCases} boundary cases + ${negativeCases} negative protocol cases checked.`)
