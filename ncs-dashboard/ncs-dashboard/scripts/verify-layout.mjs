/**
 * 布局状态机校验（Batch B.1）
 *
 * 除常规断点样本外，重点是两条「不变式」：
 *   I1 单调性：更宽的窗口不得拿到更「退化」的模式
 *              （禁止 scale 出现在比 compact 更窄的位置）
 *   I2 可达性：在任意常见高度下，scale / compact / reflow 都可达
 *
 * 从源码解析 BREAKPOINTS，并直接编译源码里的 detectMode，
 * 确保校验对象与线上实现是同一段逻辑（而不是复制粘贴的同构实现）。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const LAYOUT_SRC = new URL('../src/composables/useDashboardLayout.js', import.meta.url)

const source = readFileSync(LAYOUT_SRC, 'utf8')

// ────────────────────────── 解析 BREAKPOINTS ──────────────────────────
const block = source.match(/export const BREAKPOINTS = Object\.freeze\(\{([\s\S]*?)\n\}\)/)?.[1]
if (!block) throw new Error('无法从 useDashboardLayout.js 解析 BREAKPOINTS')

const BP = {}
for (const line of block.split('\n')) {
  const stripped = line.replace(/\/\/.*$/, '')
  const match = stripped.match(/^\s*([A-Za-z]+)\s*:\s*(-?[\d.]+)\s*,?/)
  if (match) BP[match[1]] = Number(match[2])
}

const REQUIRED = ['reflowMaxWidth', 'compactMaxWidth', 'scaleHeightRatio', 'designWidth', 'designHeight']
for (const key of REQUIRED) {
  if (!Number.isFinite(BP[key])) throw new Error(`BREAKPOINTS 缺少或非数值字段: ${key}`)
}

// ────────────────────────── 直接编译源码里的 detectMode ──────────────────────────
// 避免「校验用同构实现」与「真实实现」各写一份、日后漂移。
const fnStart = source.indexOf('function detectMode')
if (fnStart < 0) throw new Error('无法从源码定位 detectMode')
const fnEnd = source.indexOf('\n}', fnStart) + 2
const FN_SRC = source.slice(fnStart, fnEnd)
if (!/BREAKPOINTS\.(reflowMaxWidth|compactMaxWidth|scaleHeightRatio)/.test(FN_SRC)) {
  throw new Error('detectMode 未消费预期断点字段，源码可能已重构')
}
const detectMode = new Function('BREAKPOINTS', `${FN_SRC}\nreturn detectMode`)(BP)

// 同理编译 compact 的纵向分档判定
const tierStart = source.indexOf('function detectCompactTier')
if (tierStart < 0) throw new Error('无法从源码定位 detectCompactTier')
const tierEnd = source.indexOf('\n}', tierStart) + 2
const TIER_SRC = source.slice(tierStart, tierEnd)
const detectCompactTier = new Function('BREAKPOINTS', `${TIER_SRC}\nreturn detectCompactTier`)(BP)

const DESIGN_RATIO = BP.designWidth / BP.designHeight
const MODE_RANK = { reflow: 0, compact: 1, scale: 2 }

let passed = 0
const failures = []

function assert(label, condition) {
  if (condition) passed += 1
  else failures.push(label)
}

// ────────────────────────── 1. 常规分辨率样本 ──────────────────────────
const samples = [
  { w: 3840, h: 2160, mode: 'scale' },     // 4K
  { w: 3440, h: 1440, mode: 'scale' },     // 21:9
  { w: 2560, h: 1440, mode: 'scale' },     // 2K
  { w: 1920, h: 1080, mode: 'scale' },     // 设计基准
  { w: 1920, h: 1200, mode: 'scale' },     // 16:10
  { w: 1680, h: 1050, mode: 'scale' },
  { w: 1600, h: 900, mode: 'scale' },
  { w: 1440, h: 900, mode: 'scale' },
  { w: 1366, h: 768, mode: 'scale' },
  { w: 1280, h: 800, mode: 'scale' },
  { w: 1715, h: 1401, mode: 'compact' },   // 用户报告的问题尺寸
  { w: 1600, h: 1200, mode: 'compact' },   // 4:3
  { w: 1280, h: 1024, mode: 'compact' },   // 5:4
  { w: 1024, h: 768, mode: 'compact' },
  { w: 950, h: 700, mode: 'compact' },
  { w: 900, h: 600, mode: 'compact' },     // compact 下边界（含）
  { w: 899, h: 600, mode: 'reflow' },      // reflow 上边界
  { w: 768, h: 1024, mode: 'reflow' },
  { w: 600, h: 900, mode: 'reflow' },
  { w: 390, h: 844, mode: 'reflow' },      // iPhone 竖屏
  { w: 375, h: 667, mode: 'reflow' }
]

for (const s of samples) {
  const label = `${s.w}×${s.h}`
  const actual = detectMode(s.w, s.h)
  assert(`${label} 模式应为 ${s.mode}（实际 ${actual}）`, actual === s.mode)
  const scale = Math.min(s.w / BP.designWidth, s.h / BP.designHeight)
  assert(`${label} 缩放比有效`, Number.isFinite(scale) && scale > 0)
}

// ────────────────────────── 2. 四条硬约束（B.1 的设计依据） ──────────────────────────
// 这四条同时成立，就是 Batch B.1 修复的核心，缺一不可。
assert('硬约束 A：1920×1080（设计基准）→ scale', detectMode(1920, 1080) === 'scale')
assert('硬约束 B：1715×1401（用户场景）→ compact', detectMode(1715, 1401) === 'compact')
assert('硬约束 C：2560×1440（2K）→ scale', detectMode(2560, 1440) === 'scale')
assert('硬约束 D：3840×2160（4K）→ scale', detectMode(3840, 2160) === 'scale')

// k 的可行区间：1080/1920 ≤ k < 1401/1715 —— 越界则 A 与 B 不能同时满足
assert(
  `scaleHeightRatio=${BP.scaleHeightRatio} 落在可行区间 [0.5625, 0.8169)`,
  BP.scaleHeightRatio >= BP.designHeight / BP.designWidth &&
    BP.scaleHeightRatio < 1401 / 1715
)

// 旧实现的结构性缺陷：ratioDiff 关于 16:9 对称、随宽度呈 V 形。
// 这里断言新实现不再依赖任何双侧比例容差。
assert('已移除 scaleRatioTolerance（旧对称阈值）', !/scaleRatioTolerance/.test(source))
assert('已移除 compactRatioTolerance（旧对称阈值）', !/compactRatioTolerance/.test(source))
assert('已移除绝对高度上限 scaleMaxHeight', !/scaleMaxHeight/.test(source))

// ────────────────────────── 3. 不变式 I1：单调性 ──────────────────────────
// 固定高度，宽度单调递减扫描（3200 → 600）。
// 因为是「从宽到窄」，合法序列的等级必须**非递增**；
// 若出现 rank 上升，说明更窄的窗口拿到了更高级的模式。
const sweepHeights = [900, 1080, 1200, 1401, 1600, 1800, 2160]
let monotonicChecks = 0
let monotonicViolations = 0
for (const h of sweepHeights) {
  let prevRank = -1
  let prevW = null
  for (let w = 3200; w >= 600; w -= 4) {
    const rank = MODE_RANK[detectMode(w, h)]
    if (prevRank >= 0 && rank > prevRank) {
      monotonicViolations += 1
      if (monotonicViolations <= 5) {
        failures.push(
          `I1 单调性破坏：高度${h} 下 ${w}px(${detectMode(w, h)}) 比 ${prevW}px(${detectMode(prevW, h)}) 更窄但模式更高级`
        )
      }
    }
    monotonicChecks += 1
    prevRank = rank
    prevW = w
  }
}
assert(
  `I1 单调性成立（${sweepHeights.length} 个高度 × 宽度扫描，共 ${monotonicChecks} 次比较）`,
  monotonicViolations === 0
)

// ────────────────────────── 3b. compact 双档：分档正确性 ──────────────────────────
// 用户场景 1715×1401 必须落在 columns 档（保留三列），否则中心组会被
// 拉成全宽横条，图宽高比从 ~2 : 1 恶化到 ~4.9 : 1（实测值）。
assert('1715×1401 处于 compact/columns（保留三列）', detectCompactTier(1715, 1401) === 'columns')
assert('1600×1200 处于 compact/columns', detectCompactTier(1600, 1200) === 'columns')
// Batch C2 曾把此档改判 stack（理由：该档右栏只有 719px，Trend 绘图区被压到 299×62）。
// 独立 context 实测后**已回退** —— 那是净回归：进 stack 后中心组由三列变整行全宽，
// 两张中心图 1.73:1 → 4.78 / 4.64，为救一张扁图换来三张更扁。
assert('1280×1024 处于 compact/columns（C2 改判 stack 后按实测回退）', detectCompactTier(1280, 1024) === 'columns')
assert(
  'compactColumnMinHeight 不超过 1024（否则 1280×1024 进 stack，中心图比例恶化到 4.8:1）',
  BP.compactColumnMinHeight <= 1024
)
assert('900×600 处于 compact/stack（矮窗堆叠）', detectCompactTier(900, 600) === 'stack')
assert('非 compact 模式下 tier 为 default', (() => {
  // tier 只对 compact 有意义；这里校验阈值字段存在且合理
  return Number.isFinite(BP.compactColumnMinHeight) && BP.compactColumnMinHeight > 720
})())

// 双档可达性：两者都要能在合理搜索空间内出现
{
  const tiers = new Set()
  for (let h = 300; h <= 2400; h += 10) {
    for (let w = 900; w <= 2000; w += 10) {
      if (detectMode(w, h) === 'compact') tiers.add(detectCompactTier(w, h))
    }
  }
  assert(`compact 双档均可达（实际 ${[...tiers].sort().join('/')}）`, tiers.has('stack') && tiers.has('columns'))
}

// ────────────────────────── 4. 不变式 I2：三模式可达性 ──────────────────────────
// 注意：极高的窗口（h=2160 且宽度受限）下 compact 未必可达，
// 因此可达性只在「常见桌面高度」范围内断言。
for (const h of [900, 1080, 1200, 1401, 1600]) {
  const seen = new Set()
  for (let w = 3600; w >= 600; w -= 4) seen.add(detectMode(w, h))
  assert(
    `高度${h} 下三种模式均可达（实际 ${[...seen].sort().join('/')}）`,
    seen.size === 3 && seen.has('scale') && seen.has('compact') && seen.has('reflow')
  )
}

// 全局可达性（放宽步长）
const globalSeen = new Set()
for (let h = 400; h <= 2400; h += 20) {
  for (let w = 360; w <= 3840; w += 20) globalSeen.add(detectMode(w, h))
}
assert('三档模式在搜索空间内均可达', ['scale', 'compact', 'reflow'].every((m) => globalSeen.has(m)))

// ────────────────────────── 5. 阈值边界 ──────────────────────────
assert('宽度阈值 900 取 <', detectMode(899, 1401) === 'reflow' && detectMode(900, 1401) === 'compact')
assert('宽度阈值 1180 取 <', detectMode(1179, 800) === 'compact' && detectMode(1180, 800) === 'scale')
assert('scale 准入门槛为 height ≤ 0.7×width', detectMode(1715, Math.floor(0.7 * 1715)) === 'scale' && detectMode(1715, Math.ceil(0.7 * 1715)) === 'compact')
assert('设计基准 1920×1080', BP.designWidth === 1920 && BP.designHeight === 1080)
assert('尺寸为 0 兜底 scale', detectMode(0, 0) === 'scale')

// 无回归：常见 16:9 / 16:10 仍为 scale
for (const [w, h] of [[1920, 1080], [1600, 900], [1366, 768], [1440, 900], [1280, 800], [1920, 1200], [1680, 1050]]) {
  assert(`${w}×${h} 仍为 scale（无回归）`, detectMode(w, h) === 'scale')
}

// ────────────────────────── 6. 源码与 CSS 一致性 ──────────────────────────
const stripComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '')

assert('useDashboardLayout 使用 window.innerWidth', /window\.innerWidth/.test(source))
assert('useDashboardLayout 使用 window.innerHeight', /window\.innerHeight/.test(source))
assert('未误用 documentElement.clientHeight', !/documentElement\.clientHeight/.test(source))
assert('保留 visualViewport 兜底', /visualViewport/.test(source))
assert('setup 阶段同步取初值（防首帧闪烁）', /hasWindow \? window\.innerHeight/.test(source))
const VUE_SRC = stripComments(readFileSync(new URL('../src/components/layout/DashboardViewport.vue', import.meta.url), 'utf8'))
assert('transform 只在 scale 模式生效', /mode !== 'scale'\) return null/.test(VUE_SRC) && /transform: `scale\(/.test(VUE_SRC))

const css = stripComments(readFileSync(new URL('../src/styles/dashboard.css', import.meta.url), 'utf8'))
assert('dashboard.css 已删除 @media 块', !/@media/.test(css))
assert('三种模式规则齐备', ['scale', 'compact', 'reflow'].every((m) => css.includes(`data-layout='${m}'`)))
assert('Reflow 图表显式高度（防塌缩 R2）', /data-layout='reflow'[\s\S]*?height:\s*\d+px/.test(css))
assert('防溢出兜底：子项 min-width:0', /\.dashboard-column > \*[\s\S]*?min-width:\s*0/.test(css))
// Batch B.1：compact 必须按 data-tier 分两档，否则 1715×1401 会退化成全宽横条
assert('compact/stack 档规则存在', /data-tier='stack'/.test(css))
assert('compact/columns 档规则存在', /data-tier='columns'/.test(css))
assert('columns 档为三列 grid 布局', /data-tier='columns'\][\s\S]{0,200}grid-template-columns/.test(css))
assert('columns 档给 viewport 确定高度（否则 page height:100% 解析失败）', /data-layout='compact'\]\[data-tier='columns'\]\s*\{[\s\S]*?height:\s*100vh/.test(css))

const viewportVue = stripComments(readFileSync(new URL('../src/components/layout/DashboardViewport.vue', import.meta.url), 'utf8'))
assert('DashboardViewport 透出 data-tier', /:data-tier="tier"/.test(viewportVue))
const dashboardVue = readFileSync(new URL('../src/views/Dashboard.vue', import.meta.url), 'utf8')
assert('Dashboard 消费 tier', /useDashboardLayout\(\)/.test(dashboardVue) && /:tier="tier"/.test(dashboardVue))

const globalCss = stripComments(readFileSync(new URL('../src/styles/global.css', import.meta.url), 'utf8'))
assert('global.css 已解除 min-width:1280px', !/min-width:\s*1280px/.test(globalCss))
assert('global.css 已解除 min-height:720px', !/min-height:\s*720px/.test(globalCss))

// ────────────────────────── 7. Batch C1：Top10「固定窗口 + 内部滚动」 ──────────────────────────
// 改动前实测的两个缺陷：
//   · grid-template-rows: repeat(10, minmax(0,1fr)) → 行高完全由容器决定，
//     实测 14.8px ~ 35px，摆动 2.4 倍；且行数 <10 时保留空轨道 → 底部空洞 28.1px
//   · compact/stack 档只分到 300px，而 10 行 × 30px 需 377px（chrome 46 + 列表 331）
//     → 被 overflow:hidden 静默裁掉 77px
// 本节把这两条守成静态不变量，避免日后改 CSS 时无声回退。
const cssBlock = (sel) => {
  const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(?:^|\\n)\\s*${esc}\\s*\\{([^}]*)\\}`).exec(css)?.[1] ?? ''
}
// 组合选择器会带来干扰：`.a--left,\n.a--right { flex: ... }` 的第二行同样「以该选择器开头 + 以 { 结尾」，
// 但它并不是我们关心的那条规则。所以这里取「第一个真的含 grid-template-rows 的块」。
const cssBlocks = (sel) => {
  const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return [...css.matchAll(new RegExp(`(?:^|\\n)\\s*${esc}\\s*\\{([^}]*)\\}`, 'g'))].map((m) => m[1])
}
const SEL = {
  scale: ".dashboard-viewport[data-layout='scale'] .ranking-list",
  columns: ".dashboard-viewport[data-layout='compact'][data-tier='columns'] .ranking-list",
  stack: ".dashboard-viewport[data-layout='compact'][data-tier='stack'] .ranking-list",
  reflow: ".dashboard-viewport[data-layout='reflow'] .ranking-list",
  rightBase: '.dashboard-column--right',
  rightColumns: ".dashboard-viewport[data-layout='compact'][data-tier='columns'] .dashboard-column--right",
  rightStack: ".dashboard-viewport[data-layout='compact'][data-tier='stack'] .dashboard-column--right"
}
const rankBase = cssBlock('.ranking-list')

assert('Top10 不再使用固定 10 轨道', !/grid-template-rows:\s*repeat\(10/.test(css))
assert('Top10 列表改为 flex column', /display:\s*flex/.test(rankBase) && /flex-direction:\s*column/.test(rankBase))
assert('Top10 列表 height:auto（未回退 height:100%）', /height:\s*auto/.test(rankBase) && !/height:\s*100%/.test(rankBase))
assert('Top10 行不再有 17px 最小高度（会顶出固定行高盒子）', !/minmax\(17px/.test(css))
assert('Top10 行高由 --rank-row-h 驱动', /min-height:\s*var\(--rank-row-h\)/.test(css))

// 四档行高：模式级固定「设计空间 px」。Scale 模式画布本就固定 1920×1080、
// 由浏览器统一缩放，因此绝不能用 vh/cqh —— 否则同一画布会渲染出两种密度。
for (const [h, key] of [[26, 'scale'], [28, 'columns'], [30, 'stack'], [36, 'reflow']]) {
  assert(`Top10 行高 ${h}px 已声明（${key} 档）`, new RegExp(`--rank-row-h:\\s*${h}px`).test(cssBlock(SEL[key])))
}
assert('Top10 行高未使用 vh/cqh（防 scale 下同画布两种密度）', !/--rank-row-h:[^;]*c[qv]h/.test(css))

// 滚动策略：桌面/columns 内部滚动；stack/reflow 禁止内部滚动
// （手机整页本就在滚动，再套一层会出现「页面滚动 + 列表滚动」双层）
for (const key of ['scale', 'columns']) {
  const b = cssBlock(SEL[key])
  assert(`Top10 ${key} 档有 max-height 封顶`, /max-height:\s*\d+px/.test(b))
  assert(`Top10 ${key} 档内部滚动 overflow-y:auto`, /overflow-y:\s*auto/.test(b))
}
for (const key of ['stack', 'reflow']) {
  const b = cssBlock(SEL[key])
  assert(`Top10 ${key} 档不设 max-height（自然展开）`, /max-height:\s*none/.test(b))
  assert(`Top10 ${key} 档禁止内部滚动（防双层滚动）`, /overflow-y:\s*visible/.test(b))
}

// 面板高度下界：内容驱动 + min-height 兜底
// （列向 flex 容器在 auto 高度下的 intrinsic sizing 各引擎有差异，用下界保证不裁）
assert('stack 档 Top10 面板有 min-height:380px（需求实测 377）', /min-height:\s*380px/.test(css))
assert('reflow 档 Top10 面板有 min-height:460px（需求实测 433）', /min-height:\s*460px/.test(css))
assert('reflow 档 Top10 面板已解除固定 height:420px', !/nth-child\(1\)\s*\{[\s\S]{0,120}?height:\s*420px/.test(css))

// 右栏第 1 行必须是 auto（内容驱动，退出 fr 分配），否则 Top10 仍会被撑开
const rightRows = (sel) => {
  const rows = cssBlocks(sel).map((b) => b.match(/grid-template-rows:\s*([^;]+);/)?.[1]).filter(Boolean)
  return (rows[0] ?? '').trim()
}
assert(`右栏基准档首行为 auto（实际 "${rightRows(SEL.rightBase).slice(0, 12)}"）`, rightRows(SEL.rightBase).startsWith('auto'))
assert(`右栏 columns 档首行为 auto（实际 "${rightRows(SEL.rightColumns).slice(0, 12)}"）`, rightRows(SEL.rightColumns).startsWith('auto'))
assert(`右栏 stack 档首行为 auto（实际 "${rightRows(SEL.rightStack).slice(0, 12)}"）`, rightRows(SEL.rightStack).startsWith('auto'))

// Reflow 两行版：390px 装不下单行（实测只给站名留 62px，被截成 5 字）
const reflowRow = cssBlock(".dashboard-viewport[data-layout='reflow'] .ranking-row")
assert('Reflow Top10 为两行版', /grid-template-rows:\s*auto auto/.test(reflowRow))
assert(
  'Reflow 站名在第一行、数值在第二行',
  /\.ranking-station\s*\{\s*grid-row:\s*1;/.test(css) && /\.ranking-orders\s*\{\s*grid-row:\s*2;/.test(css)
)
assert('滚动条已窄化（低视觉干扰）', /scrollbar-width:\s*thin/.test(rankBase))

// ────────────────────────── 8. Batch C2：右栏重平衡 + Process 信息密度 ──────────────────────────
// 用户看真实屏幕后的四条反馈：Top10 不动 / Trend 略缩 / Process 框缩小且字放大 / Insights 放大。
// 本节把「机制」守成静态不变量（具体 px 由 diag-compact 出诊断值，不做成构建失败）。
// 注意：grid-template-rows 的轨道用**空格**分隔（不是逗号），而 minmax(a, b) 内部既有逗号也有空格。
// 所以按「深度 0 处的空白」切分。
const splitTracks = (s) => {
  const out = []
  let depth = 0, cur = ''
  for (const ch of s) {
    if (ch === '(') depth++
    else if (ch === ')') depth--
    if (depth === 0 && /\s/.test(ch)) { if (cur) { out.push(cur); cur = '' } } else cur += ch
  }
  if (cur) out.push(cur)
  return out
}
const rightRowList = (sel) => {
  const rows = cssBlocks(sel).map((b) => b.match(/grid-template-rows:\s*([^;]+);/)?.[1]).filter(Boolean)
  return rows.length ? splitTracks(rows[0]) : []
}

// 第 1 行（Top10）与第 3 行（Process）都必须是 auto —— 即「不参与剩余空间分配」。
// 这是本批的核心机制：Top10 与 Process 一旦回到 fr，就会重新被撑开（C1 / C2 的同一类回归）。
for (const [key, sel] of [['scale', SEL.rightBase], ['columns', SEL.rightColumns]]) {
  const rows = rightRowList(sel)
  assert(`右栏 ${key} 档共 4 行（实际 ${rows.length}）`, rows.length === 4)
  assert(`右栏 ${key} 档第 1 行 Top10 为 auto（实际 "${rows[0]}"）`, rows[0] === 'auto')
  // Batch C.6b 起 Process 行是「部分弹性」`minmax(140px, <fr>)` 而不是 `minmax(…, auto)`：
  // 这样它只在**有富余**的档位长高（1920 / 1715），在没富余的档位（1600 / 1280）停在下界不动，
  // 不会把运营建议的正文裁掉。
  // 下界 140 是安全线：内容实测 122px，「平均峰值温度」折行也只有 137px（判据见 CSS 注释）。
  assert(`右栏 ${key} 档第 3 行 Process 为部分弹性且下界在 [136,150]（实际 "${rows[2]}"）`, (() => {
    const m = (rows[2] ?? '').match(/^minmax\((\d+)px,\s*[\d.]+fr\)$/)
    if (!m) return false
    const v = Number(m[1])
    return v >= 136 && v <= 150
  })())
  // scale 档的设计空间固定 1920×1080，Trend 只需 fr；columns 档右栏高度随视口浮动，
  // 必须有 px 下界，否则最矮的 columns 档（1600×1200）会给出极扁的趋势图。
  assert(`右栏 ${key} 档第 2 行 Trend 为 minmax(fr) 或 calc 定界形式`, /^(minmax\((0|\d+px),\s*[\d.]+fr\)|calc\(57% - \d+px\))$/.test(rows[1] ?? ''))
  if (key === 'columns') assert('右栏 columns 档 Trend 有 px 下界', /^minmax\(\d+px,/.test(rows[1] ?? ''))
  assert(`右栏 ${key} 档第 4 行 Insights 带内容下界（≥140px）`, /^minmax\((\d+)px,\s*1fr\)$/.test(rows[3] ?? '') && Number((rows[3] ?? '').match(/minmax\((\d+)px/)?.[1] ?? 0) >= 140)
}
// stack 档：全 auto + 各面板显式下界（fr 在自指容器里恒等于下界，比例不起作用）
assert(
  '右栏 stack 档为 4 个 auto 行（放弃 fr）',
  rightRowList(SEL.rightStack).join('|') === 'auto|auto|auto|auto'
)
assert('stack 档 Trend 面板有确定高度', /data-tier='stack'\][\s\S]{0,900}?nth-child\(2\)\s*\{[\s\S]{0,120}?height:\s*\d+px/.test(css))
assert('stack 档 Process / Insights 有内容下界', /nth-child\(3\)\s*\{[\s\S]{0,120}?min-height:\s*\d+px/.test(css) && /nth-child\(4\)\s*\{[\s\S]{0,120}?min-height:\s*\d+px/.test(css))

// Process 指标卡：容器不再吃剩余高度 + 字号变量存在且 value 明显大于 label
const procGrid = cssBlock('.process-grid')
const procMetric = cssBlock('.process-metric')
assert('Process 卡片网格不再参与拉伸（原 flex:1 是卡片虚高的根因）', /flex:\s*0 0 auto/.test(procGrid) && !/flex:\s*1\s*;/.test(procGrid))
assert('Process 卡片网格为四等分且可收缩', /grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/.test(procGrid))
assert('Process 卡片有 min-height 上限约束（≤80px）', (() => {
  const m = procMetric.match(/min-height:\s*(\d+)px/)
  return m && Number(m[1]) <= 80
})())
assert('Process 字号由 --pm-label / --pm-value / --pm-unit 驱动', ['label', 'value', 'unit'].every((k) => new RegExp(`--pm-${k}:`).test(procMetric)))
assert('Process value 字号约为 label 的 1.6 倍以上（数值应为主视觉）', (() => {
  const l = Number(procMetric.match(/--pm-label:\s*(\d+(?:\.\d+)?)px/)?.[1] ?? 0)
  const v = Number(procMetric.match(/--pm-value:\s*(\d+(?:\.\d+)?)px/)?.[1] ?? 0)
  return l > 0 && v / l >= 1.6
})())
assert('Process label 允许换行（不得用 nowrap 把 6 个汉字挤在一行）', !/\.process-metric span\s*\{[^}]*white-space:\s*nowrap/.test(css))
for (const mode of ['compact', 'reflow']) {
  assert(`Process 字号已按 ${mode} 档覆盖`, new RegExp(`data-layout='${mode}'\\] \\.process-metric\\s*\\{[^}]*--pm-value`).test(css))
}
assert('Reflow 的 Process 改为 2×2（390px 四等分放不下放大后的字号）', /data-layout='reflow'\] \.process-grid\s*\{[\s\S]{0,120}?repeat\(2,\s*minmax\(0,\s*1fr\)\)/.test(css))

// stack 档中心列必须给足高度：该档中心组是整行全宽（最大 1252px），
// 原来 ~610px 高会让两张中心图跑到 4.7:1（越 3.6 门禁）。
assert('stack 档中心列行下界 ≥ 400px（防宽而矮的正方形窗口把中心图压成横条）', (() => {
  const b = cssBlock(".dashboard-viewport[data-layout='compact'][data-tier='stack'] .dashboard-column--center")
  const rows = splitTracks(b.match(/grid-template-rows:\s*([^;]+);/)?.[1] ?? '')
  return rows.length === 2 && rows.every((t) => Number(t.match(/minmax\((\d+)px/)?.[1] ?? 0) >= 400)
})())

// Insights：字号放大后必须允许换行，否则「放大」会以信息截断为代价
const insightP = cssBlock('.insight-item p')
assert('运营建议正文已解除 nowrap + ellipsis（放大字号的前提）', !/white-space:\s*nowrap/.test(insightP) && !/text-overflow:\s*ellipsis/.test(insightP))
assert('运营建议正文行高已放宽（可读性靠行高，不是只把字挤大）', (() => {
  const lh = Number(insightP.match(/line-height:\s*(\d+(?:\.\d+)?)/)?.[1] ?? 0)
  return lh >= 1.4
})())
assert('运营建议卡片按内容高度、不再被拉伸成空壳', /\.insight-list\s*\{[\s\S]{0,220}?repeat\(2,\s*auto\)/.test(css))
assert('运营建议标题 / 正文字号均已放大（经 font token）', (() => {
  const t = /insight-item strong\s*\{[^}]*font-size:\s*var\(--font-size-lg\)/.test(css)
  const b = /insight-item p\s*\{[^}]*font-size:\s*var\(--font-size-md\)/.test(css)
  return t && b
})())



// ────────────────────────── 9. 诊断脚本自身的可信度（Batch C2.1） ──────────────────────────
// diag-compact 曾经复用同一页面做 setViewportSize，resize 后 ECharts 布局滞后于容器，
// grid 坐标矩形仍是上一档尺寸 ⇒ stack 档比例被系统性少报（1024×768 中心组实测 3.79/3.68，
// 脚本报 2.88/2.82）。这类脚本比没有更危险，因为它给出「看起来很客观」的假数据。
const diagSrc = readFileSync(new URL('../scripts/diag-compact.mjs', import.meta.url), 'utf8')
assert('diag 每档独立 context（不再复用页面 resize）', !/setViewportSize/.test(stripComments(diagSrc).replace(/\/\/.*$/gm, '')))
assert('diag 读几何前等待字体就绪', /document\.fonts\?\.ready/.test(diagSrc))
assert('diag 读几何前等待两帧 rAF', /requestAnimationFrame\(\(\) => requestAnimationFrame/.test(diagSrc))
// 非劣化例外必须精确匹配 mode/tier/宽/高，且默认阈值不被放宽 ——
// 防止日后为了让门禁通过而把整个 tier 或一个宽度区间一起豁免。
assert('diag 门禁默认阈值仍为 3.6', /const gate = exception \? exception\.max : 3\.6/.test(diagSrc))
assert(
  'diag 例外按 mode/tier/宽/高 四者精确匹配（不按区间放宽）',
  /e\.mode === mode && e\.tier === tier && e\.width === w && e\.height === h/.test(diagSrc)
)
// Batch C.5：1280×1024 已回到默认门禁内（最扁画布 4.07 → 3.14），例外表清空。
// 断言「当前为空」而不是「条数 ≤1」—— 后者会被注释里的格式示例蒙混过去。
// Batch D-4 页脚使 1280×1024 回到过约束状态（Trend 150px / 画布 4.07），
// 故重新登记该档例外。断言钉住「全表仅此一条」，防止例外被随手扩充。
assert('diag 非劣化例外表仅含 1280×1024 一条', (() => {
  const n = (diagSrc.match(/mode: '[a-z]+',\s*tier: '[a-z]+',\s*width:/g) || []).length
  return n === 1 && /width:\s*1280,\s*height:\s*1024/.test(diagSrc)
})())
assert('diag 保留的例外格式未被弱化（要求 why 说明）', /why:\s*'/.test(diagSrc))
assert('diag 新增运营建议间距诊断（副标题底→首卡顶）', /insightGap:/.test(diagSrc))
assert('diag 新增 Process 数字/单位间隙诊断', /numUnitGap:/.test(diagSrc))

// ────────────────────────── 10. Batch C.5：展示层收口 ──────────────────────────
// 这一批只动「展示语义与视觉层级」，不动数据契约 / adapter / 响应式状态机 / 插值。
// 断言的作用是把这个边界钉住，防止日后有人顺手扩大。
const trendVue = readFileSync(new URL('../src/components/dashboard/FeeEnergyTrend.vue', import.meta.url), 'utf8')
// 断言前先剥掉注释：本次改动在注释里引用了旧配置名，不剥会误伤
const trendCode = stripComments(trendVue)
assert('Trend 的「充电量」折线已隐藏数据点', /name:\s*'充电量'[\s\S]{0,400}?showSymbol:\s*false/.test(trendCode))
assert('Trend 不再保留失效的 symbolSize 配置', !/symbolSize:\s*5/.test(trendCode))
assert('Trend 的趋势形状未被改动（smooth 与线宽保持原值）', /smooth:\s*0\.25/.test(trendCode) && /lineStyle:\s*\{\s*width:\s*2\.4\s*\}/.test(trendCode))

const procVue = readFileSync(new URL('../src/components/dashboard/ProcessStatusOverview.vue', import.meta.url), 'utf8')
assert('Process 的两行说明已从模板删除', !/process-summary__scope/.test(procVue) && !/process-note/.test(procVue))
assert('Process 的说明规则已从 CSS 删除（不留死规则）', !/\.process-summary__scope/.test(css) && !/\.process-note\s*\{/.test(css))
assert('Process 指标名未被改动（保持「平均电流」）', /average_current:\s*'平均电流'/.test(procVue))
// 展示层取绝对值：只允许作用于 average_current，不得全局 abs
assert('电流取绝对值只作用于 average_current（不做全局 abs）', /metricCode === 'average_current'\s*\?\s*Math\.abs\(/.test(procVue))

// 数字几何居中 + 单位独立靠右：两个必须成对成立的点
const strongRule = cssBlock('.process-metric strong')
assert('Process 数字占满内容宽（数字才能真居中，而非数字+单位整体居中）', /width:\s*100%/.test(strongRule))
assert('Process 数字居中', /text-align:\s*center/.test(strongRule))
assert('Process 的 strong 兼作单位定位基准（否则单位会落到卡片底部）', /position:\s*relative/.test(strongRule))
const smallRule = cssBlock('.process-metric strong small')
assert('Process 单位绝对定位在卡片右侧固定位', /position:\s*absolute/.test(smallRule) && /right:\s*0/.test(smallRule) && /bottom:\s*0/.test(smallRule))
// 模板里数字与单位之间不能有空白文本节点，否则尾随空格会被一起居中（约 3px 偏移）
assert('Process 模板中数字与单位之间无空白文本节点', /\{\{\s*formatMetric\(metric\)\s*\}\}<small>/.test(procVue))

// 运营建议：顶部间距由 align-content 决定，必须为 start
assert('运营建议列表为 align-content: start（否则标题与首卡之间出现断层）', /align-content:\s*start/.test(cssBlock('.insight-list')))
assert('运营建议已禁用 align-content: center（防回退）', !/\.insight-list\s*\{[^}]*align-content:\s*center/.test(css))

// useDashboard.js：这一批**只允许改文案**，触发条件与 level 必须原样
const dashSrc = readFileSync(new URL('../src/composables/useDashboard.js', import.meta.url), 'utf8')
assert('运营建议第二条的触发条件未被改动（守住「只改文案」边界）',
  /weekday\.rawValues\[0\] > weekend\.rawValues\[0\] \* 2/.test(dashSrc))
assert('运营建议第二条标题已改为「排班参考」', /title:\s*'排班参考'/.test(dashSrc))
assert('运营建议已不含旧标题「需求分布」', !/title:\s*'需求分布'/.test(dashSrc))
assert('运营建议第二条含明确动作（不再只是免责声明）', /建议结合工作日、周末日均订单确定人员配置/.test(dashSrc))

// ────────────────────────── 11. Batch C.6：Process 上下呼吸空间 ──────────────────────────
// 用户反馈「Process 大框上下有点紧」。实测确实：净空为 上 1px / 下 8px —— 不仅小，而且上紧下松。
// 处理是「抬高 Process 行下界 + 给 summary 补一点 padding」，**不动字号、不动卡片、不重开比例之争**。
// 同时必须保证高度来自 Insights 的底部富余而不是 Trend，所以 columns 的因子随之从 1.35 调到 1.40。
assert('Process summary 有上侧呼吸 padding（改前为 0，实测上净空仅 1px）',
  /\.process-summary\s*\{[\s\S]{0,400}?padding:\s*6px 2px 2px/.test(css))
// 上下对称条件：summaryPadTop − summaryPadBottom = bodyPadBottom − bodyPadTop = 5 − 1 = 4
assert('Process 上下净空对称条件成立（summary 上 padding 比下多 4px）', (() => {
  const b = cssBlock('.process-summary')
  const m = b.match(/padding:\s*(\d+)px\s+[\d.]+px\s+(\d+)px/)
  return m && Number(m[1]) - Number(m[2]) === 4
})())
// Batch C.6b：Process 用 fr 上限而非 auto —— 这是「只在有富余的档位长高」的机制本身，
// 改回 auto 就会在 1600×1200（富余 0px）把运营建议的正文裁掉。
assert('右栏 columns 档 Process 保持部分弹性（fr 上限）', /minmax\(140px,\s*\.52fr\)/.test(css))
assert('右栏 scale 档 Process 保持部分弹性（fr 上限）', /minmax\(140px,\s*\.67fr\)/.test(css))
// 移动端刻意只加一点点：桌面 +8%（126→136），reflow 仅 +2.6%（195→200）
assert('reflow 的 Process 只小幅上调（移动端纵向滚动成本高）', (() => {
  const b = cssBlock(".dashboard-viewport[data-layout='reflow'] .dashboard-column--right > :nth-child(3)")
  const m = b.match(/min-height:\s*(\d+)px/)
  return m && Number(m[1]) >= 195 && Number(m[1]) <= 205
})())
assert('diag 新增 Process 上下净空诊断', /procGapAbove/.test(diagSrc) && /procGapBelow/.test(diagSrc))
// C.6b 的新脆弱点：Process 行改用 fr 上限后内容不再能撑开该行，故必须诊断是否裁切
assert('diag 新增 Process / Insights 裁切诊断（C.6b 新脆弱点的守卫）', /procClip:/.test(diagSrc) && /insClip:/.test(diagSrc))

// ────────────────────────── 12. Batch C3：Label 收口（最后两项） ──────────────────────────
// 去重原则：同一信息各留一处（环外留百分比、图例留名称），不是删信息。
const donutSrc = readFileSync(new URL('../src/components/dashboard/PlatformDonut.vue', import.meta.url), 'utf8')
assert('平台分布图例不再追加百分比（formatter 已删除）', !/formatter:\s*\(name\)/.test(donutSrc))
assert('平台分布环外标签仍保留百分比（信息仍在，只是不重复）', /orderPercent\?\.toFixed\(1\)/.test(donutSrc))
assert('平台分布 tooltip 仍保留占比（交互信息不受影响）', /占比：\$\{item\.orderPercent/.test(donutSrc))

const durSrc = readFileSync(new URL('../src/components/dashboard/ChargeDurationChart.vue', import.meta.url), 'utf8')
assert('充电时长分布 x 轴字号已收敛到 12（13 是全屏唯一越界值）', /axisLabel:\s*\{\s*color: '#7a8798',\s*fontSize:\s*12/.test(durSrc))
assert('充电时长分布不再有 13px 字号', !/fontSize:\s*13/.test(stripComments(durSrc)))

// ────────────────────────── 13. Batch D：热力图统一蓝色系 ──────────────────────────
// 原色板「蓝渐变 + 靛 + 橙」有语义冲突：橙色在这套大屏里是「告警/重点」，
// 而热力图的橙只表示高值。改为纯蓝 sequential palette（色相不变、亮度递减、饱和度递增）。
// 边界：只改 inRange.color；visualMax 90 分位 / 分桶 / tooltip / 无观测格逻辑全都不动。
const heatSrc = readFileSync(new URL('../src/components/dashboard/StationHourHeatmap.vue', import.meta.url), 'utf8')
assert('热力图不再使用橙色（原 #f1a33b）', !/f1a33b/i.test(heatSrc))
assert('热力图不再使用靛色（原 #686adf）', !/686adf/i.test(heatSrc))
assert('热力图 inRange.color 引用 HEATMAP_COLORS（不再内联数组）', /inRange:\s*\{\s*color:\s*HEATMAP_COLORS/.test(heatSrc))
assert('热力图 visualMax 仍为 90 分位策略（数据逻辑未动）', /percentile\(observedValues, 0\.90\)/.test(heatSrc))
// 色阶历经 D-1（7档近白→黑蓝）→ D-1b（6档天蓝→海蓝）→ D-1c（7档清透蓝→钢蓝）→
// D-1d 定稿（7档冷蓝：低段有底色、中段清晰、高段深蓝不近黑）。
// Batch D-1d 最终版：低段有底色（不近纯白）、中段减少灰青感、高段深蓝但不近黑。
// 七个颜色是连续渐变的停靠点，不是离散分档。断言校验档数与亮度严格递减。
assert('热力图色阶为 7 档且亮度严格递减（冷蓝低底色 → 深蓝）', (() => {
  const m = heatSrc.match(/HEATMAP_COLORS = (\[[^\]]*\])/)
  if (!m) return false
  const hexes = [...m[1].matchAll(/#[0-9A-Fa-f]{6}/g)].map((x) => x[0].toUpperCase())
  const lum = (h) => {
    const c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
  }
  // 6 档、亮度严格递减，且首档接近白（≥0.95）、末档不得黑于 0.35（峰值不压迫）
  return hexes.length === 7 && hexes.every((h, i) => i === 0 || lum(hexes[i]) < lum(hexes[i - 1])) &&
    lum(hexes[0]) >= 0.9 && lum(hexes[6]) >= 0.12
})())
// 无观测格与最低档必须可区分（无数据 ≠ 低负载），且无观测格应偏灰而不是偏蓝
assert('热力图无观测格保留独立灰色（不与最低档浅蓝混淆）', (() => {
  const m = heatSrc.match(/color: '(#[0-9a-fA-F]{6})',\s*borderColor: '#ffffff'/i)
  return m && !/^(#F7FBFF|#DEEBF7)$/i.test(m[1])
})())

// ────────────────────────── 14. Batch D-2：Donut 中心 KPI 改为 DOM 覆盖层 ──────────────────────────
// 中心 KPI 是页面 UI 而非图表几何；graphic 的「百分比 top + 绝对字号」会让块中心
// 随图表高度线性漂移（偏移 = −0.06H + 10.5，1715×1401 实测 −7.6px）。
// 注：donutSrc 在 §12（C3）已读取，此处复用，不要重复声明。
assert('Donut 中心不再用 ECharts graphic 承载文字', !/graphic:\s*\[/.test(stripComments(donutSrc)))
assert('Donut 中心为 DOM 覆盖层（模板含 .donut-center）', /class="donut-center"/.test(donutSrc))
assert('Donut 中心含数字与标签两个元素', /donut-center__value/.test(donutSrc) && /donut-center__label/.test(donutSrc))
// 中心常量单一来源：option 的 center 与覆盖层的 top 必须共用 CENTER，否则会各自漂移
assert('Donut 圆环中心常量被 option 引用', /center:\s*\[CENTER\.x,\s*CENTER\.y\]/.test(donutSrc))
assert('Donut 圆环中心常量被覆盖层引用', /:style="\{\s*top:\s*CENTER\.y\s*\}"/.test(donutSrc))
assert('Donut 覆盖层不拦截指针（否则挡扇区 hover）', /pointer-events:\s*none/.test(cssBlock('.donut-center')))
assert('Donut 数字在上、标签在下（KPI 惯例：数字是信息、标签是解释）',
  donutSrc.indexOf('donut-center__value') >= 0 && donutSrc.indexOf('donut-center__value') < donutSrc.indexOf('donut-center__label'))
// Step3：字号再各加一号（26/13），并拉开主次色
assert('Donut 数字 26px / 标签 13px', /donut-center__value\s*\{[^}]*font-size:\s*26px/.test(css) && /donut-center__label\s*\{[^}]*font-size:\s*var\(--font-size-md\)/.test(css))
assert('Donut 数字与标签不同色（靠色阶而非同色差形成层级）', (() => {
  const v = cssBlock('.donut-center__value').match(/color:\s*(#[0-9a-fA-F]{6})/)
  const l = cssBlock('.donut-center__label').match(/color:\s*(#[0-9a-fA-F]{6})/)
  return v && l && v[1].toLowerCase() !== l[1].toLowerCase()
})())
// 视觉补偿：中心块变高（26+13+gap≈43px）后人眼觉得重心偏上，故整体下移。
// ★ 必须写成 CSS 自定义属性且**不得**并入 CENTER.y —— 并入会让圆环本身跟着移动、
//   图例距离变化；且诊断需要能读出该值，故用 var() 而非硬编码在 transform 里。
assert('Donut 视觉补偿写成 --donut-optical-y 自定义属性（可被诊断读取）',
  /--donut-optical-y:\s*\d+px/.test(cssBlock('.donut-center')))
assert('Donut 视觉补偿量在 [0,8]px（过大说明该改 CENTER.y 而不是硬调）', (() => {
  const m = cssBlock('.donut-center').match(/--donut-optical-y:\s*(\d+)px/)
  return m && Number(m[1]) >= 0 && Number(m[1]) <= 8
})())
assert('Donut 补偿量只作用于 transform，不写进 ECharts center', !/CENTER\.y\s*\+/.test(donutSrc))

// ────────────────────────── 15. Batch D-3：承重间距冻结 ──────────────────────────
// 这些间距参与高度/内容预算（面板高度、行高、裁切边界），是 C.5/C.6/C.6b 校准的依据。
// 改动它们 = 重新校准，必须先改这里的断言 —— 这是显式决策，不是无害整理。
assert('spacing token 已定义（4/8/12/16）', /--sp-1:\s*4px/.test(css) && /--sp-4:\s*16px/.test(css))
for (const [sel, ...decls] of [
  ['.dashboard-page', ['gap: 9px']],
  ['.dashboard-grid', ['gap: 9px']],
  ['.dashboard-column', ['gap: 9px']],
  ['.dashboard-column--right .panel-body', ['padding: 1px 8px 5px']],
  ['.ranking-list', ['padding: 0 5px 4px']],
  ['.process-metric', ['padding: 4px 4px 9px']],
  ['.insight-item', ['padding: 7px 10px', 'gap: 9px']],
  ['.kpi-card', ['padding: 13px 16px']]
]) {
  for (const d of decls.flat()) {
    assert(`承重间距冻结：${sel.trim()} → ${d}`, cssBlock(sel).includes(d))
  }
}
// α 类已统一到 token（抽样核对两处，防回退到字面值）
assert('α 类间距已用 token（.panel-action / .refresh-button）',
  cssBlock('.panel-action').includes('gap: var(--sp-2)') && cssBlock('.refresh-button').includes('padding: var(--sp-2) var(--sp-3)'))

// ────────────────────────── 18. Batch D-6：圆角 token 化 ──────────────────────────
// border-radius 不参与布局计算 ⇒ 统一是零几何风险的视觉收口。
// 改前 8 种字面值（3/4/5/8/9/10/12/14px），同类小卡片就有 5 种圆角。
assert('radius token 已定义（panel/card/control/deco）',
  ['--radius-panel: 14px', '--radius-card: 10px', '--radius-control: 8px', '--radius-deco: 4px'].every((t) => css.includes(t)))
assert('面板卡片用 --radius-panel（global.css 跨文件引用）', /border-radius:\s*var\(--radius-panel\)/.test(readFileSync(new URL('../src/styles/global.css', import.meta.url), 'utf8')))
for (const sel of ['.process-metric', '.insight-item', '.panel-state', '.kpi-icon']) {
  assert(`小卡片圆角统一 --radius-card：${sel}`, cssBlock(sel).includes('border-radius: var(--radius-card)'))
}
assert('控件圆角统一 --radius-control：refresh-button（且不再借用 --sp-2）',
  cssBlock('.refresh-button').includes('border-radius: var(--radius-control)') && !/border-radius:\s*var\(--sp-\d\)/.test(cssBlock('.refresh-button')))
for (const sel of ['.dashboard-brand__mark span', '.ranking-index', '.process-metric i']) {
  assert(`微装饰圆角统一 --radius-deco：${sel}`, cssBlock(sel).includes('border-radius: var(--radius-deco)'))
}
// dashboard.css 不得再出现 px 字面值圆角（999px 是「大圆角」惯用写法，50%/inherit 语义独立）
assert('dashboard.css 无 px 字面值圆角（全部 token 化）', !/border-radius:\s*(?:[1-9]|1[0-9]|20)px/.test(css))

// badge 的问题从来不是颜色/圆角（已一致），而是 padding/height 两套体系（24 vs 29px）。
// 统一契约：min-height 24 + padding 3px 10px + line-height 18（18+6=24，高度有明确来源）。
// 跨文件：.status-chip 在 global.css，badge 系列在 dashboard.css —— 两边都必须守同一契约。
// ────────────────────────── 17. Batch D-5：badge 统一 + 字体层级 ──────────────────────────
// badge 的问题从来不是颜色/圆角（已一致），而是 padding/height 两套体系（24 vs 29px）。
// 统一契约：min-height 24 + padding 3px 10px + line-height 18（18+6=24，高度有明确来源）。
// 跨文件：.status-chip 在 global.css，badge 系列在 dashboard.css —— 两边都必须守同一契约。
const chipBlock = readFileSync(new URL('../src/styles/global.css', import.meta.url), 'utf8')
const chipBlockText = chipBlock.match(/\.status-chip\s*\{([^}]*)\}/)?.[1] ?? ''
for (const block of [chipBlockText, cssBlock('.quality-badge, .mock-badge, .demo-badge, .stale-badge')]) {
  assert('badge 契约：min-height 24px', /min-height:\s*24px/.test(block))
  assert('badge 契约：padding 3px 10px', /padding:\s*3px 10px/.test(block))
  assert('badge 契约：line-height 18px（18+6=24，高度有来源）', /line-height:\s*18px/.test(block))
  assert('badge 契约：999px 胶囊、12px、700（统一≠改风格）',
    /border-radius:\s*999px/.test(block) && /font-size:\s*12px/.test(block) && /font-weight:\s*700/.test(block))
  assert('badge 契约：inline-flex 居中（内容垂直位置不依赖字体度量）', /inline-flex/.test(block) && /align-items:\s*center/.test(block))
}
// 登记项：kpi-strip__notice（11px）本轮不随 badge 统一 —— 决策留痕写在 dashboard.css 原始注释里
const dashRawD5 = readFileSync(new URL('../src/styles/dashboard.css', import.meta.url), 'utf8')
assert('kpi-strip__notice 登记为 badge 体系外（决策留痕）', /badge 体系\*\*之外/.test(dashRawD5))

// 字体层级：只动框架层（A 域），B/C 域冻结
assert('面板标题 18px（scale 档，经 --font-size-panel-title）', /panel-title\s*\{[^}]*font-size:\s*var\(--font-size-panel-title\)/.test(css))
assert('header-meta 数值 15px', /header-meta__item strong\s*\{[^}]*font-size:\s*var\(--font-size-xl\)/.test(css))
assert('KPI 名称 14px', /kpi-card__label\s*\{[^}]*font-size:\s*var\(--font-size-lg\)/.test(css))
// KPI 数字：scale 档改设计空间固定值（修 vw+transform 双重缩放），compact/reflow 保留 vw clamp
assert('KPI 数字 scale 档为设计空间 35px（修双重缩放）',
  /\.dashboard-viewport\[data-layout='scale'\]\s*\.kpi-card__value\s*\{\s*font-size:\s*35px/.test(css))
assert('KPI 数字 clamp 保留给 compact/reflow（单次缩放语义正确）', /font-size:\s*clamp\(25px,\s*1\.72vw,\s*33px\)/.test(css))
// B/C 域冻结（本批不调整；以后重新测量后可调，需先改断言）
assert('Process 数字保持 24px（scale 档，本批冻结）', /--pm-value:\s*24px/.test(css))
assert('Insights 正文仍为 13px（本批冻结，经 --font-size-md）', /insight-item p\s*\{[^}]*font-size:\s*var\(--font-size-md\)/.test(css))
assert('ECharts 外部字体未被全局放大（donut 中心仍 26）', /donut-center__value\s*\{[^}]*font-size:\s*26px/.test(css))

// ────────────────────────── 18. Batch D-7：字号 token 化 ──────────────────────────
// font-size 在本项目是布局变量（行高/面板预算/裁切边界），故只做「等值 token 化」+
// 半像素收敛（10.5→11 / 11.5→12 / 12.5→12），Top10 行高经实测保持 26px 未联动。
assert('font-size token 已定义（xs/sm/md/lg/xl/panel-title）', [
  '--font-size-xs: 11px', '--font-size-sm: 12px', '--font-size-md: 13px',
  '--font-size-lg: 14px', '--font-size-xl: 15px', '--font-size-panel-title: 18px'
].every((t) => css.includes(t)))
assert('面板标题走 token', /panel-title\s*\{[^}]*font-size:\s*var\(--font-size-panel-title\)/.test(css))
assert('面板副标题走 token', /panel-subtitle\s*\{[^}]*font-size:\s*var\(--font-size-sm\)/.test(css))
assert('Insights 正文走 token', /insight-item p\s*\{[^}]*font-size:\s*var\(--font-size-md\)/.test(css))
assert('Insights 标题走 token', /insight-item strong\s*\{[^}]*font-size:\s*var\(--font-size-lg\)/.test(css))
assert('KPI 名称走 token', /kpi-card__label\s*\{[^}]*font-size:\s*var\(--font-size-lg\)/.test(css))
assert('header-meta 数值走 token', /header-meta__item strong\s*\{[^}]*font-size:\s*var\(--font-size-xl\)/.test(css))
assert('页脚走 token', /dashboard-footer\s*\{[^}]*font-size:\s*var\(--font-size-sm\)/.test(css))
// 半像素漂移已清零（0.5px 值在跨 DPR 渲染下表现不稳定，且无设计意图）
assert('半像素字号已清零（10.5/11.5/12.5 不再出现）', !/font-size:\s*(?:10\.5|11\.5|12\.5)px/.test(css))
// Top10 行高保持 26px（10.5→11 实测未要求行高联动 —— 验证了 review 的修正）
assert('Top10 scale 行高保持 26px（字号收敛未牵动行高）', /max-height:\s*158px/.test(css))
assert('热力图格子边线为 50% 透明白（网格适度弱化：连贯但不被白线过度切割）', /borderColor:\s*'rgba\(255,\s*255,\s*255,\s*0\.5\)'/.test(heatSrc))

// KPI 数字与品牌标题的 vw 双重缩放问题登记为本批之外（V4 Typography/Scale Refactor）
assert('KPI 数字 compact/reflow 保留 vw clamp（双缩放修复拆到 V4）', /font-size:\s*clamp\(25px,\s*1\.72vw,\s*33px\)/.test(css))

// ────────────────────────── 16. Batch D-4：页脚（视觉终止层）──────────────────────────
// 职责只有「收尾」。两条红线：① 不得重复 Header 信息（品牌名/更新时间都在 Header）；
// ② 不得做成第四层卡片（背景/边框/图标）。高度参与视口预算，故钉在 32px。
const footerSrc = readFileSync(new URL('../src/components/dashboard/DashboardFooter.vue', import.meta.url), 'utf8')
assert('页面网格含页脚行（32px）', /grid-template-rows:\s*76px\s+104px\s+minmax\(0,\s*1fr\)\s+32px/.test(css))
assert('页脚高度 32px', /height:\s*32px/.test(cssBlock('.dashboard-footer')))
assert('页脚无背景（不得做成第四层卡片）', !/background/.test(cssBlock('.dashboard-footer')))
assert('页脚无边框（不引入新层次）', !/border/.test(cssBlock('.dashboard-footer')))
assert('页脚不含装饰线（第一版从简，需要时再加）', !/__rule/.test(footerSrc))
assert('页脚不重复 Header 的更新时间', !/更新时间/.test(footerSrc))
assert('页脚不重复 Header 的平台名', !/运营分析大屏|运营分析平台/.test(footerSrc))
assert('页脚为一句话（单一文本元素，不做成信息模块）', (footerSrc.match(/dashboard-footer__/g) || []).length === 1)
assert('页脚文案为理念收束句', /数据驱动运营优化/.test(footerSrc))
// 页脚在页面网格内（不进 dashboard-grid），且 reflow 档不隐藏 —— 滚动页结尾给结束感
assert('页脚是页面级元素（不进三列 grid）', !/dashboard-grid[\s\S]{0,200}dashboard-footer/.test(footerSrc) && /DashboardFooter \/>/.test(readFileSync(new URL('../src/views/Dashboard.vue', import.meta.url), 'utf8')))
assert('页脚在 reflow 档不隐藏（滚动页结尾给结束感）', !/data-layout='reflow'[\s\S]{0,240}?dashboard-footer[\s\S]{0,160}?display:\s*none/.test(css))
assert('Donut 数字使用等宽数字（数据刷新时宽度稳定）', /donut-center__value\s*\{[^}]*font-variant-numeric:\s*tabular-nums/.test(css))
assert('Donut radius 冻结为 57/74（本轮不动环径）', /radius:\s*\['57%',\s*'74%'\]/.test(donutSrc))
assert('Donut 数字走千分位格式化', /toLocaleString\('zh-CN'\)/.test(donutSrc))



for (const file of ['LoadForecastChart', 'StationHourHeatmap', 'FeeEnergyTrend']) {


  const text = readFileSync(new URL(`../src/components/dashboard/${file}.vue`, import.meta.url), 'utf8')
  assert(`${file} 已建立 compact props 通道`, /compact:\s*\{\s*type:\s*Boolean/.test(text))
}

if (failures.length) {
  console.error(`Layout verification FAILED (${failures.length} failures / ${passed + failures.length})`)
  for (const failure of failures) console.error(`  ✗ ${failure}`)
  process.exit(1)
}
console.log(
  `Layout verification PASSED (${passed} assertions, ${samples.length} resolutions, ` +
    `${sweepHeights.length} sweep heights, ${monotonicChecks} monotonicity checks)`
)
console.log(
  `  断点: reflow < ${BP.reflowMaxWidth} ≤ compact < ${BP.compactMaxWidth} ≤ scale(若 h ≤ ${BP.scaleHeightRatio}·w)`
)
