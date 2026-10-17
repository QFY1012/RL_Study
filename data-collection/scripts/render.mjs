// Renders a snapshot offline: the original page, and the page once more for each
// generated section, with that section swapped in.
//   node scripts/render.mjs <snapshot-dir>
// Every request is answered from page.har.zip (anything not in it is aborted), and
// the document itself is page.html, so all renders share the same DOM, fonts and
// images. A generated section goes into a shadow root on a host element that takes
// the old section's place: its CSS and the page's CSS cannot reach each other, while
// inherited properties (font, color, line height) still flow in from the page.
// Writes render/orig.png, render/<i>.png and render/<i>.json (boxes and checks).
import fs from "node:fs"
import path from "node:path"
import { chromium } from "playwright-core"
import { CONTEXT, settle } from "./browser.mjs"

const [dir] = process.argv.slice(2)
if (!dir) throw new Error("usage: render.mjs <snapshot-dir>")
const snap = JSON.parse(fs.readFileSync(path.join(dir, "sections.json"), "utf8"))
const html = fs.readFileSync(path.join(dir, "page.html"), "utf8")
const out = path.join(dir, "render")
fs.mkdirSync(out, { recursive: true })
const gens = fs.existsSync(path.join(dir, "gen")) ? fs.readdirSync(path.join(dir, "gen")).filter((f) => f.endsWith(".html")).map((f) => Number(f.slice(0, -5))) : []

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" })

async function render(sec, fragment) {
  const context = await browser.newContext(CONTEXT)
  await context.routeFromHAR(path.join(dir, "page.har.zip"), { notFound: "abort" })
  const page = await context.newPage()
  await page.route(snap.url, (r) => r.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: html }))
  await page.goto(snap.url, { waitUntil: "load", timeout: 60000 })
  if (fragment != null) {
    await page.evaluate(({ sec, fragment }) => {
      const old = document.querySelector(`[data-sec="${sec}"]`)
      const host = document.createElement("div")
      host.setAttribute("data-sec", String(sec))
      host.setAttribute("data-gen", "")
      host.style.display = "block"
      host.dataset.oldHeight = String(old.getBoundingClientRect().height)
      old.replaceWith(host)
      host.attachShadow({ mode: "open" }).innerHTML = fragment
    }, { sec, fragment: fragment.replace(/asset:(\d+)/g, (m, n) => snap.assets[Number(n)] ?? m) })
  }
  await settle(page)
  if (fragment != null) {
    // The page below moves by the height difference; a fraction of a pixel would
    // re-rasterize everything below and fail the isolation check, so it is rounded.
    await page.evaluate((sec) => {
      const host = document.querySelector(`[data-sec="${sec}"][data-gen]`)
      const was = Number(host.dataset.oldHeight), now = host.getBoundingClientRect().height
      host.style.height = `${was + Math.round(now - was)}px`
    }, sec)
    await settle(page)
  }
  const name = fragment == null ? "orig" : String(sec)
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: true, timeout: 120000 })
  const boxes = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll("[data-sec]")].map((el) => {
    const r = el.getBoundingClientRect()
    return [el.getAttribute("data-sec"), { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) }]
  })))
  const height = await page.evaluate(() => document.documentElement.scrollHeight)
  let checks = null
  if (fragment != null) {
    const items = snap.sections[sec].items
    checks = await page.evaluate(({ sec, items, raw }) => {
      const host = document.querySelector(`[data-sec="${sec}"][data-gen]`)
      const root = host.shadowRoot
      const norm = (t) => t.toLowerCase().replace(/\s+/g, "")
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.parentElement?.closest("style") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) })
      let shown = ""
      for (let n; (n = walker.nextNode());) shown += n.textContent
      shown = norm(shown)
      // clamped text only has to show its beginning
      const missingText = items.filter((t) => t.text && !shown.includes(norm(t.clamped ? t.text.slice(0, 24) : t.text))).map((t) => t.text)
      const imgs = [...root.querySelectorAll("img")]
      const brokenImages = imgs.filter((i) => !i.complete || !i.naturalWidth).map((i) => i.getAttribute("src"))
      const missingImages = items.filter((t) => (t.kind === "image" || t.kind === "illustration") && !(t.src.startsWith("asset:") ? new RegExp(`${t.src}(?!\\d)`).test(raw) : raw.includes(t.src))).map((t) => t.src.slice(0, 120))
      const hr = host.getBoundingClientRect()
      const overflow = [...root.querySelectorAll("*")].filter((el) => {
        const r = el.getBoundingClientRect()
        return r.width && r.height && (r.right > hr.right + 1 || r.left < hr.left - 1)
      }).length
      // only the first family of each stack has to be there; the rest are fallbacks
      const fontsUsed = [...new Set([...root.querySelectorAll("*")].map((el) => getComputedStyle(el).fontFamily.split(",")[0].trim()))]
      const fontsMissing = fontsUsed.filter((f) => !document.fonts.check(`16px ${f}`))
      return { missingText, brokenImages, missingImages, overflow, fontsMissing }
    }, { sec, items, raw: fragment })
  }
  await context.close()
  return { name, height, boxes, checks }
}

const orig = await render(null, null)
fs.writeFileSync(path.join(out, "orig.json"), JSON.stringify(orig, null, 1))
console.log(`orig: height ${orig.height}, ${Object.keys(orig.boxes).length} sections`)
for (const sec of gens) {
  const r = await render(sec, fs.readFileSync(path.join(dir, "gen", `${sec}.html`), "utf8"))
  fs.writeFileSync(path.join(out, `${sec}.json`), JSON.stringify(r, null, 1))
  const c = r.checks
  console.log(`section ${sec}: height ${orig.boxes[sec].h} → ${r.boxes[sec].h}; missing text ${c.missingText.length}, missing images ${c.missingImages.length}, broken images ${c.brokenImages.length}, overflowing elements ${c.overflow}, fonts not loaded ${c.fontsMissing.length}`)
}
await browser.close()
