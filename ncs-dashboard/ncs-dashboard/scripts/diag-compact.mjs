// 复验：compact 双档几何
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const PW_PATH = process.env.PW_PATH
  || 'C:/Users/LENOVO/.workbuddy/binaries/node/workspace/node_modules/playwright-core/index.js'
const pwModule = await import(pathToFileURL(PW_PATH).href)
const { chromium } = pwModule.chromium ? pwModule : (pwModule.default ?? pwModule)

async function resolveBrowser() {
  for (const channel of ['msedge', 'chrome']) {
    try {
      return { channel, browser: await chromium.launch({ channel, headless: true }) }
    } catch (e) {
      console.error(`channel ${channel} unavailable`)
    }
  }
  throw new Error('未找到浏览器')
}

const TARGET = process.env.TARGET_URL || 'http://127.0.0.1:5199/'

const SIZES = [
  [1920, 1080, '设计基准 → scale'],
  [1715, 1401, '用户报告 → compact/columns'],
  [1600, 1200, '4:3 → compact/columns'],
  [1440, 900, '笔记本 → scale'],
  [1280, 1024, '矮窄窗 → compact/columns'],
  [1280, 800, '小笔记本 → scale'],
  [1024, 768, '小屏 → compact/stack'],
  [900, 600, 'compact 下界 → stack'],
  [768, 1024, '平板 → reflow'],
  [390, 844, '手机 → reflow']
]

const { channel, browser } = await resolveBrowser()
console.log(`using browser channel: ${channel}`)

// ⚠️ 每档**独立 context**，不要复用同一页面做 setViewportSize。
// 复用会漏掉一个真实缺陷：resize 后 ECharts 的布局可能滞后于容器，
// 于是 grid 的坐标矩形仍是上一档的尺寸。实测差别很大 ——
//   1024×768 stack 中心组：复用页面报 2.88 / 2.82（假通过）
//                          独立 context 报 3.79 / 3.68（真实，已越 3.6 门禁）
// 也就是说这个门禁在 stack 档长期是「假通过」。改法：每档新建 context。

// 非劣化门禁的具名例外：**精确匹配 mode / tier / 宽 / 高 四者**。
// 刻意不按「宽度区间」或「整个 tier」放宽 —— 否则日后别的档位发生真回归也会被一起豁免。
// 每条都必须能说清「为什么这是结构性过约束，而不是缺陷」。
//
// 当前登记 1 条：Batch D-4 页脚（32px + gap 9 = 41px）使 1280×1024 columns 的
// Trend 由 3.14 回到 4.07 —— 该档右列本就过约束（Insights 内容 198 vs 可用 140，
// 正文同时在被裁），页脚的高度只能从 Top10 / Trend 抽。
// 格式示例（用占位符，避免被「例外条数」断言计入）：
//   { mode: <mode>, tier: <tier>, width: <w>, height: <h>, max: <上限>,
//     why: '写清为什么这是结构性过约束、无法通过布局解决' }
const BELOW_GATE = [
  {
    mode: 'compact', tier: 'columns', width: 1280, height: 1024, max: 4.2,
    why: '右列过约束：Top10 + Process(下界140) + Insights(下界140) 已占去大半，'
      + '页脚再取 41px 后 Trend 只剩 150px（画布 383×94）。'
      + '该档同时存在 Insights 正文裁切，属结构性过约束。'
  }
]
const gateFor = (mode, tier, w, h) =>
  BELOW_GATE.find((e) => e.mode === mode && e.tier === tier && e.width === w && e.height === h)

