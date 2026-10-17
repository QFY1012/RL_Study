// Has a model redesign sections of a snapshotted page from their content alone.
//   node scripts/generate.mjs <snapshot-dir> [count]
// Picks up to <count> sections (default 2) and writes gen/<i>.html (the fragment)
// and gen/<i>.json (prompt, model, usage) for each. The model gets the section's
// text, images, illustrations and icons plus the page's fonts and colors, never the original
// markup or layout, so the two versions differ only in design decisions.
// Endpoint and key come from JUDGE_URL / JUDGE_MODEL / DEEPSEEK_API_KEY
// (source ~/.config/ui-rl/judge.env); run with NODE_USE_ENV_PROXY=1.
import fs from "node:fs"
import path from "node:path"

const [dir, countArg] = process.argv.slice(2)
if (!dir) throw new Error("usage: generate.mjs <snapshot-dir> [count]")
const count = Number(countArg ?? 2)
const URL_ = process.env.JUDGE_URL ?? "https://api.deepseek.com/chat/completions"
const MODEL = process.env.GEN_MODEL ?? process.env.JUDGE_MODEL ?? "deepseek-v4.1-flash"
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")

const snap = JSON.parse(fs.readFileSync(path.join(dir, "sections.json"), "utf8"))
const { sections, tokens } = snap

// Sections worth redesigning: rendered faithfully, not the first or last (header, footer), a sensible
// height, and content that is mostly text and images rather than a mock-up of an
// app built out of hundreds of tiny labels.
const texts = (s) => s.items.filter((t) => t.text)
// Only sections whose offline render matches the live page (fidelity.py) are used:
// a pair is only as good as the original it is measured against.
const fidelity = JSON.parse(fs.readFileSync(path.join(dir, "fidelity.json"), "utf8")).sections
const candidates = sections.filter((s, k) => fidelity[s.i]?.ok && k > 0 && k < sections.length - 1 && s.box.h >= 200 && s.box.h <= 1400 && texts(s).length >= 3 && s.items.length <= 40)
const step = candidates.length / Math.min(count, candidates.length)
const chosen = Array.from({ length: Math.min(count, candidates.length) }, (_, k) => candidates[Math.floor(k * step)])
console.log(`${candidates.length} candidate sections, chosen: ${chosen.map((s) => s.i).join(", ") || "none"}`)

const system = `You are a senior web designer. You redesign one section of an existing marketing website.
You get the section's content (in reading order) and the page's design tokens. You do not see the current design.
Design the section as well as you can for a 1440px-wide desktop page.

Output one HTML fragment: a <style> block followed by the markup. Rules:
- It is inserted into a shadow root that takes the place of the old section, at the full width of its slot. Style the outer box with :host or a wrapper class, never html or body.
- Use every text item exactly as given (same words, same case); do not add, drop or rewrite text. Links and buttons keep their href.
- Images, illustrations and icons are given by a src (a URL, or asset:<n>); use them as <img src="..."> or as a CSS url() with exactly that src. You may drop icons, not images or illustrations.
- Fonts: only the font families listed in the tokens (they are already loaded). Colors: stay within the page's palette; the section background may be any of the page's background colors.
- Plain CSS only: no frameworks, no external stylesheets, scripts or fonts, no position: fixed.
Reply with the fragment inside one \`\`\`html fenced block and nothing else.`

const user = (s) => {
  const k = sections.indexOf(s)
  const around = (n) => n && `${n.background}, starts with ${JSON.stringify(texts(n)[0]?.text?.slice(0, 80) ?? "(no text)")}`
  const items = s.items.map((t, j) => {
    if (t.src) return `${j + 1}. ${t.kind}: ${t.src} (alt ${JSON.stringify(t.alt)}, aspect ratio ${t.aspect})`
    return `${j + 1}. ${t.kind}: ${JSON.stringify(t.text)}${t.href ? ` → ${t.href}` : ""}${t.clamped ? " (long: you may cut it off with an ellipsis)" : ""}`
  })
  return `Site: ${snap.title} (${snap.url})
Page tokens:
- fonts: heading ${tokens.fonts.heading}; subheading ${tokens.fonts.subheading}; body ${tokens.fonts.body}
- text colors: ${tokens.textColors.join("; ")}
- background colors: ${tokens.backgroundColors.join("; ")}
- page background: ${tokens.pageBackground}
- the other sections keep their content within ${tokens.contentWidth}px
Section ${k + 1} of ${sections.length}.
- section above: ${around(sections[k - 1]) ?? "none"}
- section below: ${around(sections[k + 1]) ?? "none"}

Content, in reading order:
${items.join("\n")}`
}

// One request, retried after 10s, 30s and 60s when the endpoint is busy (429, 5xx)
// or the connection drops: with many sites at once the endpoint does get busy.
async function complete(prompt) {
  for (const wait of [10, 30, 60, null]) {
    try {
      const res = await fetch(URL_, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${KEY}` },
        body: JSON.stringify({ model: MODEL, messages: [{ role: "system", content: system }, { role: "user", content: prompt }], temperature: 0.7, max_tokens: 32000 }),
      })
      if (res.ok) return await res.json()
      const text = (await res.text()).slice(0, 300)
      if (wait == null || !(res.status === 429 || res.status >= 500)) throw new Error(`HTTP ${res.status} ${text}`)
      console.log(`HTTP ${res.status}, retrying in ${wait}s`)
    } catch (e) {
      if (wait == null || e.message.startsWith("HTTP")) throw e
      console.log(`${e.message}, retrying in ${wait}s`)
    }
    await new Promise((r) => setTimeout(r, wait * 1000))
  }
}

// All chosen sections are asked for at once.
fs.mkdirSync(path.join(dir, "gen"), { recursive: true })
await Promise.all(chosen.map(async (s) => {
  const prompt = user(s)
  const t = Date.now()
  const body = await complete(prompt).catch((e) => { throw new Error(`section ${s.i}: ${e.message}`) })
  const reply = body.choices?.[0]?.message?.content
  if (typeof reply !== "string") throw new Error(`section ${s.i}: no content, finish_reason ${body.choices?.[0]?.finish_reason}, usage ${JSON.stringify(body.usage)}`)
  const m = reply.match(/```html\s*\n([\s\S]*?)```/)
  if (!m) { console.log(`section ${s.i}: no html block in the reply, skipped`); return }
  fs.writeFileSync(path.join(dir, "gen", `${s.i}.html`), m[1])
  fs.writeFileSync(path.join(dir, "gen", `${s.i}.json`), JSON.stringify({ section: s.i, model: MODEL, seconds: (Date.now() - t) / 1000, usage: body.usage, system, prompt }, null, 1))
  console.log(`section ${s.i}: ${m[1].length} chars in ${((Date.now() - t) / 1000).toFixed(0)}s, tokens ${JSON.stringify(body.usage)}`)
}))
