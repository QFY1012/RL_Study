// Collects the websites to run (run.mjs --list): first those in the given lists (Mobbin's sites,
// ours), then the Tranco ranking of the top million domains in rank order, until TARGET are in.
// Every one is checked by fetching its home page, and is in only if it answers 200 with an HTML
// page in English that has a title and is not a parked domain, a bot check, an error or login page,
// or an adult or gambling site. One site per brand: google.com and google.co.uk are one, and a
// domain that redirects to another is that other.
//   node scripts/domains.mjs <out> --tranco <top-1m.csv> [--list <source>=<file>]...
// Writes, as it goes:
//   <out>.tsv           one line per site that is in: source, rank, domain, url (where its home
//                       page ended up), lang, title; a domain in it already is not checked again
//   <out>.rejected.tsv  one line per domain turned away: source, rank, domain, why
//   <out>.txt           the urls, one per line (for run.mjs --list), once done
// TARGET sites (default 4500); JOBS home pages fetched at a time (default 24), each given
// FETCH_SECONDS (default 15). Tranco domains are looked at only in the first TRANCO_MAX (default
// 100000). Needs NODE_USE_ENV_PROXY=1.
import fs from "node:fs"

const args = process.argv.slice(2)
const out = args.shift()
if (!out) throw new Error("usage: domains.mjs <out> --tranco <top-1m.csv> [--list <source>=<file>]...")
const lists = [], tranco = []
for (let k = 0; k < args.length; k += 2) {
  if (args[k] === "--list") { const [source, file] = args[k + 1].split("="); lists.push({ source, file }) }
  else if (args[k] === "--tranco") tranco.push(args[k + 1])
  else throw new Error(`unknown argument ${args[k]}`)
}
const TARGET = Number(process.env.TARGET ?? 4500)
const JOBS = Number(process.env.JOBS ?? 24)
const FETCH_SECONDS = Number(process.env.FETCH_SECONDS ?? 15)
const TRANCO_MAX = Number(process.env.TRANCO_MAX ?? 100000)

// Second-level suffixes under a country's TLD (co.uk), so the brand is the label before them.
const SUFFIXES = /\.(co|com|org|net|ac|gov|edu)\.[a-z]{2}$/
// Hosts where anyone can have a site of their own under the host's name (sub.framer.website):
// there each host is a brand of its own.
const SHARED = /\.(framer\.(website|app|ai|media)|webflow\.io|vercel\.app|netlify\.app|github\.io|pages\.dev|wixsite\.com|squarespace\.com|carrd\.co|notion\.site|super\.site|myshopify\.com|herokuapp\.com|webnode\.page|readymag\.website|cargo\.site|format\.com|tilda\.ws|glitch\.me|surge\.sh|web\.app|firebaseapp\.com)$/
const brand = (host) => { if (SHARED.test(host)) return host; const h = host.replace(SUFFIXES, ".x"); const p = h.split("."); return p[p.length - 2] ?? h }
const bare = (host) => host.toLowerCase().replace(/^www\./, "")
// Generic TLDs, and the country ones English-speaking sites use; the rest are mostly in other
// languages, and fetching them only to turn them away costs time. Tranco's only: the sites in a
// list were picked by people, and an English one can have any TLD (the language is checked).
const COUNTRY_OK = new Set(["us", "uk", "ca", "au", "nz", "ie", "io", "co", "ai", "me", "so", "gg", "sh", "fm", "ly", "tv", "to", "is", "im", "cc"])
const tldOk = (host) => { const t = host.split(".").pop(); return t.length > 2 || COUNTRY_OK.has(t) }
// What serves something other than a site (content delivery, APIs, ads, telemetry): it has no
// home page worth fetching.
const INFRA = /(^|[.-])(cdn|static|api|apis|img|assets|ads?|adservice|adsystem|analytics|tracking|pixel|telemetry|metrics|dns|ntp|smtp|push|update|edge|akamai\w*|cloudfront|fastly|gstatic|googleapis|googleusercontent|googlevideo|doubleclick|amazonaws|azureedge|msedge|trafficmanager|fbcdn|ytimg|ggpht|gvt\d)\d*([.-]|$)/
const ADULT = /porn|xxx|\bsex|sexy|nsfw|hentai|escort|onlyfans|xvideos|xhamster|nude|casino|betting|\bbet\b|poker|\bslots?\b|gambl/i
const NOT_A_HOME_PAGE = /^\s*(40\d|50\d)\b|forbidden|access denied|blocked|attention required|just a moment|are you a (robot|human)|captcha|security check|not found|page not found|for sale|buy this domain|parked|coming soon|under construction|^\s*(log ?in|sign ?in)\b|(log ?in|sign ?in) ?(to|into)\b|index of \/|default (web )?page|welcome to nginx|it works!/i

