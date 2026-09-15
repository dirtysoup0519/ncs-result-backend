import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 大屏布局状态唯一来源（Batch B）。
 *
 * 设计基准：1920 × 1080（16:9）。三档模式：
 *   - scale   ：宽高比接近 16:9，整体等比缩放（transform: scale）
 *   - compact ：比例偏离 15%~30%，中心组全宽置顶 + 左右两列并排
 *   - reflow  ：比例偏离 >30% 或视口宽度 < 768，单列纵向排列（允许纵向滚动）
 *
 * ⚠️ 关键约束：视口尺寸必须取 window.innerWidth / window.innerHeight。
 *    不要用 document.documentElement.clientWidth/clientHeight —— 后者的
 *    clientHeight 是「内容驱动」的：Reflow 模式下内容被撑到 3000px 时会返回
 *    3000 而不是视口高度，ratioDiff 会整体算错，模式判定不可信。
 *
 * 禁止任何组件自行监听 window resize，一律消费本 composable 的输出。
 */

export const BREAKPOINTS = Object.freeze({
  // ── 分级阈值 ──
  //   宽度 < 900                    → reflow
  //   900 ≤ 宽度 < 1180             → compact
  //   宽度 ≥ 1180 且 高度 ≤ 0.7·宽度 → scale
  //   宽度 ≥ 1180 且 高度 > 0.7·宽度 → compact
  reflowMaxWidth: 900,
  compactMaxWidth: 1180,
  // scale 的纵向准入系数：等价于「宽高比 ≥ 1/0.7 ≈ 1.4286」
  scaleHeightRatio: 0.7,
  // compact 内部的纵向分档：高度 ≥ 此值说明纵向有富余，
  // 可保留「中｜左｜右」三列；否则改用「中置顶 + 左右并排」的堆叠式。
  //
  // ⚠️ 曾一度上调至 1200（想让 1280×1024 改判 stack，以救它那张很扁的趋势图）。
  //    独立 context 实测后**已回退**，因为那是净回归：
  //      1280×1024 进 stack 后中心组由三列变为整行全宽，
  //      两张中心图的比例 1.73:1 → 4.78 / 4.64（同时 Trend 画布 4.5:1），
  //      即「为救一张扁图换来三张更扁的」。
  //    真正的修法是让 stack 档的中心组有足够高度 —— 见 dashboard.css 里
  //    stack 中心列的行定义（minmax(420px,1fr) / minmax(400px,1fr)）。
  compactColumnMinHeight: 960,

  designWidth: 1920,
  designHeight: 1080
})

/**
 * 模式判定（Batch B.1 修正版）。
 *
 * ── 为什么废弃 ratioDiff ──
 * Batch B 初版用 `ratioDiff = |w/h − 16/9| / (16/9)` 判定，存在两个结构性缺陷：
 *
 * 1. **非单调（顺序颠倒）**：ratioDiff 关于 16:9 对称、且随宽度呈 V 形
 *    （在 16:9 处为 0，两侧同时上升）。固定高度增大宽度时它先降后升，
 *    于是任何双侧阈值都必然产生 `compact → scale → compact` ——
 *    更宽的窗口反而拿到更「退化」的模式。
 *    实测高度 1401 时：`3600~2790 compact / 2789~2192 scale / 2191~900 compact`。
 *
 * 2. **竖向窗口不可达**：compact 的定义是「空间不够、退化布局」，但旧逻辑下
 *    它漂到了 2864px 以上的超宽区间，而真正需要并排布局的竖向桌面窗口
 *    （1715×1401 位于 2191~900，是 compact 区间？——实际被比值挡在 reflow）
 *    反而进不去。
 *
 * ── 修正原则 ──
 * 分级条件必须**单调**：视口变宽时，模式等级（reflow < compact < scale）
 * 只许升、不许降。这里把模式写成「宽度」与「高度」两个一维条件的函数。
 *
 * 宽度主干天然单调（越宽越高级）。难点在高度条件：
 *
 *   - 若用「绝对高度上限」（h ≤ 1000 → scale），2K/4K 屏（h=1440/2160）
 *     会被误判成 compact，但它们的视觉体验其实和 1080p 一致 —— 因为
 *     缩放系数取 min(vw/1920, vh/1080)，高度充足时由**宽度**决定，
 *     纵向只会留白，不会挤压。用绝对高度会把 1440p/4K 全部打下去。
 *   - 若用「比例」（w/h ≥ 1.6 → scale），固定高度下宽度增大时 w/h 单调增，
 *     看起来也行，但 1920×1080（1.778）与 1715×1401（1.224）的差别
 *     只在比例上，而 1440p（1.778）也在同一比例带上 —— 会把 1920×1080
 *     这个设计基准自己踢出 scale（实测 ratioDiff 版本即如此）。
 *
 * 真正的解法是 **高度上限随宽度浮动**：
 *
 *     高度 ≤ 0.7 × 宽度  ⇔  宽度 / 高度 ≥ 1/0.7 ≈ 1.4286  ⇔  scale
 *
 * 这是「同时依赖 w 与 h」的条件，但它对**固定高度**扫描宽度时是单调的：
 * 高度固定、宽度增大 ⇒ 右侧 0.7·宽度 单调增大 ⇒ 条件只会从「不满足」
 * 翻到「满足」，永不回退。于是单调性保住，竖向窗口也能被正确区分。
 *
 * 检验两个硬约束（k = 0.7）：
 *   - 1920×1080：1080 ≤ 0.7×1920 = 1344 ✅ → scale（设计基准保住）
 *   - 1715×1401：1401 ≤ 0.7×1715 = 1200.5 ❌ → compact（竖向窗口退化）
 *   - 2560×1440：1440 ≤ 0.7×2560 = 1792 ✅ → scale（2K 保住）
 *   - 3840×2160：2160 ≤ 0.7×3840 = 2688 ✅ → scale（4K 保住）
 *
 * k 的可行区间由前两个约束夹出：1080/1920 = 0.5625 ≤ k < 1401/1715 = 0.8169。
 * 取 0.7 是区间中点附近，两侧都留足余量（对 1200p 屏、对 16:10 屏）。
 */
