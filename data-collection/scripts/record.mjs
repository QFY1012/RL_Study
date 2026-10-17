// Loads a live page, records everything it loads, and reads its sections.
//   node scripts/record.mjs <url> <out-dir>
// Writes to <out-dir>:
//   page.har        every request and response (render.mjs replays it, scripts included)
//   media/          videos and audio, whole (browser.mjs, routeMedia)
//   live.png        full-page screenshot of the live page, for reference
//   sections.json   the page URL, design tokens, per section its box and content,
//                   and the inline SVGs as standalone files (assets)
import fs from "node:fs"
import path from "node:path"
import { chromium } from "playwright-core"
import { CHROME, CONTEXT, load, routeMedia } from "./browser.mjs"
import { readPage } from "./read-page.mjs"

const [url, out] = process.argv.slice(2)
if (!url || !out) throw new Error("usage: record.mjs <url> <out-dir>")
fs.mkdirSync(out, { recursive: true })
const har = path.join(out, "page.har")

const browser = await chromium.launch({ executablePath: CHROME, proxy: { server: process.env.HTTPS_PROXY } })
const context = await browser.newContext({ ...CONTEXT, recordHar: { path: har, mode: "full", content: "embed" } })
await routeMedia(context, out, true)
const page = await context.newPage()
await load(page, url)
const { sections, assets, tokens } = await readPage(page)
await page.screenshot({ path: path.join(out, "live.png"), fullPage: true, timeout: 120000 })
const finalUrl = page.url()
fs.writeFileSync(path.join(out, "sections.json"), JSON.stringify({ url: finalUrl, title: await page.title(), tokens, sections, assets }, null, 1))
await context.close()
await browser.close()

// A response that redirects to its own URL (a server setting a cookie, then sending
// the page) would loop in the replay, which answers with the first match: dropped.
const log = JSON.parse(fs.readFileSync(har, "utf8"))
const before = log.log.entries.length
log.log.entries = log.log.entries.filter((e) => !(e.response.status >= 300 && e.response.status < 400 && new URL(e.response.redirectURL || e.request.url, e.request.url).href === e.request.url))
fs.writeFileSync(har, JSON.stringify(log))
console.log(`recorded ${log.log.entries.length} requests${before > log.log.entries.length ? ` (dropped ${before - log.log.entries.length} redirects to themselves)` : ""}`)

console.log(`${finalUrl}: ${sections.length} sections`)
for (const s of sections) console.log(`  #${s.i} <${s.tag}> y=${s.box.y} h=${s.box.h} items=${s.items.length} ${JSON.stringify(s.items.find((t) => t.text)?.text?.slice(0, 50) ?? "")}`)