const done = new Set()
const tsv = `${out}.tsv`, rejected = `${out}.rejected.tsv`
let inCount = 0
if (fs.existsSync(tsv)) for (const line of fs.readFileSync(tsv, "utf8").split("\n").filter(Boolean)) { const [, , domain] = line.split("\t"); done.add(brand(domain)); inCount++ }
else fs.writeFileSync(tsv, "")
if (fs.existsSync(rejected)) for (const line of fs.readFileSync(rejected, "utf8").split("\n").filter(Boolean)) done.add(`checked:${line.split("\t")[2]}`)

// The candidates, in order: every list, then Tranco. What is collected is sites, so a url in a
// list (a gallery can link to a product's pricing page) stands for its site's home page.
function* candidates() {
  for (const { source, file } of lists) for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const l = line.trim()
    if (!l || l.startsWith("#")) continue
    let u
    try { u = new URL(l.includes("://") ? l : `https://${l}`) } catch { continue }
    yield { source, rank: "-", host: bare(u.hostname), url: `${u.protocol}//${u.host}/` }
  }
  for (const file of tranco) for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const [rank, host] = line.trim().split(",")
    if (!host || Number(rank) > TRANCO_MAX) continue
    yield { source: "tranco", rank, host: bare(host), url: `https://${bare(host)}/` }
  }
}

// The start of a page (at most 400KB): enough for its <html lang>, <title> and some text.
// Sent plain, or as a browser: some sites turn away a request that is not from one, and some
// (facebook) one that says it is Chrome without the rest of what Chrome sends.
const AS_BROWSER = { "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36", accept: "text/html,application/xhtml+xml", "accept-language": "en-US,en;q=0.9" }
async function fetchStart(url, headers) {
  const res = await fetch(url, { redirect: "follow", signal: AbortSignal.timeout(FETCH_SECONDS * 1000), headers })
  let html = ""
  if ((res.headers.get("content-type") ?? "").includes("text/html")) {
    const reader = res.body.getReader(), decoder = new TextDecoder()
    while (html.length < 400_000) { const { done, value } = await reader.read(); if (done) break; html += decoder.decode(value, { stream: true }) }
    reader.cancel().catch(() => {})
  } else res.body?.cancel().catch(() => {})
  return { status: res.status, url: res.url, type: res.headers.get("content-type") ?? "", html }
}

