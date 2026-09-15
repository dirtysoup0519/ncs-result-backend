const GENERATED_AT = '2026-09-13T18:30:00+08:00'

export const capabilityAvailability = {
  globalStatus: true,
  overview: true,
  platformDistribution: true,
  durationDistribution: true,
  weekdayWeekendProfile: true,
  loadPrediction: false,
  stationHourHeatmap: false,
  stationRanking: true,
  feeEnergyTrend: true,
  processSummary: true
}

const makeMeta = (extra = {}) => ({
  requestId: `mock-${Math.random().toString(36).slice(2, 10)}`,
  dataVersion: 'dataset:mock-v3.3',
  dataDate: '2019-09-13',
  generatedAt: GENERATED_AT,
  staleness: 'FRESH',
  empty: false,
  partial: false,
  ...extra
})

export const ok = (data, meta = {}) => ({
  code: 'OK',
  message: 'ok',
  data,
  meta: makeMeta(meta)
})

const rankingRows = [
  ['100047', '科学大道充电站', 334, '328.60', '2098.40'],
  ['100021', '高铁站充电站', 268, '298.20', '1863.50'],
  ['100088', '科技园充电站', 221, '274.10', '1502.30'],
  ['100014', '大学城充电站', 205, '251.70', '1345.60'],
  ['100063', '商业广场充电站', 188, '236.40', '1201.20'],
  ['100032', '政务中心充电站', 176, '214.60', '1039.50'],
  ['100009', '住宅区充电站', 154, '196.80', '988.10'],
  ['100071', '产业园充电站', 137, '178.20', '821.40'],
  ['100052', '机场充电站', 129, '166.50', '792.30'],
  ['100096', '会展中心充电站', 112, '151.40', '738.80']
]

const trendRows = [
  ['2019-01', 39, '34.50', '264.30'],
  ['2019-02', 88, '75.80', '598.70'],
  ['2019-03', 146, '132.10', '992.40'],
  ['2019-04', 213, '194.40', '1414.80'],
  ['2019-05', 312, '286.20', '2031.70'],
  ['2019-06', 427, '401.60', '2790.10'],
  ['2019-07', 594, '568.70', '3988.20'],
  ['2019-08', 760, '721.30', '5114.60'],
  ['2019-09', 816, '850.20', '4681.62']
]

