// Replays a recorded page and screenshots it as it is and with each generated
// section swapped in, all in the one running page.
//   node scripts/render.mjs <dir>
// The page runs its own scripts; every request is answered from page.har (anything
// not in it is aborted), and browser.mjs pins the clock and the random numbers. The
// page is read again and each section compared with the recording: only a section
// that comes back with the same content and, pixel for pixel, the same look is usable
// (replay.json), so generate.mjs picks from those and pairs.py keeps only those.
// With the page clock stopped, the original is screenshot, then for each generated
// section: the section's content is hidden, its backdrop left as it is (read-page.mjs),
// and a host element is laid over its box with the fragment in its shadow root (the
// fragment's CSS and the page's cannot reach each other); screenshot, and put back.
// Writes replay.json, render/orig.png, render/orig.json, render/<i>.png and render/<i>.json.
import fs from "node:fs"
import path from "node:path"
import { chromium } from "playwright-core"
import { CHROME, CONTEXT, load, freeze, routeMedia } from "./browser.mjs"
import { readPage, signature } from "./read-page.mjs"

const [dir] = process.argv.slice(2)
if (!dir) throw new Error("usage: render.mjs <dir>")
const snap = JSON.parse(fs.readFileSync(path.join(dir, "sections.json"), "utf8"))
const out = path.join(dir, "render")
fs.mkdirSync(out, { recursive: true })
const gens = fs.existsSync(path.join(dir, "gen")) ? fs.readdirSync(path.join(dir, "gen")).filter((f) => f.endsWith(".html")).map((f) => Number(f.slice(0, -5))) : []

const browser = await chromium.launch({ executablePath: CHROME })
const context = await browser.newContext(CONTEXT)
await context.routeFromHAR(path.join(dir, "page.har"), { notFound: "abort" })
await routeMedia(context, dir, false)
const page = await context.newPage()
await load(page, snap.url)

const again = await readPage(page)
const boxes = () => page.evaluate(() => Object.fromEntries([...document.querySelectorAll("[data-sec]")].map((el) => {
  const r = el.getBoundingClientRect()
  return [el.getAttribute("data-sec"), { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) }]
})))
const shoot = async (name) => {
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: true, timeout: 120000 })
  return { name, height: await page.evaluate(() => document.documentElement.scrollHeight), boxes: await boxes() }
}

const orig = await shoot("orig")
fs.writeFileSync(path.join(out, "orig.json"), JSON.stringify(orig, null, 1))
console.log(`orig: height ${orig.height}`)

// Each section must look the same here as in the recording, pixel for pixel: live.png
// against orig.png, each at its own run's box, compared at half size in a blank page.
// Whatever comes out differently from one run to the next shows here, whatever its
// cause (an animation that started later, a video without its frame, a canvas drawn
// differently, random content), and the section is not used: what the model was given
// would not be what the original image shows.
const blank = await context.newPage()
const url = (f) => `data:image/png;base64,${fs.readFileSync(f).toString("base64")}`
const changed = await blank.evaluate(async ({ live, shot, boxes }) => {
  const open = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src })
  const [a, b] = await Promise.all([open(live), open(shot)])
  const out = {}
  for (const [i, x, y] of boxes) {
    const w = Math.max(1, Math.round(x.w / 2)), h = Math.max(1, Math.round(x.h / 2))
    const pixels = (img, r) => { const c = new OffscreenCanvas(w, h).getContext("2d"); c.drawImage(img, r.x, r.y, r.w, r.h, 0, 0, w, h); return c.getImageData(0, 0, w, h).data }
    const p = pixels(a, x), q = pixels(b, y)
    let n = 0
    for (let k = 0; k < p.length; k += 4) if (Math.max(Math.abs(p[k] - q[k]), Math.abs(p[k + 1] - q[k + 1]), Math.abs(p[k + 2] - q[k + 2])) > 12) n++
    out[i] = n / (w * h)
  }
  return out
}, { live: url(path.join(dir, "live.png")), shot: url(path.join(out, "orig.png")), boxes: snap.sections.filter((s) => orig.boxes[s.i]).map((s) => [s.i, s.box, orig.boxes[s.i]]) })
await blank.close()