function detectMode(width, height) {
  if (!width || !height) return 'scale'

  // 宽度主干：单调性的保证
  if (width < BREAKPOINTS.reflowMaxWidth) return 'reflow'
  if (width < BREAKPOINTS.compactMaxWidth) return 'compact'

  // 宽度已足够：纵向上限随宽度浮动，等价于「宽高比 ≥ 1/0.7」
  return height <= BREAKPOINTS.scaleHeightRatio * width ? 'scale' : 'compact'
}

/**
 * Compact 的纵向分档（Batch B.1 二段修复）。
 *
 * ── 为什么 compact 还需要再分两档 ──
 * Batch B 的 compact 只有一种形态：「中心组 flex-basis:100% 置顶 +
 * 左右两列 50/50 并排」。这在 1280×1024、1024×768 这类**矮而窄**的
 * 窗口里是对的 —— 横向挤不下三列，只能让中心组独占一行。
 *
 * 但在 1715×1401 这类**竖向高窗**里，横向其实够放三列，纵向还大量富余。
 * 此时仍强制中心组全宽置顶，会得到实测结果：
 *   - .dashboard-page 被撑到 2270px（视口仅 1401），必须滚动才能看全；
 *   - 中心组宽度 1687px，其内两张图被 `minmax(320px,1fr)` 拉成
 *     1669×339，宽高比 **4.92 : 1** —— 一条被压扁的横条，
 *     折线/热力图的空间信息严重失真。
 * 这正是用户报告的「继续变窄，页面不变，信息从右侧开始丢失」的底层成因：
 * 不是真的裁切，而是**结构降级过度**导致的视觉失真 + 纵向溢出。
 *
 * ── 分档规则 ──
 *   height ≥ 1150 → 'columns'：纵向有富余，保留「中｜左｜右」三列，
 *                     中心组恢复 flex:0 0 auto，由 .dashboard-page 的
 *                     grid-template-rows: 68px auto minmax(0,1fr) 给高度，
 *                     图表拿回 16:9 左右的正常宽高比。
 *   height <  1150 → 'stack'  ：维持 Batch B 的堆叠形态（已验证无回归）。
 *
 * 1150 的取法：compact 的 page 在堆叠形态下实测固定为 2270px 高
 * （grid 1956 + KPI 209 + header 68 + padding）。要装下正常的三列，
 * 大致需要三列中最高的右列（300+200+160+140 + 3×10 gap = 830）
 * 加上 KPI（~209）与 header（68），约 1110px。取 1150 留 40px 余量，
 * 同时避开 1080 这个最常见的笔记本高度（1080 走 scale，不会进 compact）。
 */
function detectCompactTier(width, height) {
  if (!width || !height) return 'stack'
  return height >= BREAKPOINTS.compactColumnMinHeight ? 'columns' : 'stack'
}

export function useDashboardLayout() {
  const hasWindow = typeof window !== 'undefined'

  // setup 阶段同步取初值：computed(mode) 的首次求值发生在 onMounted 之前，
  // 若初值为 0 会兜底成 scale，窄屏首帧闪烁一次再跳 reflow。
  const viewportWidth = ref(hasWindow ? window.innerWidth : BREAKPOINTS.designWidth)
  const viewportHeight = ref(hasWindow ? window.innerHeight : BREAKPOINTS.designHeight)

  let frame = null

  function measure() {
    if (!hasWindow) return
    viewportWidth.value = window.innerWidth
    viewportHeight.value = window.innerHeight
  }

  function scheduleMeasure() {
    if (frame !== null) cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      frame = null
      measure()
    })
  }

  const mode = computed(() => detectMode(viewportWidth.value, viewportHeight.value))

  // compact 的纵向形态（只对 compact 有意义），输出到 data-tier 供 CSS 消费
  const tier = computed(() => {
    if (mode.value !== 'compact') return 'default'
    return detectCompactTier(viewportWidth.value, viewportHeight.value)
  })

  const scale = computed(() => {
    if (!viewportWidth.value || !viewportHeight.value) return 1
    return Math.min(
      viewportWidth.value / BREAKPOINTS.designWidth,
      viewportHeight.value / BREAKPOINTS.designHeight
    )
  })

  const isScale = computed(() => mode.value === 'scale')
  const isCompact = computed(() => mode.value === 'compact')
  // 图表 props 通道用：Compact 与 Reflow 都算「空间紧张」
  const isMobile = computed(() => mode.value === 'reflow')

  onMounted(() => {
    measure()
    window.addEventListener('resize', scheduleMeasure, { passive: true })
    // visualViewport 语义最精确，存在时作为兜底（应对地址栏收放 / 移动端缩放）
    window.visualViewport?.addEventListener('resize', scheduleMeasure, { passive: true })
  })

  onBeforeUnmount(() => {
    if (frame !== null) cancelAnimationFrame(frame)
    frame = null
    window.removeEventListener('resize', scheduleMeasure)
    window.visualViewport?.removeEventListener('resize', scheduleMeasure)
  })

  return {
    mode,
    tier,
    scale,
    viewportWidth,
    viewportHeight,
    isScale,
    isCompact,
    isMobile,
    remeasure: measure
  }
}
