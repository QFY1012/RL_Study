// Web tools for an agent that reads published pages (originals.py: a Pudding story's findings).
//
// They run here, outside the sandbox, since the sandbox has no network; the agent's bash stays in it.
// - web_fetch: the page's HTML as it comes from the server, turned into text, with its links.
// - web_view: the page opened in Chromium and scrolled from top to bottom the way a reader does, with the
//   text visible on screen collected at every stop, chart labels included. For pages drawn by scripts,
//   where web_fetch gets little text, and for scrolling stories whose charts change their labels.
import { execFile } from "node:child_process"
import { createRequire } from "node:module"
import { Type } from "typebox"

const PAGE_CHARS = 20000 // characters returned per call; the agent asks for the rest with offset
const STEP = 450 // px scrolled between reads, half a screen as in capture.py
const PAUSE = 600 // ms after each step, for scroll-triggered steps to run
const VIEW_SECONDS = 180

const proxy = process.env.HTTPS_PROXY || process.env.https_proxy
const cache = new Map() // url + tool -> text, so paging through a long page loads it once

const page = (text, offset = 0) => {
  const part = text.slice(offset, offset + PAGE_CHARS)
  const rest = text.length - offset - part.length
  return part + (rest > 0 ? `\n\n[${rest} more characters: call again with offset ${offset + part.length}]` : "")
}
const result = (text) => ({ content: [{ type: "text", text }], details: {} })

function htmlToText(html, base) {
  const links = []
  let s = html.replace(/<(script|style|noscript|template)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
  s = s.replace(/<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi, (_, href, inner) => {
    const label = inner.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
    try { links.push(`${label || "(no text)"} -> ${new URL(href, base).href}`) } catch {}
    return inner
  })
  s = s.replace(/<(br|\/p|\/div|\/li|\/h[1-6]|\/tr|\/figcaption|\/section|\/text)\b[^>]*>/gi, "\n")
  s = s.replace(/<(h[1-6])\b[^>]*>/gi, "\n# ").replace(/<li\b[^>]*>/gi, "\n- ")
  s = s.replace(/<[^>]+>/g, " ")
  s = s.replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;|&#x27;|&rsquo;/g, "'").replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
  const text = s.split("\n").map((l) => l.replace(/\s+/g, " ").trim()).filter(Boolean).join("\n")
  return `${text}\n\n## Links\n${[...new Set(links)].join("\n")}`
}

function curl(url) {
  return new Promise((resolve, reject) =>
    execFile("curl", ["-sL", "--max-time", "60", "-A", "Mozilla/5.0", url], { maxBuffer: 64 << 20 }, (err, out) =>
      err ? reject(new Error(`could not fetch ${url}: ${err.message.slice(0, 200)}`)) : resolve(out)))
}

async function view(url) {
  const { chromium } = createRequire("/opt/node-tools/")("playwright")
  const browser = await chromium.launch(proxy ? { proxy: { server: proxy, bypass: "127.0.0.1,localhost" } } : {})
  try {
    const p = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    await p.goto(url, { waitUntil: "load", timeout: 90_000 })
    await p.waitForTimeout(2000)
    const seen = new Set()
    const lines = []
    const t0 = Date.now()
    for (let y = 0; Date.now() - t0 < VIEW_SECONDS * 1000; y += STEP) {
      // text nodes on screen right now, in document order, svg labels included
      const shown = await p.evaluate(() => {
        const out = []
        const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
        for (let n = walk.nextNode(); n; n = walk.nextNode()) {
          const t = n.textContent.replace(/\s+/g, " ").trim()
          const el = n.parentElement
          if (!t || !el || el.closest("script,style,noscript")) continue
          const r = el.getBoundingClientRect()
          const cs = getComputedStyle(el)
          if (r.width && r.height && r.bottom > 0 && r.top < innerHeight && cs.visibility !== "hidden" && +cs.opacity !== 0) out.push(t)
        }
        return out
      })
      for (const t of shown) if (!seen.has(t)) { seen.add(t); lines.push(t) }
      const bottom = await p.evaluate((y) => { window.scrollTo(0, y); return y >= document.documentElement.scrollHeight - innerHeight }, y + STEP)
      await p.waitForTimeout(PAUSE)
      if (bottom) break
    }
    return lines.join("\n")
  } finally {
    await browser.close()
  }
}

const params = Type.Object({
  url: Type.String({ description: "The page's address" }),
  offset: Type.Optional(Type.Number({ description: "Character to start from, to read the rest of a long page" })),
})

export const webTools = [
  {
    name: "web_fetch",
    label: "web_fetch",
    description: `Fetch a web page as the server sends it and return its text, then its links. Up to ${PAGE_CHARS} characters per call; use offset for the rest. Pages drawn by scripts come back nearly empty: use web_view for them.`,
    parameters: params,
    async execute(_id, { url, offset = 0 }) {
      const key = "fetch " + url
      if (!cache.has(key)) cache.set(key, htmlToText(await curl(url), url))
      return result(page(cache.get(key), offset))
    },
  },
  {
    name: "web_view",
    label: "web_view",
    description: `Open a web page in a browser 1440 px wide, scroll it from top to bottom like a reader, and return every piece of text that was on screen, in the order it appeared, chart labels and the text of scrolling steps included. Takes up to ${VIEW_SECONDS + 90} seconds. Up to ${PAGE_CHARS} characters per call; use offset for the rest.`,
    parameters: params,
    async execute(_id, { url, offset = 0 }) {
      const key = "view " + url
      if (!cache.has(key)) cache.set(key, await view(url))
      return result(page(cache.get(key), offset))
    },
  },
]
