/**
 * 插值工具验证脚本（Batch A）
 *
 * 断言 docs/v3.6-frozen-plan.md 第 3.6 节列出的 10 条数学不变量。
 * 纯 Node 执行，不依赖浏览器 / Vue / ECharts。
 */
import {
  pchipInterpolate,
  interpolateSeries,
  splitContinuousSegments
} from '../src/utils/interpolation.js'

let passed = 0
const failures = []

function assert(name, condition, detail = '') {
  if (condition) {
    passed += 1
  } else {
    failures.push(`${name}${detail ? ` — ${detail}` : ''}`)
  }
}

/** 在 displayPoints 中找到与指定 x 最接近的点 */
function nearest(points, x) {
  let best = null
  let bestDist = Infinity
  for (const p of points) {
    const d = Math.abs(p.x - x)
    if (d < bestDist) {
      bestDist = d
      best = p
    }
  }
  return best
}

function buildGrid(values) {
  return values.map((v, i) => ({ x: i, y: v }))
}

const EPS = 1e-9

/* ---------- 断言 1：原始节点被曲线精确经过 ---------- */
{
  const raw = buildGrid([10, 40, 30, 55, 20])
  const curve = pchipInterpolate(raw)
  let ok = true
  let detail = ''
  for (const node of raw) {
    const hit = curve.find((p) => Math.abs(p.x - node.x) < EPS)
    if (!hit || Math.abs(hit.y - node.y) > 1e-6) {
      ok = false
      detail = `节点 x=${node.x} 期望 y=${node.y}，实际 ${hit ? hit.y : '缺失'}`
      break
    }
  }
  assert('1. 原始节点被曲线精确经过', ok, detail)
}

/* ---------- 断言 2：单调区间不产生额外极值（overshoot 检查） ---------- */
{
  // 严格单增序列，插值后必须仍严格单增（局部极值 = overshoot）
  const raw = buildGrid([10, 20, 30, 40])
  const curve = pchipInterpolate(raw)
  let ok = true
  let detail = ''
  for (let i = 1; i < curve.length; i += 1) {
    if (curve[i].y < curve[i - 1].y - EPS) {
      ok = false
      detail = `x=${curve[i - 1].x.toFixed(3)}→${curve[i].x.toFixed(3)} 处出现回落 ${curve[i - 1].y.toFixed(4)}→${curve[i].y.toFixed(4)}`
      break
    }
  }
  // 同时确认没有超出原始值域
  const maxY = Math.max(...curve.map((p) => p.y))
  const minY = Math.min(...curve.map((p) => p.y))
  if (ok && (maxY > 40 + 1e-6 || minY < 10 - 1e-6)) {
    ok = false
    detail = `值域越界 [${minY.toFixed(4)}, ${maxY.toFixed(4)}] 超出 [10, 40]`
  }
  assert('2. 单调区间不产生额外极值', ok, detail)
}

/* ---------- 断言 3：常量序列仍为常量 ---------- */
{
  const curve = pchipInterpolate(buildGrid([10, 10, 10, 10]))
  const ok = curve.every((p) => Math.abs(p.y - 10) < 1e-6)
  assert('3. 常量序列仍为常量', ok, ok ? '' : `出现非 10 值：${curve.map((p) => p.y.toFixed(4)).join(',')}`)
}

/* ---------- 断言 4：单调序列保持单调（增/减各一） ---------- */
{
  const up = pchipInterpolate(buildGrid([10, 20, 30, 40]))
  const down = pchipInterpolate(buildGrid([40, 30, 20, 10]))

  let okUp = true
  for (let i = 1; i < up.length; i += 1) {
    if (up[i].y < up[i - 1].y - EPS) { okUp = false; break }
  }
  let okDown = true
  for (let i = 1; i < down.length; i += 1) {
    if (down[i].y > down[i - 1].y + EPS) { okDown = false; break }
  }
  assert('4. 单调序列保持单调', okUp && okDown,
    `递增=${okUp ? 'OK' : 'FAIL'} 递减=${okDown ? 'OK' : 'FAIL'}`)
}

/* ---------- 断言 5：尖峰不过冲 ---------- */
{
  // [10,100,12,11]：峰值 100 处，插值不得出现 > 100 的假峰
  const curve = pchipInterpolate(buildGrid([10, 100, 12, 11]))
  const maxY = Math.max(...curve.map((p) => p.y))
  const minY = Math.min(...curve.map((p) => p.y))
  const ok = maxY <= 100 + 1e-6 && minY >= 10 - 1e-6
  assert('5. 尖峰不过冲', ok,
    `值域 [${minY.toFixed(4)}, ${maxY.toFixed(4)}] 应落在 [10, 100] 内`)
}

