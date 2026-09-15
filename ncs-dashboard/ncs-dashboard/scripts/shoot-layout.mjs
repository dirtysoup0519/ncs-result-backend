/**
 * 用本机已安装的 Chrome / Edge 渲染 12 个验收尺寸，截图 + 读取实测布局数据。
 *
 * 不下载 Chromium，直接用 system channel（chrome / msedge）。
 * 输出：
 *   .shots/<size>.png          截图
 *   .shots/layout-report.json  每个尺寸的实际 mode / 列尺寸 / 是否出现滚动条 / 图表 canvas 尺寸
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { join } from 'node:path'

// playwright-core 装在受管 Node 的隔离工作区（不污染本项目依赖），
// 因此用绝对路径动态 import，而不是裸包名解析。
const PW_PATH = process.env.PW_PATH
  || 'C:/Users/LENOVO/.workbuddy/binaries/node/workspace/node_modules/playwright-core/index.js'
// playwright-core 是 CJS 包，ESM 动态 import 后命名导出可能为空，需回退到 default。
const pwModule = await import(pathToFileURL(PW_PATH).href)
const { chromium } = pwModule.chromium ? pwModule : (pwModule.default ?? pwModule)

const root = fileURLToPath(new URL('../', import.meta.url))
const shotDir = join(root, '.shots')
mkdirSync(shotDir, { recursive: true })

const TARGET_URL = process.env.SHOT_URL || 'http://127.0.0.1:5199/'

const sizes = [
  { w: 1920, h: 1080, expect: 'scale' },
  { w: 2560, h: 1440, expect: 'scale' },
  { w: 1600, h: 900, expect: 'scale' },
  { w: 1366, h: 768, expect: 'scale' },
  { w: 1280, h: 800, expect: 'scale' },
  { w: 1715, h: 1401, expect: 'compact' }, // Batch B.1 用户报告场景
  { w: 1600, h: 1200, expect: 'compact' },
  { w: 1024, h: 768, expect: 'compact' },
  { w: 1280, h: 1024, expect: 'compact' },
  { w: 900, h: 600, expect: 'compact' },
  { w: 768, h: 1024, expect: 'reflow' },
  { w: 1024, h: 1366, expect: 'reflow' },
  { w: 390, h: 844, expect: 'reflow' },
  { w: 375, h: 667, expect: 'reflow' }
]

async function resolveBrowserType() {
  for (const channel of ['chrome', 'msedge']) {
    try {
      const browser = await chromium.launch({ channel })
      return { channel, browser }
    } catch (error) {
      console.error(`channel ${channel} unavailable: ${error.message.split('\n')[0]}`)
    }
  }
  throw new Error('本机未找到 Chrome / Edge，无法截图')
}

const report = []
const { channel, browser } = await resolveBrowserType()
console.log(`using browser channel: ${channel}`)

try {
  for (const size of sizes) {
    const page = await browser.newPage({
      viewport: { width: size.w, height: size.h },
      deviceScaleFactor: 1
    })
    await page.goto(TARGET_URL, { waitUntil: 'load' })
    // 等 Vue 挂载 + ECharts 首次渲染
    await page.waitForSelector('.dashboard-viewport', { timeout: 15000 })
    await page.waitForTimeout(1200)

    const probe = await page.evaluate(() => {
      const viewport = document.querySelector('.dashboard-viewport')
      const canvas = document.querySelector('.dashboard-canvas')
      const page_ = document.querySelector('.dashboard-page')
      const grid = document.querySelector('.dashboard-grid')
      const cols = [...document.querySelectorAll('.dashboard-column')].map((el) => {
        const r = el.getBoundingClientRect()
        return { cls: el.className.replace('dashboard-column ', ''), w: Math.round(r.width), h: Math.round(r.height) }
      })
      const charts = [...document.querySelectorAll('.chart')].map((el) => {
        const r = el.getBoundingClientRect()
        const inner = el.querySelector('canvas')
        return {
          w: Math.round(r.width),
          h: Math.round(r.height),
          canvasW: inner ? inner.width : null,
          canvasH: inner ? inner.height : null
        }
      })
      const scrollRoot = document.documentElement
      return {
        mode: viewport?.dataset.layout ?? null,
        tier: viewport?.dataset.tier ?? null,
        canvasStyle: canvas ? canvas.getAttribute('style') : null,
        pageHeight: page_ ? Math.round(page_.getBoundingClientRect().height) : null,
        gridDisplay: grid ? getComputedStyle(grid).display : null,
        cols,
        charts,
        hasHScroll: scrollRoot.scrollWidth > scrollRoot.clientWidth + 1,
        hasVScroll: scrollRoot.scrollHeight > scrollRoot.clientHeight + 1
      }
    })

    await page.screenshot({ path: join(shotDir, `${size.w}x${size.h}.png`), fullPage: size.expect !== 'scale' })
    report.push({ size: `${size.w}x${size.h}`, expect: size.expect, ...probe })
    await page.close()
    console.log(`done ${size.w}x${size.h} → mode=${probe.mode}/${probe.tier} cols=${probe.cols.map((c) => `${c.w}p`).join('/')} hScroll=${probe.hasHScroll}`)
  }
} finally {
  await browser.close()
}

writeFileSync(join(shotDir, 'layout-report.json'), JSON.stringify(report, null, 2), 'utf8')
console.log(`\nreport written: .shots/layout-report.json (${report.length} sizes)`)
