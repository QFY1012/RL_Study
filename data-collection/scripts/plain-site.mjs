// A whole home page designed by a model from a few words about the site: its name and
// what it is (the home page's <title> and meta description), nothing else. To see what a
// model makes when it decides everything itself, next to what the site's designer made.
// With --text, the model also gets every piece of text the real home page shows, in
// reading order (as site.mjs read it: <run-dir>/<host>/sections.json), to use word for
// word with none of its own: the same task with the content fixed, as a report's is.
//   node scripts/plain-site.mjs <out-dir> [--text <run-dir>] <url>...      (or --list <file>)
// Writes <out-dir>/<host>.html (the page), <host>.json (the brief, the reply, usage) and
// <host>.png (the page at 1440px wide, full page); with --text, also how many of the
// text items the page shows. GEN_MODEL picks the model (default deepseek-v4.1-flash), on
// JUDGE_URL with DEEPSEEK_API_KEY (source ~/.config/ui-rl/judge.env); run with
// NODE_USE_ENV_PROXY=1.
import fs from "node:fs"
import path from "node:path"
import { chromium } from "playwright-core"
import { CHROME } from "./browser.mjs"

const args = process.argv.slice(2)
const out = args.shift()
if (!out) throw new Error("usage: plain-site.mjs <out-dir> [--text <run-dir>] <url>... | --list <file>")
const textRoot = args[0] === "--text" ? (args.shift(), args.shift()) : null
const urls = args[0] === "--list" ? fs.readFileSync(args[1], "utf8").split("\n").map((l) => l.trim()).filter(Boolean) : args
const URL_ = process.env.JUDGE_URL ?? "https://api.deepseek.com/chat/completions"
const MODEL = process.env.GEN_MODEL ?? "deepseek-v4.1-flash"
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")
fs.mkdirSync(out, { recursive: true })

const SYSTEM = `Design the home page of the website described by the user, for a 1440px-wide desktop screen.
Output one complete HTML file with its CSS inside; no external resources (no images, fonts or scripts from elsewhere).${textRoot ? `
The user gives all of the page's text. Use every piece of it exactly as given (same words), and add no text of your own; how it is laid out, grouped and ordered is up to you.` : ""}
Reply with the HTML inside one \`\`\`html fenced block and nothing else.`

const unescape = (s) => s.replace(/&amp;/g, "&").replace(/&#0?39;|&apos;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ").trim()
// the home page's title and description, as a search result shows them
async function about(url) {
  const html = await (await fetch(url, { signal: AbortSignal.timeout(20000), headers: { "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36" } })).text()
  const title = unescape(html.match(/<title[^>]*>([^<]*)<\/title>/i)?.[1] ?? "")
  const meta = (name) => html.match(new RegExp(`<meta[^>]+(?:name|property)=["']${name}["'][^>]*>`, "i"))?.[0].match(/content=["']([^"']*)["']/i)?.[1]
  return { title, description: unescape(meta("description") ?? meta("og:description") ?? "") }
}
// the real page's text items in reading order, across its sections
const texts = (host) => JSON.parse(fs.readFileSync(path.join(textRoot, host, "sections.json"), "utf8")).sections.flatMap((s) => s.items.filter((t) => t.text))

async function one(url) {
  const host = new URL(url).hostname.replace(/^www\./, "")
  const t = Date.now()
  const { title, description } = await about(url)
  let brief = `Website: ${host}\nTitle: ${title || "(none)"}\nDescription: ${description || "(none)"}`
  if (textRoot) brief += `\n\nThe page's text, in reading order:\n${texts(host).map((x, j) => `${j + 1}. ${x.kind}: ${JSON.stringify(x.text)}${x.href ? ` → ${x.href}` : ""}`).join("\n")}`
  const messages = [{ role: "system", content: SYSTEM }, { role: "user", content: brief }]
  const res = await fetch(URL_, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${KEY}` },
    body: JSON.stringify({ model: MODEL, messages, max_tokens: 65536 }),
    signal: AbortSignal.timeout(900_000),
  })
  if (!res.ok) throw new Error(`${host}: HTTP ${res.status} ${(await res.text()).slice(0, 300)}`)
  const body = await res.json()
  const reply = body.choices?.[0]?.message?.content ?? ""
  fs.writeFileSync(path.join(out, `${host}.json`), JSON.stringify({ url, model: MODEL, messages, reply, usage: body.usage, finish: body.choices?.[0]?.finish_reason }, null, 1))
  const html = reply.match(/```html\s*\n([\s\S]*?)```/)?.[1]
  if (!html) throw new Error(`${host}: no html block in the reply (it ended: ${body.choices?.[0]?.finish_reason})`)
  fs.writeFileSync(path.join(out, `${host}.html`), html)
  console.log(`${host}: brief of ${brief.length} chars; ${html.length} chars in ${Math.round((Date.now() - t) / 1000)}s, tokens ${JSON.stringify(body.usage)}`)
  return host
}

const done = (await Promise.allSettled(urls.map(one))).flatMap((r) => (r.status === "fulfilled" ? [r.value] : (console.log(r.reason.message), [])))
const browser = await chromium.launch({ executablePath: CHROME })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
for (const host of done) {
  await page.goto(`file://${path.resolve(out, `${host}.html`)}`, { waitUntil: "load" })
  await page.waitForTimeout(1000)
  await page.screenshot({ path: path.join(out, `${host}.png`), fullPage: true })
  // with --text: the items whose words the page shows (as written, whatever the CSS case)
  const shown = textRoot ? await page.evaluate((items) => {
    const norm = (s) => s.replace(/\s+/g, " ").trim().toLowerCase(), all = norm(document.body.textContent)
    return items.filter((x) => all.includes(norm(x))).length
  }, texts(host).map((x) => x.text)) : null
  console.log(`${host}: 1440x${await page.evaluate(() => document.documentElement.scrollHeight)}${textRoot ? `, shows ${shown} of the ${texts(host).length} text items` : ""}`)
}
await browser.close()