const entities = (t) => t.replace(/&amp;/g, "&").replace(/&#39;|&apos;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&nbsp;/g, " ").replace(/&#(\d+);/g, (m, n) => String.fromCodePoint(Number(n)))
// Whether c's home page is in: why not, or the line to write. Its home page is asked for plain,
// and if it answers other than 200, as a browser; a bare domain that still does not is tried
// again with www. (whatsapp.com and www.whatsapp.com differ). One that cannot be reached at all
// is not asked again as a browser.
async function check(c) {
  const get = (url, headers) => fetchStart(url, headers).catch((e) => ({ error: `fetch: ${String(e.cause?.code || e.cause?.message || e.name || e.message).slice(0, 40)}` }))
  const host0 = new URL(c.url).hostname
  const urls = [c.url, ...(!host0.startsWith("www.") && host0.split(".").length === 2 ? [c.url.replace(`//${host0}`, `//www.${host0}`)] : [])]
  let r
  for (const url of urls) {
    const first = await get(url, {})
    const got = first.error || first.status === 200 ? first : await get(url, AS_BROWSER)
    if (!r || (!got.error && (r.error || got.status === 200))) r = got
    if (!r.error && r.status === 200) break
  }
  // asked too fast (many gallery sites share a host, Framer's or Webflow's): once more, later
  if (r.status === 429) { await new Promise((ok) => setTimeout(ok, 20000)); r = await get(c.url, {}) }
  if (r.error) return { why: r.error }
  if (r.status !== 200) return { why: `HTTP ${r.status}` }
  if (!r.type.includes("text/html")) return { why: `not HTML: ${r.type.slice(0, 40)}` }
  const host = bare(new URL(r.url).hostname)
  const title = entities((/<title[^>]*>([\s\S]*?)<\/title>/i.exec(r.html)?.[1] ?? "").replace(/\s+/g, " ").trim())
  const lang = (/<html[^>]*\slang=["']?([\w-]+)/i.exec(r.html)?.[1] ?? "").toLowerCase()
  const text = r.html.replace(/<(script|style|noscript)[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").slice(0, 5000)
  const ascii = (s) => s.length ? [...s].filter((ch) => ch.charCodeAt(0) < 128).length / s.length : 1
  if (!/[\p{L}\p{N}]/u.test(title)) return { why: "no title" }
  if (ADULT.test(`${host} ${title}`)) return { why: "adult or gambling" }
  if (NOT_A_HOME_PAGE.test(title)) return { why: `not a home page: ${title.slice(0, 60)}` }
  if (lang ? !lang.startsWith("en") : ascii(title + text) < 0.95) return { why: `not English: ${lang || "no lang"}` }
  if (c.source === "tranco" && !tldOk(host)) return { why: `ended up at ${host}` }
  return { host, line: [c.source, c.rank, host, r.url, lang || "-", title.slice(0, 200)].join("\t") }
}

const t0 = Date.now()
let checked = 0
const reasons = {}
const it = candidates()
const next = () => {
  for (;;) {
    const { value: c, done: end } = it.next()
    if (end) return null
    const b = brand(c.host)
    if (done.has(b) || done.has(`checked:${c.host}`)) continue
    if (c.source === "tranco" && (!tldOk(c.host) || INFRA.test(c.host) || ADULT.test(c.host))) continue
    done.add(`checked:${c.host}`)
    return c
  }
}
const reject = (c, why) => {
  fs.appendFileSync(rejected, [c.source, c.rank, c.host, why].join("\t") + "\n")
  const k = why.split(":")[0]
  reasons[k] = (reasons[k] ?? 0) + 1
}
async function worker() {
  for (let c; inCount < TARGET && (c = next());) {
    const r = await check(c)
    checked++
    if (r.why) reject(c, r.why)
    else if (done.has(brand(r.host))) reject(c, `same site as one in: ${r.host}`)
    else { done.add(brand(r.host)); done.add(brand(c.host)); fs.appendFileSync(tsv, r.line + "\n"); inCount++ }
    if (checked % 200 === 0) console.log(`${checked} checked in ${((Date.now() - t0) / 1000).toFixed(0)}s, ${inCount} in (at ${c.source} ${c.rank}); turned away: ${Object.entries(reasons).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, n]) => `${k} ${n}`).join(", ")}`)
  }
}
await Promise.all(Array.from({ length: JOBS }, worker))
const lines = fs.readFileSync(tsv, "utf8").split("\n").filter(Boolean)
fs.writeFileSync(`${out}.txt`, lines.map((l) => l.split("\t")[3]).join("\n") + "\n")
const bySource = {}
for (const l of lines) { const s = l.split("\t")[0]; bySource[s] = (bySource[s] ?? 0) + 1 }
console.log(`${lines.length} sites in (${Object.entries(bySource).map(([s, n]) => `${s} ${n}`).join(", ")}), ${checked} checked this run, in ${((Date.now() - t0) / 1000).toFixed(0)}s: ${out}.txt`)
