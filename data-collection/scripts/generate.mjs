// Has a model redesign sections of a recorded page from their content alone.
//   node scripts/generate.mjs <dir> [count]     picks up to <count> sections (default 2)
//   node scripts/generate.mjs <dir> --revise    sends back the ones that do not fit their box or show a seam
// Writes gen/<i>.html (the fragment) and gen/<i>.json (the conversation, model, usage)
// for each. The model gets the section's text, images, illustrations and icons, the
// page's fonts and colors, and the size of the box it goes in (the original's width
// and exact height), never the original markup or layout, so the two versions differ
// only in design decisions. With --revise, every section whose pair failed "fit" or
// "seam" (pairs/report.json: it runs past its box, or its edge shows as a line where
// the original joins the page) is told what is wrong and asked again, in the same
// conversation.
// Endpoint and key come from JUDGE_URL / JUDGE_MODEL / DEEPSEEK_API_KEY
// (source ~/.config/ui-rl/judge.env); run with NODE_USE_ENV_PROXY=1.
import fs from "node:fs"
import path from "node:path"

const [dir, arg] = process.argv.slice(2)
if (!dir) throw new Error("usage: generate.mjs <dir> [count | --revise]")
const revise = arg === "--revise"
const count = revise ? 0 : Number(arg ?? 2)
const URL_ = process.env.JUDGE_URL ?? "https://api.deepseek.com/chat/completions"
const MODEL = process.env.GEN_MODEL ?? process.env.JUDGE_MODEL ?? "deepseek-v4.1-flash"
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")

const snap = JSON.parse(fs.readFileSync(path.join(dir, "sections.json"), "utf8"))
const { sections, tokens } = snap

// Sections worth redesigning: the same in the replay, not the first or last (header, footer), a sensible
// height, and content that is mostly text and images rather than a mock-up of an
// app built out of hundreds of tiny labels.
const texts = (s) => s.items.filter((t) => t.text)
// Only sections that replay with the same height and content as recorded
// (render.mjs, replay.json) are used: the pair is rendered in the replay.
const replay = JSON.parse(fs.readFileSync(path.join(dir, "replay.json"), "utf8"))
const candidates = sections.filter((s, k) => replay[s.i]?.same && k > 0 && k < sections.length - 1 && s.box.h >= 200 && s.box.h <= 1400 && texts(s).length >= 3 && s.items.length <= 40)
const step = candidates.length / Math.min(count, candidates.length)
const chosen = Array.from({ length: Math.min(count, candidates.length) }, (_, k) => candidates[Math.floor(k * step)])
if (!revise) console.log(`${candidates.length} candidate sections, chosen: ${chosen.map((s) => s.i).join(", ") || "none"}`)

const system = `You are a senior web designer. You redesign one section of an existing marketing website.
You get the section's content (in reading order) and the page's design tokens. You do not see the current design.
Design the section as well as you can for a 1440px-wide desktop page.

Output one HTML fragment: a <style> block followed by the markup. Rules:
- It is inserted into a shadow root that takes the place of the old section, at the full width of its slot. Style the outer box with :host or a wrapper class, never html or body.
- Use every text item exactly as given (same words, same case); do not add, drop or rewrite text. Links and buttons keep their href.
- Images, illustrations and icons are given by a src (a URL, or asset:<n>); use them as <img src="..."> or as a CSS url() with exactly that src. You may drop icons, not images or illustrations.
- Fonts: only the font families listed in the tokens (they are already loaded). Colors: stay within the page's palette.
- Backdrop: the section's backdrop (given: the color behind it and any full-section layers of color, gradient or image) stays in place under your fragment and is not yours to change. Leave your outer box unpainted (no background, border or shadow on it), so the box joins the page around it with no visible edge. Cards and panels inside may use the page's background colors, kept clear of the box's edges.
- Size: the section's box is exactly the width and height given, and your outer box is stretched to fill it. Lay the content out to fit inside that height; how the space is used (where the room goes, how big images and type are) is your design decision. Nothing may reach past the top or bottom of the box, and nothing may be cut off: no hidden overflow, no heights that clip.
- Plain CSS only: no frameworks, no external stylesheets, scripts or fonts, no position: fixed.
Reply with the fragment inside one \`\`\`html fenced block and nothing else.`

// What stays behind the content: the color behind the section and the layers in it
// that paint its background (read-page.mjs, backdrop; render.mjs keeps them).
const backdrop = (s) => {
  const layers = s.backdrop.filter((l) => l.image || l.color !== "rgba(0, 0, 0, 0)")
    .map((l) => [l.color !== "rgba(0, 0, 0, 0)" ? l.color : null, l.image].filter(Boolean).join(" with ") + (l.opacity < 1 ? ` at opacity ${l.opacity}` : ""))
  return `${s.background}${layers.length ? `, under full-section layers: ${layers.join("; ")}` : ""}`
}

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
Section ${k + 1} of ${sections.length}. Its box is ${s.box.w}px wide and exactly ${s.box.h}px tall.
- its backdrop (stays under your content): ${backdrop(s)}
- section above: ${around(sections[k - 1]) ?? "none"}
- section below: ${around(sections[k + 1]) ?? "none"}