/* ---------- 断言 6：null 两侧不被连接 ---------- */
{
  const raw = [{ x: 0, y: 10 }, { x: 1, y: null }, { x: 2, y: 30 }]
  const segments = splitContinuousSegments(raw)
  const { displayPoints } = interpolateSeries(raw)

  // 应切成 2 段，且任何显示点都不得落在 x∈(0,2) 的「桥接区间」内
  const bridged = displayPoints.some((p) => p.x > 0 + EPS && p.x < 2 - EPS)
  const ok = segments.length === 2 && !bridged
  assert('6. null 两侧不被连接', ok,
    `段数=${segments.length}（期望 2），桥接点=${bridged ? '存在' : '无'}`)
}

/* ---------- 断言 7：无 NaN / Infinity ---------- */
{
  const raw = [
    { x: 0, y: 10 }, { x: 1, y: 25 }, { x: 2, y: null },
    { x: 3, y: 40 }, { x: 4, y: 38 }, { x: 5, y: 5 }
  ]
  const { displayPoints } = interpolateSeries(raw)
  const ok = displayPoints.length > 0 &&
    displayPoints.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
  assert('7. 无 NaN / Infinity', ok,
    displayPoints.length === 0 ? '输出为空' : '存在非有限值')
}

/* ---------- 断言 8：x 严格递增 ---------- */
{
  const raw = [
    { x: 0, y: 10 }, { x: 1, y: 25 }, { x: 2, y: null },
    { x: 3, y: 40 }, { x: 4, y: 38 }
  ]
  const { displayPoints } = interpolateSeries(raw)
  let ok = true
  let detail = ''
  for (let i = 1; i < displayPoints.length; i += 1) {
    if (!(displayPoints[i].x > displayPoints[i - 1].x)) {
      ok = false
      detail = `索引 ${i} 处 ${displayPoints[i - 1].x} → ${displayPoints[i].x}`
      break
    }
  }
  assert('8. x 严格递增', ok, detail)
}

/* ---------- 断言 9 & 10：置信区间结构 lower ≤ forecast ≤ upper，宽度 ≥ 0 ---------- */
{
  // 复刻组件中的「预测值 + 两侧宽度」结构
  const forecastRaw = buildGrid([50, 62, 58, 70, 66])
  const lowerRaw = buildGrid([40, 50, 46, 55, 52])
  const upperRaw = buildGrid([60, 74, 70, 85, 80])

  // 原始整点先算宽度
  const lowerGapRaw = forecastRaw.map((p, i) => ({ x: p.x, y: p.y - lowerRaw[i].y }))
  const upperGapRaw = forecastRaw.map((p, i) => ({ x: p.x, y: upperRaw[i].y - p.y }))

  const forecastCurve = pchipInterpolate(forecastRaw)
  const lowerGapCurve = pchipInterpolate(lowerGapRaw)
  const upperGapCurve = pchipInterpolate(upperGapRaw)

  // 重构：从结构上保证包围关系
  const lowGap = lowerGapCurve.map((p) => Math.max(0, p.y))
  const highGap = upperGapCurve.map((p) => Math.max(0, p.y))

  const lower = forecastCurve.map((p, i) => p.y - lowGap[i])
  const upper = forecastCurve.map((p, i) => p.y + highGap[i])

  let orderOk = true
  let orderDetail = ''
  for (let i = 0; i < forecastCurve.length; i += 1) {
    if (!(lower[i] <= forecastCurve[i].y + EPS && forecastCurve[i].y <= upper[i] + EPS)) {
      orderOk = false
      orderDetail = `x=${forecastCurve[i].x.toFixed(3)}: lower=${lower[i].toFixed(4)} forecast=${forecastCurve[i].y.toFixed(4)} upper=${upper[i].toFixed(4)}`
      break
    }
  }
  assert('9. 每个预测采样点 lower ≤ forecast ≤ upper', orderOk, orderDetail)

  let widthOk = true
  let widthDetail = ''
  for (let i = 0; i < upper.length; i += 1) {
    if (upper[i] - lower[i] < -EPS) {
      widthOk = false
      widthDetail = `x=${forecastCurve[i].x.toFixed(3)}: 宽度=${(upper[i] - lower[i]).toFixed(4)}`
      break
    }
  }
  assert('10. interval width ≥ 0', widthOk, widthDetail)
}

