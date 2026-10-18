// Collects the websites that design galleries list, for domains.mjs (--list): each gallery's
// sitemap gives its entry pages, and each entry page links to the site it shows; that link is
// taken as written (GALLERIES). Each gallery is asked for JOBS pages at a time (default 5), with
// PAUSE_MS (default 300) between one and the next.
//   node scripts/galleries.mjs <out-dir> [gallery]...      (default: every gallery)
// Writes <out-dir>/<gallery>.tsv (entry page, site url) as it goes, and <out-dir>/<gallery>.txt
// (the site urls, one per line) once done; an entry page in the .tsv already is not fetched again.
// Needs NODE_USE_ENV_PROXY=1.
import fs from "node:fs"

// Per gallery: its sitemaps (or a sitemap index, whose sitemaps are those matching `maps`), what
// in them is an entry page, and the link on an entry page to the site it shows.
const GALLERIES = {
  cssnectar: {
    index: "https://cssnectar.com/sitemap_index.xml", maps: /site-sitemap\d*\.xml$/,
    entry: /^https:\/\/cssnectar\.com\/css-gallery-inspiration\/[^/]+\/$/,
    site: /<a [^>]*href="([^"]+)"[^>]*class="gray-btn"/,
  },
  "minimal-gallery": {
    index: "https://minimal.gallery/wp-sitemap.xml", maps: /wp-sitemap-posts-post-\d+\.xml$/,
    entry: /^https:\/\/minimal\.gallery\/[^/]+\/$/,
    site: /href="([^"]+)\?ref=minimal\.gallery"/,
  },
  saaslandingpage: {
    index: "https://saaslandingpage.com/sitemap_index.xml", maps: /\/post-sitemap\d*\.xml$/,
    entry: /^https:\/\/saaslandingpage\.com\/[^/]+\/$/,
    site: /<a id="ext-link-\d+"[^>]*href="([^"]+)"/,
  },
}

const [dir, ...only] = process.argv.slice(2)
if (!dir) throw new Error(`usage: galleries.mjs <out-dir> [${Object.keys(GALLERIES).join("|")}]...`)
fs.mkdirSync(dir, { recursive: true })
const JOBS = Number(process.env.JOBS ?? 5)
const PAUSE_MS = Number(process.env.PAUSE_MS ?? 300)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// A page's text; a 429 or 5xx is tried again after 10s, 30s and 60s.
async function get(url) {
  for (const wait of [10, 30, 60, null]) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(30000), headers: { "accept-language": "en-US,en;q=0.9" } })
      if (res.ok) return await res.text()
      if (wait === null || !(res.status === 429 || res.status >= 500)) throw new Error(`HTTP ${res.status}`)
    } catch (e) { if (wait === null || /^HTTP 4/.test(e.message)) throw e }
    console.log(`${url}: trying again in ${wait}s`)
    await sleep(wait * 1000)
  }
}
const locs = (xml) => [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((m) => m[1].replace(/&amp;/g, "&"))

async function gallery(name, g) {
  const tsv = `${dir}/${name}.tsv`
  const done = new Set(fs.existsSync(tsv) ? fs.readFileSync(tsv, "utf8").split("\n").filter(Boolean).map((l) => l.split("\t")[0]) : [])
  const maps = locs(await get(g.index)).filter((u) => g.maps.test(u))
  const entries = []
  for (const m of maps) { entries.push(...locs(await get(m)).filter((u) => g.entry.test(u))); await sleep(PAUSE_MS) }
  // newest first: sitemaps list a gallery's entries oldest first, and the oldest sites are the
  // likeliest to be gone
  const todo = [...new Set(entries)].reverse().filter((u) => !done.has(u))
  console.log(`${name}: ${maps.length} sitemaps, ${new Set(entries).size} entry pages, ${todo.length} to fetch`)
  let n = 0, found = 0, missing = 0
  const worker = async () => {
    for (let e; (e = todo.shift());) {
      let html = ""
      try { html = await get(e) } catch (err) { console.log(`${name}: ${e}: ${err.message}`) }
      const url = g.site.exec(html)?.[1]?.replace(/&amp;/g, "&").trim()
      fs.appendFileSync(tsv, `${e}\t${url ?? "-"}\n`)
      url ? found++ : missing++
      if (++n % 200 === 0) console.log(`${name}: ${n} fetched, ${found} with a site link, ${missing} without`)
      await sleep(PAUSE_MS)
    }
  }
  await Promise.all(Array.from({ length: JOBS }, worker))
  const urls = fs.readFileSync(tsv, "utf8").split("\n").filter(Boolean).map((l) => l.split("\t")[1]).filter((u) => u && u !== "-" && /^https?:\/\//.test(u))
  fs.writeFileSync(`${dir}/${name}.txt`, [...new Set(urls)].join("\n") + "\n")
  console.log(`${name}: done, ${new Set(urls).size} site urls in ${dir}/${name}.txt`)
}

const names = only.length ? only : Object.keys(GALLERIES)
await Promise.all(names.map((n) => gallery(n, GALLERIES[n])))
