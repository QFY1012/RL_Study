// Collects the websites Awwwards lists, for domains.mjs (--list). Awwwards turns away the cloud
// machines the rest of this runs on, so this is run on a computer of one's own, in its own Google
// Chrome, shown on screen (HEADLESS=1 to hide it): if Awwwards asks whether you are a person, you
// can answer it there, and this waits (up to 2 minutes) until the page has come through.
//   node scripts/awwwards.mjs <out-dir> [listing-url]...
// Listings (default: LISTINGS) are gone through page by page (?page=2, 3, ...) until a page shows
// no entry not seen before, or PAGES pages (default 500); every entry page (/sites/<name>) is then
// opened and its link to the site it shows taken: the one that says "Visit", else the first link
// that leaves Awwwards and is not to a social network. One page at a time, PAUSE_MS (default 1500)
// apart. Writes to <out-dir>, as it goes:
//   entries.txt     the entry pages found; a listing page is not gone through again once its
//                   entries are in (delete the file to start over)
//   awwwards.tsv    entry page, site url ("-" if none was found); one in it is not opened again
//   awwwards.txt    the site urls, one per line, once done: this is the file to hand over
// Needs `npm install` (playwright-core) and Google Chrome.
import fs from "node:fs"
import { chromium } from "playwright-core"

const BASE = "https://www.awwwards.com"
const LISTINGS = [`${BASE}/websites/sites_of_the_day/`, `${BASE}/websites/`]
const [dir, ...given] = process.argv.slice(2)
if (!dir) throw new Error("usage: awwwards.mjs <out-dir> [listing-url]...")
const listings = given.length ? given : LISTINGS
const PAGES = Number(process.env.PAGES ?? 500)
const PAUSE_MS = Number(process.env.PAUSE_MS ?? 1500)
fs.mkdirSync(dir, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await chromium.launch({ channel: "chrome", headless: process.env.HEADLESS === "1" })
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "en-US" })).newPage()

// Opens url and waits until it is past any check that it is asked by a person (its title then
// stops being "Just a moment..." and the like). Returns false if it could not be opened.
async function open(url) {
  for (let k = 1; k <= 3; k++) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 })
      const end = Date.now() + 120000
      let said = false
      while (/just a moment|attention required|verify you are human|access denied/i.test(await page.title())) {
        if (!said) { console.log(`${url}: Awwwards is checking whether this is a person; answer it in the browser window if it asks`); said = true }
        if (Date.now() > end) throw new Error("still being checked after 2 minutes")
        await sleep(2000)
      }
      await page.waitForLoadState("load", { timeout: 30000 }).catch(() => {})
      return true
    } catch (e) {
      console.log(`${url}: ${e.message.split("\n")[0]}${k < 3 ? `, trying again in ${10 * k}s` : ", left out"}`)
      await sleep(10000 * k)
    }
  }
  return false
}

// 1. Entry pages, from every listing, page by page
const entriesFile = `${dir}/entries.txt`
const entries = new Set(fs.existsSync(entriesFile) ? fs.readFileSync(entriesFile, "utf8").split("\n").filter(Boolean) : [])
for (const listing of listings) {
  for (let n = 1; n <= PAGES; n++) {
    const url = n === 1 ? listing : `${listing}${listing.includes("?") ? "&" : "?"}page=${n}`
    if (!(await open(url))) break
    // lazily shown cards: scroll to the bottom once
    await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 800) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 150)) } })
    const found = await page.evaluate((BASE) => [...document.querySelectorAll("a[href]")].map((a) => new URL(a.getAttribute("href"), BASE)).filter((u) => u.hostname.endsWith("awwwards.com") && /^\/sites\/[^/]+\/?$/.test(u.pathname)).map((u) => `${BASE}${u.pathname.replace(/\/$/, "")}`), BASE)
    const fresh = [...new Set(found)].filter((e) => !entries.has(e))
    for (const e of fresh) entries.add(e)
    fs.appendFileSync(entriesFile, fresh.map((e) => e + "\n").join(""))
    console.log(`${url}: ${found.length} entries, ${fresh.length} new, ${entries.size} in all`)
    if (!fresh.length) break
    await sleep(PAUSE_MS)
  }
}

// 2. Each entry page's link to its site
const tsv = `${dir}/awwwards.tsv`
const done = new Set(fs.existsSync(tsv) ? fs.readFileSync(tsv, "utf8").split("\n").filter(Boolean).map((l) => l.split("\t")[0]) : [])
const todo = [...entries].filter((e) => !done.has(e))
console.log(`${entries.size} entry pages, ${todo.length} to open`)
const SOCIAL = /(^|\.)(awwwards\.com|facebook\.com|twitter\.com|x\.com|instagram\.com|linkedin\.com|pinterest\.com|youtube\.com|vimeo\.com|behance\.net|dribbble\.com|tiktok\.com|google\.com|apple\.com|medium\.com|github\.com|threads\.net|bsky\.app)$/
let k = 0, found = 0
for (const e of todo) {
  let site = null
  if (await open(e)) site = await page.evaluate((SOCIAL) => {
    const out = [...document.querySelectorAll("a[href]")].filter((a) => { try { const u = new URL(a.href); return /^https?:$/.test(u.protocol) && !new RegExp(SOCIAL).test(u.hostname) } catch { return false } })
    const visit = out.find((a) => /visit/i.test(`${a.textContent} ${a.getAttribute("title") ?? ""} ${a.getAttribute("aria-label") ?? ""}`))
    return (visit ?? out[0])?.href ?? null
  }, SOCIAL.source)
  fs.appendFileSync(tsv, `${e}\t${site ?? "-"}\n`)
  if (site) found++
  if (++k % 25 === 0) console.log(`${k}/${todo.length} entry pages opened, ${found} with a site link`)
  await sleep(PAUSE_MS)
}
await browser.close()

const urls = [...new Set(fs.readFileSync(tsv, "utf8").split("\n").filter(Boolean).map((l) => l.split("\t")[1]).filter((u) => u && u !== "-"))]
fs.writeFileSync(`${dir}/awwwards.txt`, urls.join("\n") + "\n")
console.log(`done: ${urls.length} site urls in ${dir}/awwwards.txt`)
