// One site, start to end, in one loaded page: load it (browser.mjs; its scripts are
// then off and it holds still), read its sections, screenshot it, and for each chosen
// section have a model redesign it (generate.mjs), swap the design in (swap.mjs),
// screenshot it, put the pair together and check it, and send it back to the model
// while it fails a check, up to ROUNDS times. Everything is
// taken from the same page, so what the model is given is exactly what the original
// image shows. The chosen sections go through this each on its own, at once; the page
// takes one swap at a time.
//   node scripts/site.mjs <url> <dir>
// Writes to <dir>:
//   page.png           the page as loaded, full page: the original
//   sections.json      the page URL and size, design tokens, per section its box and
//                      content, and the inline SVGs as standalone files (assets)
//   looks/<i>.json     what the model is shown of the page around section i (images.mjs)
//   gen/<i>.html       the fragment; gen/<i>.json the conversation, model and rounds
//   render/<i>.png     the section's box with the fragment swapped in; render/<i>.json
//                      how it did (spill, fits, content checks)
//   pairs/<i>-orig.png, <i>-gen.png, <i>-side.png, <i>-gen.jpg   (images.mjs, pair)
//   pairs/report.json  per pair its checks and the ones it failed (none: usable)
// COUNT sections (default 2), ROUNDS revisions at most (default 2). Loading the page
// may take LOAD_SECONDS (default 300); a page that takes longer (a large WebGL scene
// drawn on the CPU, with no GPU here) is given up. Run from run.mjs, which shares out
// the CPU among the sites: the load is done when it says so (slot); a loaded page
// with its scripts off costs no CPU while it waits on the model.
// Needs ~/.config/ui-rl/judge.env in the environment and NODE_USE_ENV_PROXY=1.
import fs from "node:fs"
import path from "node:path"
import { chromium } from "playwright-core"
import { CHROME, CONTEXT, load } from "./browser.mjs"
import { readPage } from "./read-page.mjs"
import { choose, start, revision, turn } from "./generate.mjs"
import { hide, unhide, shoot, swap } from "./swap.mjs"
import { images } from "./images.mjs"

