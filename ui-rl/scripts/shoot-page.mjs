// 渲染一个报告网页给 agent 看(截法和 plain-report.mjs 一样):
//   node ui-rl/scripts/shoot-page.mjs <page.html>
// 写 <page>.png(1440 宽整页)和 <page>-part-<i>.png(按 1440×1600 切开,好看清),
// 打印页面高度、脚本报错、加载失败的图片、正文里的 undefined/NaN、有没有横向溢出。
import fs from "node:fs"
import path from "node:path"
import { createRequire } from "node:module"
const { chromium } = createRequire(import.meta.url)("../gen/node_modules/playwright-core")
const f = path.resolve(process.argv[2])
const base = f.replace(/\.html$/, "")
for (const old of fs.readdirSync(path.dirname(f))) if (old.startsWith(path.basename(base) + "-part-")) fs.rmSync(path.join(path.dirname(f), old))
const b = await chromium.launch({ executablePath: process.env.CHROME ?? "/opt/pw-browsers/chromium" })
const page = await b.newPage({ viewport: { width: 1440, height: 900 } })
const errs = []
page.on("pageerror", (e) => errs.push(e.message))
await page.goto(`file://${f}`, { waitUntil: "load" })
await page.evaluate(() => Promise.all([...document.images].map((i) => { i.loading = "eager"; return i.complete ? null : new Promise((r) => { i.onload = i.onerror = r }) })))
await page.evaluate(async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += 400) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)) } scrollTo(0, 0) })
await page.waitForTimeout(1500)
await page.screenshot({ path: `${base}.png`, fullPage: true })
const r = await page.evaluate(() => ({
  height: document.documentElement.scrollHeight,
  images: document.images.length,
  broken: [...document.images].filter((i) => !i.naturalWidth).map((i) => i.getAttribute("src")),
  undefinedOrNaN: (document.body.innerText.match(/\bundefined\b|\bNaN\b/g) ?? []).length,
  horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
}))
const parts = []
for (let y = 0, i = 1; y < r.height; y += 1600, i++) {
  const p = `${base}-part-${i}.png`
  await page.screenshot({ path: p, fullPage: true, clip: { x: 0, y, width: 1440, height: Math.min(1600, r.height - y) } })
  parts.push(p)
}
console.log(JSON.stringify({ ...r, scriptErrors: errs, fullPage: `${base}.png`, parts }, null, 1))
await b.close()
