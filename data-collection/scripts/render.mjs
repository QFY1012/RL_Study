// Replays a recorded page and screenshots it as it is and with each generated
// section swapped in, all in the one running page.
//   node scripts/render.mjs <dir>
// The page runs its own scripts; every request is answered from page.har (anything
// not in it is aborted), and browser.mjs pins the clock and the random numbers. The
// page is read again and each section compared with the recording: only a section
// that comes back with the same height and content is usable (replay.json), so
// generate.mjs picks from those.
// With the page clock stopped, the original is screenshot, then for each generated
// section: the section is swapped for a host element of the same height with the
// fragment in its shadow root (the fragment's CSS and the page's cannot reach each other; inherited
// properties such as font and color still flow in), screenshot, and swapped back.
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

// the same section, with the same content, in the replay as in the recording
const again = await readPage(page)
const replay = {}
for (const s of snap.sections) {
  const r = again.sections[s.i]
  const videos = r ? await page.evaluate((i) => [...document.querySelector(`[data-sec="${i}"]`).querySelectorAll("video")].filter((v) => v.readyState < 2).length, s.i) : 0
  replay[s.i] = !r ? { same: false, why: "missing" }
    : signature(r) !== signature(s) ? { same: false, why: r.box.h !== s.box.h ? `height ${s.box.h} → ${r.box.h}` : "content" }
    : videos ? { same: false, why: `${videos} videos without a frame` }
    : r.overlappedBy.length ? { same: false, why: `covered by ${r.overlappedBy.length} elements from elsewhere, e.g. ${r.overlappedBy[0]}` }
    : { same: true }
}
fs.writeFileSync(path.join(dir, "replay.json"), JSON.stringify(replay, null, 1))
console.log(`replay: ${Object.values(replay).filter((r) => r.same).length}/${snap.sections.length} sections the same as recorded; ${Object.entries(replay).filter(([, r]) => !r.same).map(([i, r]) => `#${i} ${r.why}`).join(", ") || "all"}`)

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

for (const sec of gens) {
  const fragment = fs.readFileSync(path.join(dir, "gen", `${sec}.html`), "utf8")
  // The host takes the old section's exact box height, so the page around it does
  // not move; it is a grid, so the fragment's outer box stretches to fill it. It also
  // takes the old section's own background color, which the model is told is fixed:
  // a section that paints its own background keeps it.
  await page.evaluate(({ sec, fragment }) => {
    const old = document.querySelector(`[data-sec="${sec}"]`)
    const host = document.createElement("div")
    host.setAttribute("data-sec", String(sec))
    host.setAttribute("data-gen", "")
    host.style.display = "grid"
    host.style.height = `${old.getBoundingClientRect().height}px`
    host.style.backgroundColor = getComputedStyle(old).backgroundColor
    window.__swapped = old
    old.replaceWith(host)
    host.attachShadow({ mode: "open" }).innerHTML = fragment
  }, { sec, fragment: fragment.replace(/asset:(\d+)/g, (m, n) => snap.assets[Number(n)] ?? m) })
  await freeze(page)
  const r = await shoot(String(sec))
  // How far the content reaches past the top or bottom of the box, cut off or not.
  // Anything past it does not fit, and the section goes back to the model.
  r.spill = await page.evaluate((sec) => {
    const host = document.querySelector(`[data-sec="${sec}"][data-gen]`)
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
  await page.evaluate((sec) => document.querySelector(`[data-sec="${sec}"][data-gen]`).replaceWith(window.__swapped), sec)
  await freeze(page)
}
await browser.close()