const [url, dir] = process.argv.slice(2)
if (!url || !dir) throw new Error("usage: site.mjs <url> <dir>")
const COUNT = Number(process.env.COUNT ?? 2)
const ROUNDS = Number(process.env.ROUNDS ?? 2)
const LOAD_SECONDS = Number(process.env.LOAD_SECONDS ?? 300)
const SEAM = 0.02
for (const d of ["looks", "gen", "render", "pairs"]) fs.mkdirSync(path.join(dir, d), { recursive: true })
const write = (f, data) => fs.writeFileSync(path.join(dir, f), typeof data === "string" || Buffer.isBuffer(data) ? data : JSON.stringify(data, null, 1))
const t0 = Date.now()
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(0)}s]`, ...a)

// a turn at the CPU from run.mjs; run on its own, no waiting
const slot = async (fn) => {
  if (!process.send) return fn()
  process.send("take")
  await new Promise((r) => process.once("message", r))
  try { return await fn() } finally { process.send("give") }
}
// the page takes one swap at a time
let queue = Promise.resolve()
const exclusive = (fn) => { const run = queue.then(fn); queue = run.catch(() => {}); return run }

const browser = await chromium.launch({ executablePath: CHROME, proxy: { server: process.env.HTTPS_PROXY } })
const page = await (await browser.newContext(CONTEXT)).newPage()
const { snap, pagePng, moved } = await slot(async () => {
  const late = setTimeout(() => { log(`loading took over ${LOAD_SECONDS}s, given up`); process.exit(1) }, LOAD_SECONDS * 1000)
  await load(page, url)
  clearTimeout(late)
  const { sections, assets, tokens } = await readPage(page)
  const pagePng = await page.screenshot({ path: path.join(dir, "page.png"), fullPage: true, timeout: 120000 })
  // the screenshot has to show the sections where they were read; one that moved is
  // not used (with the page's scripts off nothing should)
  const moved = await page.evaluate((sections) => sections.filter(({ i, box }) => {
    const r = document.querySelector(`[data-sec="${i}"]`).getBoundingClientRect()
    return [r.left + scrollX, r.top + scrollY, r.width, r.height].map(Math.round).join() !== [box.x, box.y, box.w, box.h].join()
  }).map(({ i }) => i), sections)
  const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }))
  return { snap: { url: page.url(), title: await page.title(), size, tokens, sections, assets }, pagePng, moved }
})
write("sections.json", snap)
log(`${snap.url}: ${snap.sections.length} sections`)
for (const s of snap.sections) console.log(`  #${s.i} <${s.tag}> y=${s.box.y} h=${s.box.h} items=${s.items.length} ${JSON.stringify(s.items.find((t) => t.text)?.text?.slice(0, 50) ?? "")}`)
if (moved.length) log(`moved after the screenshot, not used: ${moved.map((i) => `#${i}`).join(", ")}`)

const { candidates, chosen } = choose(snap, COUNT, moved)
log(`${candidates.length} candidate sections, chosen: ${chosen.map(({ s, model }) => `${s.i} (${model})`).join(", ") || "none"}`)
const pic = await images(browser, pagePng)
const report = { pairs: {} }

async function section({ s, model }) {
  const empty = await exclusive(async () => { await hide(page, [s.i]); const png = await shoot(page, s.box); await unhide(page); return png })
  const look = await pic.look(s, empty)
  write(`looks/${s.i}.json`, JSON.stringify(look))
  const messages = start(snap, s, look)
  const record = { section: s.i, model, rounds: [], messages }
  for (let round = 0; ; round++) {
    const t = Date.now()
    const { fragment, usage, finish } = await turn(model, messages)
    record.rounds.push({ seconds: (Date.now() - t) / 1000, usage, finish })
    write(`gen/${s.i}.json`, record)
    if (!fragment) { log(`section ${s.i}: no html block in the reply from ${model} (it ended: ${finish})${round ? ", kept the last one" : ", left out"}`); return }
    write(`gen/${s.i}.html`, fragment)
    log(`section ${s.i}: ${model}${round ? ` revision ${round}` : ""}, ${fragment.length} chars in ${((Date.now() - t) / 1000).toFixed(0)}s, tokens ${JSON.stringify(usage)}`)
    const r = await exclusive(() => swap(page, snap, s, fragment))
    write(`render/${s.i}.png`, r.png)
    write(`render/${s.i}.json`, { box: s.box, spill: r.spill, fits: r.fits, checks: r.checks })
    const p = await pic.pair(s, r.png)
    for (const k of ["orig", "gen", "side"]) write(`pairs/${s.i}-${k}.png`, p[k])
    write(`pairs/${s.i}-gen.jpg`, Buffer.from(p.genJpg.split(",")[1], "base64"))
    const c = r.checks
    const entry = { box: s.box, model, rounds: round + 1, spill: r.spill, seam: p.seam, ...c }
    entry.failed = [
      ["fit", !r.fits],
      ["seam", Math.max(0, ...Object.values(p.seam)) > SEAM],
      ["text", c.missingText.length > 0],
      ["images", c.missingImages.length + c.brokenImages.length > 0],
      ["overflow", c.overflow > 0],
      ["fonts", c.fontsMissing.length > 0],
    ].filter(([, bad]) => bad).map(([name]) => name)
    report.pairs[s.i] = entry
    write("pairs/report.json", report)
    log(`section ${s.i}: ${entry.failed.length ? `FAILED ${entry.failed.join(", ")}` : "ok"} (spill ${r.spill}px of its ${s.box.h}px box, seam ${Object.entries(p.seam).map(([k, v]) => `${k} ${(v * 100).toFixed(1)}%`).join(" ") || "none measured"}; missing text ${c.missingText.length}, missing images ${c.missingImages.length}, broken images ${c.brokenImages.length}, overflowing elements ${c.overflow}, fonts not loaded ${c.fontsMissing.length})`)
    if (!entry.failed.length || round === ROUNDS) return
    messages.push(revision(s, entry, p.genJpg))
  }
}

// a section whose model request still fails after the retries is left out (logged),
// so it does not take the site's other sections down with it
await Promise.all(chosen.map((c) => section(c).catch((e) => log(`section ${c.s.i}: failed, left out: ${e.message}`))))
await browser.close()
const pairs = Object.values(report.pairs)
log(`done: ${pairs.filter((p) => !p.failed.length).length}/${chosen.length} pairs usable`)
process.exit(0)