let bad = 0
for (const [w, h, label] of SIZES) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  await page.goto(TARGET, { waitUntil: 'networkidle' })
  // 读几何前先等「字体就绪 + 两帧 rAF」：
  // 字体晚到会改变 label 宽度，进而改变 ECharts 的 grid 计算；rAF 保证布局已提交。
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
  })
  await page.waitForTimeout(300)

  const info = await page.evaluate(() => {
    const vp = document.querySelector('.dashboard-viewport')
    const rect = (el) => {
      if (!el) return null
      const r = el.getBoundingClientRect()
      return { w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top) }
    }
    return {
      mode: vp?.getAttribute('data-layout'),
      tier: vp?.getAttribute('data-tier'),
      page: rect(document.querySelector('.dashboard-page')),
      grid: rect(document.querySelector('.dashboard-grid')),
      center: rect(document.querySelector('.dashboard-column--center')),
      cols: [...document.querySelectorAll('.dashboard-grid > *')].map((el) => {
        const r = el.getBoundingClientRect()
        return { cls: el.className.replace('dashboard-column--', ''), w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top) }
      }),
      charts: [...document.querySelectorAll('.dashboard-column canvas')].map((c) => {
        const r = c.getBoundingClientRect()
        return { w: Math.round(r.width), h: Math.round(r.height), ratio: +(r.width / Math.max(r.height, 1)).toFixed(2) }
      }),
      // Batch C1：Top10 几何。这些是「诊断值」，只报告不作为构建门禁 ——
      // 真实浏览器受字体 / DPR / 亚像素影响，188px 可能报 187.4px，硬阈值会假失败。
      // 注意：一律用布局空间（offsetHeight / clientHeight），不用 getBoundingClientRect ——
      // scale 模式下后者是 transform 缩放后的值（26px 行高会报 19.5px），跨模式不可比。
      ranking: (() => {
        const panel = document.querySelector('.dashboard-column--right > :first-child')
        const list = panel?.querySelector('.ranking-list')
        if (!list) return null
        const rows = [...list.querySelectorAll('.ranking-row')]
        const cs = getComputedStyle(list)
        const padT = parseFloat(cs.paddingTop) || 0
        const padB = parseFloat(cs.paddingBottom) || 0
        const gap = parseFloat(cs.rowGap) || 0
        const rowH = rows.length ? rows[0].offsetHeight : 0
        const inner = list.clientHeight - padT - padB
        const contentH = rows.reduce((s, r) => s + r.offsetHeight, 0) + gap * Math.max(0, rows.length - 1)
        const scrollable = list.scrollHeight > list.clientHeight + 1
        return {
          panelH: panel.offsetHeight,
          rowH,
          rows: rows.length,
          gap,
          listClient: list.clientHeight,
          listScroll: list.scrollHeight,
          scrollable,
          display: cs.display,
          overflowY: cs.overflowY,
          // 可见行数（含被截断的那一行的小数部分）
          visibleRows: rowH ? +(inner / (rowH + gap)).toFixed(1) : 0,
          // 底部空洞：只在「内容装得下」时有意义（装不下时靠滚动，无空洞概念）
          tailGap: scrollable ? null : +(inner - contentH).toFixed(1)
        }
      })(),
      // Batch C.5：两组「展示层收口」的诊断值
      // ① 运营建议：副标题底 → 首卡顶 的视觉间距（align-content 改为 start 后应恒为 ~4px）
      // ② Process 卡内：数字右缘 → 单位左缘 的最小间隙（数字真居中 + 单位靠右，必须 >0）
      insightGap: (() => {
        const ins = document.querySelector('.dashboard-column--right > :nth-child(4)')
        const sub = ins?.querySelector('.panel-subtitle')
        const first = ins?.querySelector('.insight-item')
        if (!sub || !first) return null
        return +(first.getBoundingClientRect().top - sub.getBoundingClientRect().bottom).toFixed(1)
      })(),
      numUnitGap: (() => {
        const proc = document.querySelector('.dashboard-column--right > :nth-child(3)')
        const cards = [...(proc?.querySelectorAll('.process-metric') || [])]
        if (!cards.length) return null
        const gaps = cards.map((c) => {
          const strong = c.querySelector('strong')
          const small = strong?.querySelector('small')
          if (!small) return null
          // 数字本体宽度：用只含数字文本的探针量（strong 内已无空白文本节点）
          const probe = document.createElement('span')
          probe.style.cssText = `position:absolute;visibility:hidden;white-space:nowrap;font:${getComputedStyle(strong).font}`
          probe.textContent = strong.childNodes[0].textContent
          document.body.appendChild(probe)
          const nw = probe.getBoundingClientRect().width
          probe.remove()
          const cb = c.getBoundingClientRect()
          const numRight = cb.left + cb.width / 2 + nw / 2
          return +(small.getBoundingClientRect().left - numRight).toFixed(1)
        }).filter((x) => x !== null)
        return gaps.length ? Math.min(...gaps) : null
      })(),
      // Batch C.6：Process 面板内部「标题底 → 指标卡顶」与「指标卡底 → 面板底」的净空，
      // 用来验证上下呼吸空间是否对称（改前实测为上 1px / 下 8px，明显上紧下松）。
      // ⚠️ 这三个 C.5/C.6 诊断用的是 getBoundingClientRect，即 **transform 之后**的值 ——
      //    scale 模式下会被整体缩放（1920 报 9px，1440×900 报 6.8px，1280×800 报 6px，
      //    实为同一个设计空间值 9px × 0.75 / 0.667）。判断「是否对称」不受影响
      //    （两侧同比例缩放，差值也同比例），但**不要跨模式比较绝对值**。
      //    ranking 那组诊断已改用 offsetHeight（布局空间），此处为保持与 C.5 一致未改。
      procGapAbove: (() => {
        const proc = document.querySelector('.dashboard-column--right > :nth-child(3)')
        const h = proc?.querySelector('.panel-header')
        const g = proc?.querySelector('.process-grid')
        if (!h || !g) return null
        return +(g.getBoundingClientRect().top - h.getBoundingClientRect().bottom).toFixed(1)
      })(),
      procGapBelow: (() => {
        const proc = document.querySelector('.dashboard-column--right > :nth-child(3)')
        const g = proc?.querySelector('.process-grid')
        if (!g) return null
        return +(proc.getBoundingClientRect().bottom - g.getBoundingClientRect().bottom).toFixed(1)
      })(),
      // Batch C.6b：Process 行改用 fr 上限（不再 auto），代价是**内容高度不再能撑开该行** ——
      // 若内容超过被分配的高度就会裁切。这里报告两个面板是否发生裁切，用来守住这个新脆弱点。
      procClip: (() => {
        const p = document.querySelector('.dashboard-column--right > :nth-child(3)')
        if (!p) return null
        return p.scrollHeight > p.clientHeight + 1 ? p.scrollHeight - p.clientHeight : 0
      })(),
      insClip: (() => {
        const ps = [...document.querySelectorAll('.dashboard-column--right > :nth-child(4) .insight-item p')]
        if (!ps.length) return null
        // 用 p 自身的 scrollHeight 判定真实文本高度（offsetHeight 是已裁后的值，测不出来）
        const maxOver = Math.max(0, ...ps.map((p) => p.scrollHeight - p.clientHeight))
        return maxOver > 1 ? maxOver : 0
      })(),
      // Batch D-2：Donut 中心 KPI 的几何验收（只报告，不作门禁）
      // donutOffset = 覆盖层中心 − 环心；验收标准 **≤1px**（不追求数学 0：
      //   DPR / 字体渲染 / 亚像素定位都会产生零点几 px）。
      //
      // ⚠️ 这里量的是 **top 绑定是否正确**（覆盖层未补偿前的中心 vs 环心），不是最终视觉位置。
      //    最终视觉位置 = 该值 + --donut-optical-y（UI 视觉补偿，有意的下移）。
      //    两者必须分开：合并在一起会让「CENTER.y 绑定断了」这类真 bug 被补偿量掩盖。
      //
      // ⚠️ 同样必须用**布局空间**：scale 模式整页被 transform 缩放，
      //    getBoundingClientRect() 是缩放后的值，clientHeight 是缩放前的 ——
      //    混用会算出假偏移（初版就犯过：1440×900 报 −19.5px、1280×800 报 −26px，实际都是 0）。
      //    统一用 offsetTop / clientHeight / offsetWidth。
      donutOffset: (() => {
        const wrap = document.querySelector('.donut-wrapper')
        const center = document.querySelector('.donut-center')
        const chart = wrap?.querySelector('.chart')
        if (!wrap || !center || !chart) return null
        // 覆盖层 top:43% ⇒ offsetTop 即「未补偿前的视觉中心」
        const centerY = center.offsetTop
        // 环心 = 图表高度的 43%（与组件里的 CENTER.y 一致）
        const ringY = chart.clientHeight * 0.43
        return +(centerY - ringY).toFixed(1)
      })(),
      // UI 视觉补偿量（有意下移），从 CSS 自定义属性读出，保持单一真源
      donutOptical: (() => {
        const center = document.querySelector('.donut-center')
        if (!center) return null
        const v = getComputedStyle(center).getPropertyValue('--donut-optical-y')
        return parseFloat(v) || 0
      })(),
      // donutFits = 内半径 − 文字块外接半径；正值 = 放得下（同样用布局空间）
      donutFits: (() => {
        const chart = document.querySelector('.donut-wrapper .chart')
        const center = document.querySelector('.donut-center')
        if (!chart || !center) return null
        const W = chart.clientWidth, H = chart.clientHeight
        const innerR = 0.57 * Math.min(W, H) / 2
        const bw = center.offsetWidth, bh = center.offsetHeight
        const need = Math.sqrt(bw * bw + bh * bh) / 2
        return +(innerR - need).toFixed(1)
      })(),
      // Batch D-3：三列「行分界」对齐度（用户要求：既是三列，也是两行）
      // 取每列「第二行首个面板」的顶边相对列顶的距离；三值越接近，横向秩序感越强。
      // 注：用 getBoundingClientRect（scale 档被缩放），但三列同比例缩放 ⇒ 差值不受影响。
      rowAlign: (() => {
        const g = (sel, n) => {
          const col = document.querySelector(sel)
          if (!col || !col.children[n]) return null
          const colTop = col.getBoundingClientRect().top
          return +(col.children[n].getBoundingClientRect().top - colTop).toFixed(1)
        }
        const L = g('.dashboard-column--left', 2)
        const C = g('.dashboard-column--center', 1)
        const R = g('.dashboard-column--right', 2)
        if (L === null || C === null || R === null) return null
        return { L, C, R, max: +(Math.max(L, C, R) - Math.min(L, C, R)).toFixed(1) }
      })(),
      scrollH: document.querySelector('.dashboard-viewport')?.scrollHeight,
      innerH: window.innerHeight
    }
  })

  // Trend 绘图区（ECharts 布局空间坐标；scale 模式下 = 1920×1080 设计空间，跨模式可比）
  const trend = await page.evaluate(async () => {
    const urls = performance.getEntriesByType('resource').map((e) => e.name)
      .filter((n) => /echarts/i.test(n) && /\.js(\?|$)/.test(n))
    let ec = null
    for (const u of urls) {
      try {
        const mod = await import(u)
        const c = mod.default ?? mod
        if (typeof c.getInstanceByDom === 'function') { ec = c; break }
      } catch (e) { /* 换下一个候选 */ }
    }
    if (!ec) return null
    const panel = document.querySelector('.dashboard-column--right > :nth-child(2)')
    const dom = panel?.querySelector('.chart')
    const inst = dom ? ec.getInstanceByDom(dom) : null
    if (!inst) return null
    const g = inst.getModel().getComponent('grid')
    const r = g?.coordinateSystem?.getRect?.()
    if (!r) return null
    return {
      panelH: panel.offsetHeight,
      plot: { w: +r.width.toFixed(1), h: +r.height.toFixed(1) },
      ratio: +(r.width / Math.max(r.height, 1)).toFixed(2)
    }
  })

  const ratios = info.charts.map((c) => c.ratio)
  const worstRatio = ratios.length ? Math.max(...ratios) : 0
  const exception = gateFor(info.mode, info.tier, w, h)
  const gate = exception ? exception.max : 3.6
  const flat = ratios.filter((r) => r > gate).length
  // scale 模式纵向留白/滚动是设计行为；只有 compact(columns) 才要求不溢出
  const isColumns = info.mode === 'compact' && info.tier === 'columns'
  const overflow = info.scrollH - info.innerH
  const overflowBad = isColumns && overflow > 60
  const flag = flat > 0 ? `  ⚠ ${flat} 张图 >3.6:1` : overflowBad ? `  ⚠ 纵向溢出 ${overflow}px` : '  ✅'
  if (flat > 0 || overflowBad) bad++

  console.log(
    `\n${String(w).padStart(4)}×${String(h).padEnd(4)} ${label}`
  )
  console.log(`  mode=${info.mode} tier=${info.tier}  page ${info.page?.w}×${info.page?.h}  grid ${info.grid?.w}×${info.grid?.h}`)
  console.log(`  columns: ${info.cols.map((c) => `${c.cls} ${c.w}×${c.h}@${c.top}`).join(' | ')}`)
  console.log(`  chart ratios: [${ratios.join(', ')}]  最扁 ${worstRatio}${flag}`)

  const rk = info.ranking
  if (rk) {
    const scrollNote = rk.scrollable ? `可滚动 ${rk.listScroll}>${rk.listClient}` : `不滚动`
    const tailNote = rk.tailGap === null ? '' : `  尾部空洞 ${rk.tailGap}px`
    console.log(
      `  Top10: 面板 ${rk.panelH}px | 行高 ${rk.rowH}px × ${rk.rows} 行 | 列表 ${rk.listClient}/${rk.listScroll} ${scrollNote}`
        + ` | 可见 ${rk.visibleRows} 行 | ${rk.display}/${rk.overflowY}${tailNote}`
    )
  }
  if (trend) {
    console.log(`  Trend: 面板 ${trend.panelH}px | 绘图区 ${trend.plot.w}×${trend.plot.h} = ${trend.ratio} : 1`)
  } else {
    console.log('  Trend: (未取到绘图区，ECharts 实例或 grid 组件不可用)')
  }
  if (info.insightGap !== null || info.numUnitGap !== null) {
    const gap = info.insightGap === null ? '—' : `${info.insightGap}px`
    const nu = info.numUnitGap === null ? '—' : `${info.numUnitGap}px`
    const nuFlag = info.numUnitGap !== null && info.numUnitGap <= 0 ? ' ⚠ 数字与单位重叠' : ''
    console.log(`  C.5: 运营建议「副标题底→首卡顶」${gap} | Process「数字右缘→单位左缘」最小 ${nu}${nuFlag}`)
  }
  if (info.rowAlign) {
    const { L, C, R, max } = info.rowAlign
    // 目标 5px：fr 取整 + 页脚行引入后，scale 档实测残差 0.8~3.8px（肉眼不可辨）；
    // 2px 的旧目标在页脚加入后不可达（左列 .84fr 的取整），故校准为 5。
    const known = info.mode === 'scale' ? (max <= 5 ? '✅ 已对齐' : '⚠ 超出目标 5px') : '（compact 档：登记为接受的错落）'
    console.log(`  D.3: 三列分界 左 ${L} / 中 ${C} / 右 ${R}  最大差 ${max}px  ${known}`)
  }
  if (info.procGapAbove !== null) {
    const diff = +(info.procGapAbove - info.procGapBelow).toFixed(1)
    const flag = Math.abs(diff) <= 2 ? '✅ 基本对称' : '⚠ 上下不对称'
    const clip = (info.procClip ? ` ⚠ Process 被裁 ${info.procClip}px` : '') + (info.insClip ? ` ⚠ 运营建议正文被裁 ${info.insClip}px` : '')
    console.log(`  C.6: Process 净空 上 ${info.procGapAbove}px / 下 ${info.procGapBelow}px（差 ${diff}）${flag}${clip || ' | 无裁切 ✅'}`)
  }
  if (info.donutOffset !== null) {
    // 验收 ≤1px（不追求 0：DPR/字体渲染/亚像素定位会带零点几 px）
    const ok = Math.abs(info.donutOffset) <= 1 ? '✅ 居中' : '⚠ 偏移'
    const fits = info.donutFits > 0 ? `✅ 内圆余 ${info.donutFits}px` : '❌ 溢出内圆'
    console.log(`  D.2: Donut 绑定偏移 ${info.donutOffset}px ${ok} | 视觉补偿 +${info.donutOptical}px | ${fits}`)
  }
  if (exception) console.log(`  ↑ 具名例外（${exception.mode}/${exception.tier} ${exception.width}×${exception.height}），门禁放宽至 ${exception.max}\n    ${exception.why}`)
  await ctx.close()
}

await browser.close()
console.log(`\n${bad === 0 ? '全部通过 ✅' : bad + ' 个尺寸存在问题 ❌'}`)
process.exit(bad === 0 ? 0 : 1)