const replay = {}
for (const s of snap.sections) {
  const r = again.sections[s.i]
  replay[s.i] = !r ? { same: false, why: "missing" }
    : signature(r) !== signature(s) ? { same: false, why: r.box.h !== s.box.h ? `height ${s.box.h} → ${r.box.h}` : "content" }
    : changed[s.i] > 0.02 ? { same: false, why: `looks different (${Math.round(changed[s.i] * 100)}% of its pixels)` }
    : r.overlappedBy.length ? { same: false, why: `covered by ${r.overlappedBy.length} elements from elsewhere, e.g. ${r.overlappedBy[0]}` }
    : { same: true }
}
fs.writeFileSync(path.join(dir, "replay.json"), JSON.stringify(replay, null, 1))
console.log(`replay: ${Object.values(replay).filter((r) => r.same).length}/${snap.sections.length} sections the same as recorded; ${Object.entries(replay).filter(([, r]) => !r.same).map(([i, r]) => `#${i} ${r.why}`).join(", ") || "all"}`)

for (const sec of gens) {
  const fragment = fs.readFileSync(path.join(dir, "gen", `${sec}.html`), "utf8")
  // The section's content is hidden (visibility, so nothing moves) and its backdrop,
  // the layers marked data-backdrop, left showing: the generated version keeps the
  // original's band of color or gradient. The host lies over the section's box, exactly
  // its size, above everything (no element from elsewhere covers a usable section); it
  // is a grid, so the fragment's outer box stretches to fill it. It takes the
  // section's inherited text properties, as if it were inside it.
  await page.evaluate(({ sec, fragment }) => {
    const old = document.querySelector(`[data-sec="${sec}"]`)
    window.__styles = [...old.querySelectorAll("*")].map((e) => [e, e.getAttribute("style")])
    for (const [e] of window.__styles) e.style.setProperty("visibility", e.hasAttribute("data-backdrop") ? "visible" : "hidden", "important")
    const box = old.getBoundingClientRect()
    const host = document.createElement("div")
    host.setAttribute("data-gen", String(sec))
    const cs = getComputedStyle(old)
    for (const p of ["color", "font-family", "font-size", "font-weight", "line-height", "letter-spacing"]) host.style.setProperty(p, cs.getPropertyValue(p))
    Object.assign(host.style, { position: "absolute", display: "grid", margin: "0", zIndex: "2147483000", left: `${box.left + scrollX}px`, top: `${box.top + scrollY}px`, width: `${box.width}px`, height: `${box.height}px` })
    document.body.append(host)
    // a positioned <body> or <html> moves it: shift it by what is left over
    const at = host.getBoundingClientRect()
    host.style.left = `${box.left + scrollX + box.left - at.left}px`
    host.style.top = `${box.top + scrollY + box.top - at.top}px`
    host.attachShadow({ mode: "open" }).innerHTML = fragment
  }, { sec, fragment: fragment.replace(/asset:(\d+)/g, (m, n) => snap.assets[Number(n)] ?? m) })
  await freeze(page)
  const r = await shoot(String(sec))
  // How far the content reaches past the top or bottom of the box, cut off or not.
  // Anything past it does not fit, and the section goes back to the model.
  r.spill = await page.evaluate((sec) => {
    const host = document.querySelector(`[data-gen="${sec}"]`)
    const hr = host.getBoundingClientRect()
    let spill = 0
    for (const el of host.shadowRoot.querySelectorAll("*")) {
      const r = el.getBoundingClientRect()
      if (r.width && r.height) spill = Math.max(spill, r.bottom - hr.bottom, hr.top - r.top)
    }
    return Math.round(spill)
  }, sec)
  r.fits = r.spill <= 1
  const items = snap.sections[sec].items
  r.checks = await page.evaluate(({ sec, items, raw }) => {
    const host = document.querySelector(`[data-gen="${sec}"]`)
    const root = host.shadowRoot
    const norm = (t) => t.toLowerCase().replace(/\s+/g, "")
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.parentElement?.closest("style") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) })
    let shown = ""
    for (let n; (n = walker.nextNode());) shown += n.textContent
    shown = norm(shown)
    // clamped text only has to show its beginning
    const missingText = items.filter((t) => t.text && !shown.includes(norm(t.clamped ? t.text.slice(0, 24) : t.text))).map((t) => t.text)
    const imgs = [...root.querySelectorAll("img")]
    const brokenImages = imgs.filter((i) => !i.complete || !i.naturalWidth).map((i) => (i.getAttribute("src") ?? "").slice(0, 120))
    // an image is used when an <img> has its src (as parsed: the raw HTML may write & as
    // &amp;) or the fragment's CSS names it; asset:N is replaced in the page, so it is
    // looked for in the raw fragment
    const srcs = imgs.map((i) => i.getAttribute("src"))
    const missingImages = items.filter((t) => (t.kind === "image" || t.kind === "illustration") && !(t.src.startsWith("asset:") ? new RegExp(`${t.src}(?!\\d)`).test(raw) : srcs.includes(t.src) || raw.includes(t.src))).map((t) => t.src.slice(0, 120))
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
  fs.writeFileSync(path.join(out, `${sec}.json`), JSON.stringify(r, null, 1))
  const c = r.checks
  console.log(`section ${sec}: ${r.fits ? `fits its ${orig.boxes[sec].h}px box` : `runs ${r.spill}px past its ${orig.boxes[sec].h}px box`}; missing text ${c.missingText.length}, missing images ${c.missingImages.length}, broken images ${c.brokenImages.length}, overflowing elements ${c.overflow}, fonts not loaded ${c.fontsMissing.length}`)
  await page.evaluate((sec) => {
    document.querySelector(`[data-gen="${sec}"]`).remove()
    for (const [e, style] of window.__styles) style === null ? e.removeAttribute("style") : e.setAttribute("style", style)
  }, sec)
  await freeze(page)
}
await browser.close()