Content, in reading order:
${items.join("\n")}`
}

// One request, retried after 10s, 30s and 60s when the endpoint is busy (429, 5xx)
// or the connection drops: with many sites at once the endpoint does get busy.
async function complete(messages) {
  for (const wait of [10, 30, 60, null]) {
    try {
      const res = await fetch(URL_, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${KEY}` },
        body: JSON.stringify({ model: MODEL, messages, temperature: 0.7, max_tokens: 32000 }),
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

// One turn of a section's conversation: sends the messages, keeps the reply's
// fragment. Returns the fragment, or null when the reply has none.
async function turn(sec, messages) {
  const body = await complete(messages).catch((e) => { throw new Error(`section ${sec}: ${e.message}`) })
  const reply = body.choices?.[0]?.message?.content
  if (typeof reply !== "string") throw new Error(`section ${sec}: no content, finish_reason ${body.choices?.[0]?.finish_reason}, usage ${JSON.stringify(body.usage)}`)
  messages.push({ role: "assistant", content: reply })
  const m = reply.match(/```html\s*\n([\s\S]*?)```/)
  return { fragment: m?.[1] ?? null, usage: body.usage }
}

const save = (sec, record, fragment) => {
  fs.writeFileSync(path.join(dir, "gen", `${sec}.html`), fragment)
  fs.writeFileSync(path.join(dir, "gen", `${sec}.json`), JSON.stringify(record, null, 1))
}

fs.mkdirSync(path.join(dir, "gen"), { recursive: true })
if (!revise) {
  // all chosen sections are asked for at once
  await Promise.all(chosen.map(async (s) => {
    const t = Date.now()
    const messages = [{ role: "system", content: system }, { role: "user", content: user(s) }]
    const { fragment, usage } = await turn(s.i, messages)
    if (!fragment) { console.log(`section ${s.i}: no html block in the reply, skipped`); return }
    save(s.i, { section: s.i, model: MODEL, rounds: [{ seconds: (Date.now() - t) / 1000, usage }], messages }, fragment)
    console.log(`section ${s.i}: ${fragment.length} chars in ${((Date.now() - t) / 1000).toFixed(0)}s, tokens ${JSON.stringify(usage)}`)
  }))
} else {
  const report = JSON.parse(fs.readFileSync(path.join(dir, "pairs", "report.json"), "utf8")).pairs
  const misses = Object.entries(report).filter(([, p]) => p.failed.includes("fit") || p.failed.includes("seam")).map(([i, p]) => [Number(i), p])
  console.log(`${misses.length} sections to revise${misses.length ? `: ${misses.map(([i, p]) => `${i} (${p.failed.filter((f) => f === "fit" || f === "seam").join(", ")})`).join(", ")}` : ""}`)
  await Promise.all(misses.map(async ([i, p]) => {
    const t = Date.now()
    const record = JSON.parse(fs.readFileSync(path.join(dir, "gen", `${i}.json`), "utf8"))
    const h = sections[i].box.h
    const wrong = []
    if (p.failed.includes("fit")) wrong.push(`your content reaches ${p.spill}px past the edge of the ${h}px box`)
    if (p.failed.includes("seam")) {
      const sides = Object.entries(p.seam).filter(([, v]) => v > 0.02).map(([side, v]) => `${side} (${Math.round(v * 100)}% of it)`)
      wrong.push(`a visible line runs along the ${sides.join(", ")} edge of the box, where the original joins the page with none: something you paint (a background, panel, border or shadow) meets the edge of the box. The section's backdrop is ${backdrop(sections[i])} and stays under your fragment`)
    }
    record.messages.push({ role: "user", content: `Rendered in the page, ${wrong.join("; and ")}. Change the design so everything fits inside ${h}px and the outer box is unpainted, with panels clear of its edges, keeping every rule above. Reply with the whole fragment again.` })
    const { fragment, usage } = await turn(i, record.messages)
    record.rounds.push({ seconds: (Date.now() - t) / 1000, usage, failed: p.failed, spill: p.spill, seam: p.seam })
    if (!fragment) { console.log(`section ${i}: no html block in the revision, kept the last one`); fs.writeFileSync(path.join(dir, "gen", `${i}.json`), JSON.stringify(record, null, 1)); return }
    save(i, record, fragment)
    console.log(`section ${i}: revised (${wrong.map((w) => w.split(":")[0]).join("; ")}) in ${((Date.now() - t) / 1000).toFixed(0)}s`)
  }))
}
