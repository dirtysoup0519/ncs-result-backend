/**
 * 纯数学插值工具（PCHIP / 单调三次 Hermite 插值）
 *
 * 设计约束（见 docs/v3.6-frozen-plan.md 第 3 章）：
 *  - 不依赖 Vue / ECharts / 任何业务 DTO，输入仅为 `{ x, y }` 点数组；
 *  - 不修改传入的原始点（纯函数，返回新数组）；
 *  - 支持 null 分段（不跨空档生成虚假曲线）；
 *  - 支持单点（原样保留）与两点（退化为线性）；
 *  - x 必须严格递增；
 *  - 保证不过冲（不制造原始数据中不存在的极值）。
 *
 * 为什么不用普通三次样条：普通样条在 100 → 200 → 210 → 150 这类序列上
 * 可能插值出 100 → 230 → 210，即制造出原始数据里不存在的假峰值。
 * PCHIP 通过限制导数避免 overshoot。
 */

const DEFAULT_SAMPLES_PER_SEGMENT = 12

/** 判断是否为「有效数值点」——排除 null / undefined / NaN / Infinity */
function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * 将 `{ x, y }[]` 按 y 是否为有效数值切分为连续段。
 * null / undefined / NaN / Infinity 视为断点，断点不进入任何段，
 * 从而保证不会跨越空档生成虚假曲线。
 *
 * @param {{x:number, y:number|null}[]} points
 * @returns {{x:number, y:number}[][]}  连续段数组，每段内部 y 全为有效数值
 */
export function splitContinuousSegments(points) {
  if (!Array.isArray(points)) return []

  const segments = []
  let current = []

  for (const point of points) {
    if (point && isFiniteNumber(point.y)) {
      current.push({ x: point.x, y: point.y })
    } else if (current.length) {
      segments.push(current)
      current = []
    }
  }
  if (current.length) segments.push(current)

  return segments
}

/**
 * 校验单段 x 严格递增，违反时抛出可读错误（便于测试定位）。
 */
function assertStrictlyIncreasing(points) {
  for (let i = 1; i < points.length; i += 1) {
    if (!(points[i].x > points[i - 1].x)) {
      throw new Error(
        `pchipInterpolate: x 必须严格递增，但在索引 ${i} 处出现 ${points[i - 1].x} → ${points[i].x}`
      )
    }
  }
}

/**
 * 计算 PCHIP 单调斜率（Fritsch–Carlson 限制导数）。
 *
 * 核心思想：在数据非单调处把导数压到 0，从而保证插值结果在每对相邻
 * 节点之间保持单调，不会 overshoot。
 *
 * @param {number[]} h 区间宽度 h[i] = x[i+1] - x[i]
 * @param {number[]} delta 差商 delta[i] = (y[i+1] - y[i]) / h[i]
 * @returns {number[]} 长度为 n 的节点导数数组
 */
function computeMonotoneSlopes(h, delta) {
  const n = h.length + 1 // 节点数
  const slopes = new Array(n).fill(0)

  if (n === 1) return slopes
  if (n === 2) {
    slopes[0] = delta[0]
    slopes[1] = delta[0]
    return slopes
  }

  for (let i = 1; i < n - 1; i += 1) {
    const d0 = delta[i - 1]
    const d1 = delta[i]

    // 相邻差商异号或为零 → 极值点，导数置 0（避免过冲的关键）
    if (d0 * d1 <= 0) {
      slopes[i] = 0
    } else {
      // 加权调和平均（Fritsch–Carlson）
      const w0 = 2 * h[i] + h[i - 1]
      const w1 = h[i] + 2 * h[i - 1]
      slopes[i] = (w0 + w1) / (w0 / d0 + w1 / d1)
    }
  }

  // 端点斜率：单侧三点公式 + 限幅
  slopes[0] = endpointSlope(h[0], h[1], delta[0], delta[1])
  slopes[n - 1] = endpointSlope(h[n - 2], h[n - 3], delta[n - 2], delta[n - 3])

  return slopes
}

/**
 * 端点导数：用单侧三点公式估计，并做 Fritsch–Carlson 限幅，
 * 防止端点处出现超出相邻差商的斜率。
 */