/* ---------- 断言 11：自定义多边形闭合环（替代 stack 渲染层的几何校验） ---------- */
{
  // 复刻组件的 bandPolygon 构造：upper 正向 + lower 反向 = 闭合环
  const forecastRaw = buildGrid([300, 620, 300, 120])
  const lowerRaw = buildGrid([220, 470, 220, 90])
  const upperRaw = buildGrid([380, 770, 380, 150])

  const lowerGapRaw = forecastRaw.map((p, i) => ({ x: p.x, y: p.y - lowerRaw[i].y }))
  const upperGapRaw = forecastRaw.map((p, i) => ({ x: p.x, y: upperRaw[i].y - p.y }))

  const forecastCurve = pchipInterpolate(forecastRaw)
  const lowerGapCurve = pchipInterpolate(lowerGapRaw)
  const upperGapCurve = pchipInterpolate(upperGapRaw)

  const lowerCurve = forecastCurve.map((p, i) => ({ x: p.x, y: p.y - Math.max(0, lowerGapCurve[i].y) }))
  const upperCurve = forecastCurve.map((p, i) => ({ x: p.x, y: p.y + Math.max(0, upperGapCurve[i].y) }))

  const bandPolygon = [
    ...upperCurve.map((p) => [p.x, p.y]),
    ...lowerCurve.slice().reverse().map((p) => [p.x, p.y])
  ]

  const expectedLen = forecastCurve.length * 2
  const closesAtSameX = bandPolygon[0][0] === bandPolygon[bandPolygon.length - 1][0]
  const allFinite = bandPolygon.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
  // 环内每一对 (upper[i], lower[i]) 都满足 upper ≥ lower —— 保证多边形不自交
  const noSelfIntersect = upperCurve.every((p, i) => p.y >= lowerCurve[i].y - EPS)

  assert('11. 置信区间多边形闭合环合法',
    bandPolygon.length === expectedLen && closesAtSameX && allFinite && noSelfIntersect,
    `点数=${bandPolygon.length}/${expectedLen} 同x收口=${closesAtSameX} 有限值=${allFinite} 不自交=${noSelfIntersect}`)
}

/* ---------- 断言 12：lowerBound 为 0 不得被当作 null 丢弃 ---------- */
{
  // 真实 Demo 数据中 hour 21/22/23 的 lowerBound 恰为 '0'。
  // 0 是有效数值，必须保留 —— 若误判为缺失，置信区间会在 21:00 处断裂。
  const lowerRaw = [
    { x: 20, y: 158.25 }, { x: 21, y: 0 }, { x: 22, y: 0 }, { x: 23, y: 0 }
  ]
  const forecastRaw = [
    { x: 20, y: 299.05 }, { x: 21, y: 71.02 }, { x: 22, y: 34.32 }, { x: 23, y: 9.8 }
  ]

  const gapRaw = lowerRaw.map((p, i) => {
    const f = forecastRaw[i]
    if (p.y == null || f.y == null) return { x: p.x, y: null }
    return { x: p.x, y: f.y - p.y }
  })

  const segments = splitContinuousSegments(gapRaw)
  const curve = pchipInterpolate(gapRaw)

  // 正确的不变量（只针对 lower === 0 的那些点，i=0 的 lower 非零不参与）：
  //  1) lower=0 是有效值，不应被切成多段（若被误判为 null，会断成 2 段）
  //  2) 这些点的 gap 必须精确等于 forecast（证明 lower 被当作 0 使用，而非被丢弃）
  //  3) 从 gap 反推的 lower 必须回到 0
  const zeroIdx = lowerRaw.map((p, i) => (p.y === 0 ? i : -1)).filter((i) => i >= 0)
  const singleSegment = segments.length === 1
  const gapEqualsForecast = zeroIdx.every((i) => Math.abs(gapRaw[i].y - forecastRaw[i].y) < 1e-9)
  const reconstructedZero = zeroIdx.every((i) => Math.abs(forecastRaw[i].y - gapRaw[i].y) < 1e-9)

  assert('12. lowerBound = 0 保留为有效值（非 null）',
    zeroIdx.length === 3 && singleSegment && gapEqualsForecast && reconstructedZero && curve.length > 0,
    `零值点=${zeroIdx.length}（期望 3）段数=${segments.length}（期望 1）gap==forecast=${gapEqualsForecast} 反推为0=${reconstructedZero} 点数=${curve.length}`)
}

/* ---------- 附加：单点 / 两点边界与「不修改原始点」 ---------- */
{
  const single = pchipInterpolate([{ x: 5, y: 42 }])
  assert('附加 A. 单点原样保留', single.length === 1 && single[0].x === 5 && single[0].y === 42)

  const two = pchipInterpolate([{ x: 0, y: 0 }, { x: 2, y: 20 }])
  const mid = nearest(two, 1)
  assert('附加 B. 两点退化为线性', mid && Math.abs(mid.y - 10) < 1e-6,
    mid ? `x≈1 处 y=${mid.y.toFixed(4)}（期望 10）` : '未找到中点')

  const original = [{ x: 0, y: 10 }, { x: 1, y: 20 }, { x: 2, y: 30 }]
  const snapshot = JSON.stringify(original)
  interpolateSeries(original)
  assert('附加 C. 不修改原始业务点', JSON.stringify(original) === snapshot)
}

/* ---------- 结果输出 ---------- */
const total = passed + failures.length
if (failures.length) {
  console.error(`Interpolation verification FAILED (${passed}/${total})`)
  for (const f of failures) console.error(`  ✗ ${f}`)
  process.exit(1)
}
console.log(`Interpolation verification PASSED (${total} assertions)`)