export const mockResponses = {
  capabilities: ok({
    items: Object.entries(capabilityAvailability).map(([capabilityCode, available]) => ({
      capabilityCode,
      available
    }))
  }, { dataVersion: null, dataDate: null, staleness: 'UNKNOWN' }),

  filterOptions: ok({
    topic: 'overview',
    regions: [],
    stations: [],
    dateRange: { minDate: '2019-01-01', maxDate: '2019-09-13' }
  }, { dataVersion: null, dataDate: null, staleness: 'UNKNOWN' }),

  manifest: ok({
    items: Object.entries(capabilityAvailability).map(([componentCode, available]) => ({
      componentCode,
      available,
      refreshIntervalSeconds: null
    }))
  }, { dataVersion: null, dataDate: null, staleness: 'UNKNOWN' }),

  dataStatus: ok({
    dataDate: '2019-09-13',
    sourceRecordCount: 3395,
    stationCount: 105,
    updatedAt: GENERATED_AT,
    qualityStatus: 'PASSED',
    staleness: 'FRESH'
  }),

  overview: ok({
    items: [
      { metricCode: 'total_order_count', displayName: '总订单数', value: 3395, unit: 'count', precision: 0 },
      { metricCode: 'total_charging_energy', displayName: '总充电量', value: '21876.42', unit: 'kWh', precision: 2 },
      { metricCode: 'total_charging_fee', displayName: '总充电费用', value: '3264.80', unit: 'CNY', precision: 2 },
      { metricCode: 'total_user_count', displayName: '总用户数', value: 1268, unit: 'count', precision: 0 },
      { metricCode: 'active_station_count', displayName: '活跃站点数', value: 98, unit: 'count', precision: 0 }
    ]
  }),

  platformDistribution: ok({
    subject: 'ORDER',
    totalOrderCount: 3395,
    unit: 'count',
    items: [
      { platformCode: 'IOS', displayName: 'iOS', orderCount: 2234, orderRatio: '0.6580', totalFees: '1820.40' },
      { platformCode: 'ANDROID', displayName: 'Android', orderCount: 1155, orderRatio: '0.3402', totalFees: '1432.90' },
      { platformCode: 'WEB', displayName: 'Web', orderCount: 6, orderRatio: '0.0018', totalFees: '11.50' }
    ]
  }),

  durationDistribution: ok({
    subject: 'ORDER',
    unit: 'count',
    items: [
      { bucketCode: 'PT0H_PT1H', label: '0–1h', lowerMinutes: 0, upperMinutes: 60, orderCount: 412, ratio: '0.1214' },
      { bucketCode: 'PT1H_PT2H', label: '1–2h', lowerMinutes: 60, upperMinutes: 120, orderCount: 526, ratio: '0.1549' },
      { bucketCode: 'PT2H_PT3H', label: '2–3h', lowerMinutes: 120, upperMinutes: 180, orderCount: 1088, ratio: '0.3205' },
      { bucketCode: 'PT3H_PLUS', label: '3h+', lowerMinutes: 180, upperMinutes: null, orderCount: 1369, ratio: '0.4032' }
    ]
  }),

  weekdayWeekendProfile: ok({
    indicators: [
      { metricCode: 'order_count', displayName: '订单量', unit: 'count', max: null },
      { metricCode: 'charging_energy', displayName: '充电量', unit: 'kWh', max: null },
      { metricCode: 'charging_fee', displayName: '费用', unit: 'CNY', max: null },
      { metricCode: 'user_count', displayName: '用户数', unit: 'count', max: null },
      { metricCode: 'avg_duration', displayName: '平均时长', unit: 'hour', max: null }
    ],
    series: [
      {
        dayType: 'WEEKDAY',
        displayName: '工作日',
        rawValues: [3309, '21261.82', '3152.40', 1220, '2.86'],
        normalizedValues: null
      },
      {
        dayType: 'WEEKEND',
        displayName: '周末',
        rawValues: [86, '614.60', '112.40', 64, '2.98'],
        normalizedValues: null
      }
    ],
    normalization: null
  }),

  loadPrediction: ok({
    availability: 'UNAVAILABLE',
    date: null,
    cutoffHour: null,
    forecastStartAt: null,
    energyUnit: 'kWh',
    orderCountUnit: 'count',
    actual: [],
    forecast: [],
    interval: {
      available: false,
      confidenceLevel: null
    },
    modelVersion: null,
    predictionRunId: null,
    generatedAt: null
  }),

  stationHourHeatmap: ok({
    availability: 'UNAVAILABLE',
    metricCode: 'kwh',
    unit: 'kWh',
    hours: Array.from({ length: 24 }, (_, hour) => hour),
    stations: [],
    points: [],
    valueRange: { min: null, max: null }
  }),

  stationRanking: ok({
    metricCode: 'total_fees',
    unit: 'CNY',
    items: rankingRows.map(([stationId, stationName, orderCount, totalFees, totalKwh], index) => ({
      rank: index + 1,
      stationId,
      stationName,
      orderCount,
      totalFees,
      totalKwh,
      value: totalFees
    }))
  }),

  feeEnergyTrend: ok({
    granularity: 'MONTH',
    units: { fees: 'CNY', energy: 'kWh', orders: 'count' },
    points: trendRows.map(([period, orderCount, totalFees, totalKwh]) => ({
      period,
      orderCount,
      totalFees,
      totalKwh
    }))
  }),

  processSummary: ok({
    scope: 'ALL_STATIONS',
    recordCount: 1594,
    sessionCount: 1594,
    metrics: [
      { metricCode: 'average_soc', displayName: '平均 SOC', value: '0.678', unit: 'ratio', precision: 1 },
      { metricCode: 'average_current', displayName: '平均电流', value: '-32.4', unit: 'A', precision: 1 },
      { metricCode: 'average_voltage', displayName: '平均电压', value: '384.6', unit: 'V', precision: 1 },
      { metricCode: 'average_max_temperature', displayName: '平均峰值温度', value: '34.2', unit: 'celsius', precision: 1 }
    ]
  })
}