function endpointSlope(h0, h1, d0, d1) {
  let slope = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)

  // 符号与首段差商不一致 → 归零
  if (slope * d0 <= 0) {
    slope = 0
  } else if (d0 * d1 < 0 && Math.abs(slope) > Math.abs(3 * d0)) {
    // 端点处若差商反号，斜率不得超过首段差商的 3 倍
    slope = 3 * d0
  }

  return slope
}

/** 三次 Hermite 基函数求值（t ∈ [0,1]） */
function hermite(y0, y1, m0, m1, h, t) {
  const t2 = t * t
  const t3 = t2 * t
  const h00 = 2 * t3 - 3 * t2 + 1
  const h10 = t3 - 2 * t2 + t
  const h01 = -2 * t3 + 3 * t2
  const h11 = t3 - t2
  return h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1
}

/**
 * 对单段（x 严格递增、y 全为有效数值）做 PCHIP 插值。
 *
 * @param {{x:number, y:number}[]} points 单段有效点，长度 ≥ 1
 * @param {number} samplesPerSegment 每段采样数（不含左端点），默认 12
 * @returns {{x:number, y:number}[]} 插值后的显示曲线点
 */
export function pchipInterpolate(points, samplesPerSegment = DEFAULT_SAMPLES_PER_SEGMENT) {
  if (!Array.isArray(points) || points.length === 0) return []

  // 单点：无法插值，原样保留（返回新对象，不引用原数组元素）
  if (points.length === 1) return [{ x: points[0].x, y: points[0].y }]

  assertStrictlyIncreasing(points)

  // 两点：PCHIP 退化为线性，显式走线性分支更直观
  if (points.length === 2) {
    return linearInterpolate(points, samplesPerSegment)
  }

  const count = points.length
  const h = new Array(count - 1)
  const delta = new Array(count - 1)
  for (let i = 0; i < count - 1; i += 1) {
    h[i] = points[i + 1].x - points[i].x
    delta[i] = (points[i + 1].y - points[i].y) / h[i]
  }

  const slopes = computeMonotoneSlopes(h, delta)
  const steps = Math.max(1, Math.floor(samplesPerSegment))
  const result = []

  for (let i = 0; i < count - 1; i += 1) {
    const { x: x0, y: y0 } = points[i]
    const { y: y1 } = points[i + 1]

    // 每段输出左端点，最后一段补上右端点，保证节点被精确经过
    for (let s = 0; s < steps; s += 1) {
      const t = s / steps
      result.push({ x: x0 + h[i] * t, y: hermite(y0, y1, slopes[i], slopes[i + 1], h[i], t) })
    }
  }

  const last = points[count - 1]
  result.push({ x: last.x, y: last.y })

  return result
}

/**
 * 两点线性插值（PCHIP 在 n=2 时的退化情形）。
 */
function linearInterpolate(points, samplesPerSegment) {
  const [{ x: x0, y: y0 }, { x: x1, y: y1 }] = points
  const steps = Math.max(1, Math.floor(samplesPerSegment))
  const result = []
  for (let s = 0; s < steps; s += 1) {
    const t = s / steps
    result.push({ x: x0 + (x1 - x0) * t, y: y0 + (y1 - y0) * t })
  }
  result.push({ x: x1, y: y1 })
  return result
}

/**
 * 面向组件的主入口：接收「可能含 null 的连续网格点」，
 * 自动分段 + 逐段 PCHIP + 合并输出。
 *
 * 入参约定：`points = [{ x, y }, ...]`，y 可为 null（表示该 x 无数据）。
 * 返回：`{ displayPoints, segments }`，二者均为新数组，原始 points 不被修改。
 *
 * @param {{x:number, y:number|null}[]} points
 * @param {{samplesPerSegment?:number}} options
 */
export function interpolateSeries(points, options = {}) {
  const { samplesPerSegment = DEFAULT_SAMPLES_PER_SEGMENT } = options
  const segments = splitContinuousSegments(points)

  const displayPoints = []
  for (const segment of segments) {
    displayPoints.push(...pchipInterpolate(segment, samplesPerSegment))
  }

  return { displayPoints, segments }
}

export { DEFAULT_SAMPLES_PER_SEGMENT }