export const demoResponses = {
  weekdayWeekendProfile: ok({
    indicators: [
      { metricCode: 'order_count', displayName: '订单量', unit: 'count', max: 4000 },
      { metricCode: 'charging_energy', displayName: '充电量', unit: 'kWh', max: '25000' },
      { metricCode: 'charging_fee', displayName: '费用', unit: 'CNY', max: '4000' },
      { metricCode: 'user_count', displayName: '用户数', unit: 'count', max: 1500 },
      { metricCode: 'avg_duration', displayName: '平均时长', unit: 'hour', max: '4.00' }
    ],
    series: [
      {
        dayType: 'WEEKDAY',
        displayName: '工作日',
        rawValues: [3309, '21261.82', '3152.40', 1220, '2.86'],
        normalizedValues: ['0.94', '0.91', '0.89', '0.92', '0.73']
      },
      {
        dayType: 'WEEKEND',
        displayName: '周末',
        rawValues: [86, '614.60', '112.40', 64, '2.98'],
        normalizedValues: ['0.57', '0.61', '0.63', '0.55', '0.82']
      }
    ],
    normalization: {
      method: 'DEMO_DISPLAY_SCALE',
      version: 'v3.3-demo'
    }
  }),

  loadPrediction: (() => {
    // DEMO 仅用于视觉验收：小时订单分布参考最新交接包真实 hour_dist；
    // 历史负荷额外引入分时单均电量变化，避免与订单曲线机械重合。
    const hourOrders = [3, 3, 0, 2, 4, 2, 1, 1, 53, 158, 295, 504, 475, 291, 139, 192, 404, 437, 233, 119, 56, 14, 7, 2]
    const kwhPerOrderProfile = [5.6, 5.5, 5.4, 5.5, 5.7, 5.6, 5.4, 5.5, 5.8, 6.5, 7.1, 6.2, 5.7, 6.6, 7.3, 6.9, 6.7, 6.3, 5.9, 5.6, 5.4, 5.2, 5.0, 4.9]

    const actual = hourOrders.slice(0, 16).map((orderCount, hour) => {
      const localVariation = 0.96 + (((hour * 5) % 7) - 3) * 0.012
      const chargingEnergy = orderCount === 0
        ? 0
        : orderCount * kwhPerOrderProfile[hour] * localVariation
      return {
        hour,
        orderCount,
        chargingEnergy: chargingEnergy.toFixed(2)
      }
    })

    const forecast = hourOrders.slice(16).map((orderCount, index) => {
      const hour = 16 + index
      const seasonalFactor = 1 + 0.025 * Math.sin((hour - 16) * 0.9)
      const predicted = orderCount * kwhPerOrderProfile[hour] * seasonalFactor
      const horizonScale = 1 + index * 0.07
      const margin = Math.max(110, predicted * 0.10) * horizonScale
      const lower = Math.max(0, predicted - margin)
      const upper = predicted + margin
      return {
        hour,
        predictedEnergy: predicted.toFixed(2),
        lowerBound: lower.toFixed(2),
        upperBound: upper.toFixed(2)
      }
    })

    return ok({
      availability: 'AVAILABLE',
      date: '2019-09-13',
      cutoffHour: 16,
      forecastStartAt: '2019-09-13T16:00:00+08:00',
      energyUnit: 'kWh',
      orderCountUnit: 'count',
      actual,
      forecast,
      interval: { available: true, confidenceLevel: '0.90' },
      modelVersion: 'demo-v3.5-real-shape',
      predictionRunId: 'demo-run-v3.5',
      generatedAt: GENERATED_AT
    })
  })(),

  stationHourHeatmap: (() => {
    // DEMO 形态参考最新交接包：Top 站点权重 + 真实小时订单分布。
    // 强化中高值区分，使 11/12、16/17 点高峰和热门站点在大屏上可肉眼识别。
    const stationSeeds = [
      ['369001', '航空港区迎宾大道·交流站1号', 334],
      ['474204', '经开区航海东路·直流站3号', 213],
      ['955429', '航空港区迎宾大道·交流站2号', 190],
      ['228137', '上街区中心路·交直流站1号', 104],
      ['878706', '高新区科学大道·交直流站10号', 91],
      ['250527', '经开区第八大街·交直流站1号', 89],
      ['944515', '经开区第八大街·交直流站8号', 83],
      ['207262', '郑东新区金水东路·交直流站1号', 80]
    ]
    const hourOrders = [3, 3, 0, 2, 4, 2, 1, 1, 53, 158, 295, 504, 475, 291, 139, 192, 404, 437, 233, 119, 56, 14, 7, 2]
    const maxStationWeight = stationSeeds[0][2]
    const maxHourOrders = Math.max(...hourOrders)
    const stations = stationSeeds.map(([stationId, stationName]) => ({ stationId, stationName }))
    const points = []
    let max = 0

    stationSeeds.forEach(([stationId, , weight], stationIndex) => {
      const stationFactor = Math.pow(weight / maxStationWeight, 0.45)
      hourOrders.forEach((hourCount, hour) => {
        if (hourCount === 0) {
          points.push({ stationId, hour, value: '0', isObserved: false })
          return
        }
        const hourFactor = Math.pow(hourCount / maxHourOrders, 0.52)
        const deterministicVariation = 0.92 + ((stationIndex * 7 + hour * 3) % 13) / 100
        const value = Number((2 + 118 * stationFactor * hourFactor * deterministicVariation).toFixed(2))
        max = Math.max(max, value)
        points.push({ stationId, hour, value: value.toFixed(2), isObserved: true })
      })
    })

    return ok({
      availability: 'AVAILABLE',
      metricCode: 'kwh',
      unit: 'kWh',
      hours: Array.from({ length: 24 }, (_, hour) => hour),
      stations,
      points,
      valueRange: { min: '0', max: max.toFixed(2) }
    })
  })()
}
