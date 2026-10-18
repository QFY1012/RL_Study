// How a model is asked to redesign a section from its content alone (site.mjs runs
// the conversations). The model gets what the page's designer would have, short of
// the section's own design: its text, images, illustrations and icons, each image as
// it looks, a screenshot of the page around the section with the section emptied down
// to its backdrop (looks/<i>.json), the page's fonts, loaded faces, type scale (the
// other sections' titles and body text first), colors and content column, where the
// sections around run, and where the box it goes in lies (the original's place, width
// and exact height); never the original markup or layout, so the two versions differ
// only in design decisions. A
// section that fails a check is told what is wrong, shown how it rendered, and asked
// again, in the same conversation (revision).
// The chosen sections are shared out among the models in GEN_MODELS (comma-separated,
// default deepseek-v4.1-flash,glm-5.3-flash) in turn, starting at a place that
// depends on the site, so no one model's style marks all generated sections; a
// revision goes back to the model that made the section, in its conversation.
// GEN_PROMPT=plain instead gives a short brief with the section's content (its text and
// images, each as it looks) and its box, and nothing of the page's design: no
// screenshot, fonts, type scale, colors, grid or backdrop. That is how the model designs
// with no style to go by. Only the checks such a brief can be held to are sent back
// (REVISED).
// Endpoint and key come from JUDGE_URL / DEEPSEEK_API_KEY (source
// ~/.config/ui-rl/judge.env); run with NODE_USE_ENV_PROXY=1.
const URL_ = process.env.JUDGE_URL ?? "https://api.deepseek.com/chat/completions"
export const MODELS = (process.env.GEN_MODELS ?? "deepseek-v4.1-flash,glm-5.3-flash").split(",").map((m) => m.trim()).filter(Boolean)
const PLAIN = process.env.GEN_PROMPT === "plain"
if (process.env.GEN_PROMPT && !PLAIN) throw new Error(`GEN_PROMPT is plain or unset, not ${process.env.GEN_PROMPT}`)
// the failed checks that send a section back to its model
export const REVISED = PLAIN ? ["fit", "text", "images", "overflow"] : ["fit", "seam", "text", "images", "overflow", "fonts", "grid"]
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")
// a request that has not been answered in this long is given up and retried
const REQUEST_SECONDS = Number(process.env.REQUEST_SECONDS ?? 900)
// room for the reply, thinking included: deepseek thinks for up to 27k tokens before a
// fragment of 8k characters, and a reply cut off has no fragment
const MAX_TOKENS = 65536

const texts = (s) => s.items.filter((t) => t.text)

// Sections worth redesigning: within the page's width (the swap is screenshot box by
// box), a sensible height (a navigation bar is too short), and content that
// is mostly text and images rather than a mock-up of an app built out of hundreds of
// tiny labels. Up to count of them, spread over the page, each with the model that is
// to make it; none of those in skip.
export function choose(snap, count, skip = []) {
  const { sections } = snap
  const candidates = sections.filter((s) => !skip.includes(s.i) && s.box.x >= 0 && s.box.x + s.box.w <= snap.size.w && s.box.h >= 200 && s.box.h <= 1400 && texts(s).length >= 3 && s.items.length <= 40)
  const n = Math.min(count, candidates.length)
  const first = [...snap.url].reduce((m, c) => m + c.charCodeAt(0), 0)
  return { candidates, chosen: Array.from({ length: n }, (_, k) => ({ s: candidates[Math.floor((k * candidates.length) / n)], model: MODELS[(first + k) % MODELS.length] })) }
}

const system = `You are a senior web designer. You redesign one section of an existing marketing website.
You get the section's content (in reading order), how each image looks, a screenshot of the page around the section with the section emptied, and the page's design tokens. You do not see the section's current design.
Design the section as well as you can for a 1440px-wide desktop page.

Output one HTML fragment: a <style> block followed by the markup. Rules:
- It is inserted into a shadow root that takes the place of the old section, at the full width of its slot. Style the outer box with :host or a wrapper class, never html or body.
- Use every text item exactly as given (same words, same case); do not add, drop or rewrite text. Links and buttons keep their href.
- Images, illustrations and icons are given by a src (a URL, or asset:<n>); use them as <img src="..."> or as a CSS url() with exactly that src. You may drop icons, not images or illustrations.
- Type: only the font families listed in the tokens, in the weights and styles the page has loaded (others are not available and would fall back to another font). Set text in the page's type scale, as the other sections are (their titles and body text are given), so the section reads as part of this page. Colors: stay within the page's palette.
- Grid: keep to the page's content column, as the sections around do: the outer edges of your content (text, pictures, panels) start at the column's left edge, or your layout is centered on the page. Positions are given in page x and in your box.
- Backdrop: the section's backdrop (given: the color behind it and the layers of color, gradient, image or frame lines that run through the section, which belong to the page) stays in place under your fragment and is not yours to change; keep content clear of its frame lines. Leave your outer box unpainted (no background, border or shadow on it), so the box joins the page around it with no visible edge. Cards and panels inside may use the page's background colors, kept clear of the box's edges.
- Size: the section's box is exactly the width and height given, and your outer box is stretched to fill it. Lay the content out to fit inside that height; how the space is used (where the room goes, how big images and type are) is your design decision. Nothing may reach past the top or bottom of the box, and nothing may be cut off: no hidden overflow, no heights that clip.
- Plain CSS only: no frameworks, no external stylesheets, scripts or fonts, no position: fixed.
Reply with the fragment inside one \`\`\`html fenced block and nothing else.`

// What stays behind the content: the color behind the section and the layers in it
// that paint its background (read-page.mjs, backdrop; swap.mjs keeps them).
const backdrop = (s) => {
  const layers = s.backdrop.filter((l) => l.image || l.border || l.color !== "rgba(0, 0, 0, 0)").map((l) => {
    const paint = [l.color !== "rgba(0, 0, 0, 0)" ? l.color : null, l.image, l.border && `border ${l.border}`].filter(Boolean).join(", ")
    const where = l.x <= 2 && l.w >= s.box.w - 4 ? "full width" : `x ${l.x}px to ${l.x + l.w}px`
    return `${paint} (${where}${l.opacity < 1 ? `, opacity ${l.opacity}` : ""})`
  })
  return `${s.background}${layers.length ? `; layers running through the section: ${layers.join("; ")}` : ""}`
}

// The text styles the rest of the page is set in, the way its designer would know
// them: for the other sections, what their titles are set in (the largest text in
// each) and their body text (most of the text in each), then all the styles they use,
// the most used first. Styles found only in this section are left out, as they are its
// own design.
const typeScale = (tokens, s) => {
  const style = (t) => `${t.role}: ${t.family} ${t.size}/${t.lineHeight}, ${t.weight}, ${t.letterSpacing}${t.transform === "none" ? "" : `, ${t.transform}`}`
  const other = tokens.typeScale.filter((t) => Object.keys(t.sections).some((i) => Number(i) !== s.i))
  const secs = [...new Set(other.flatMap((t) => Object.keys(t.sections).map(Number)))].filter((i) => i !== s.i).sort((a, b) => a - b)
  // the style each other section has most of by score, with the sections that have it
  const by = (score) => {
    const m = new Map()
    for (const i of secs) {
      const best = other.filter((t) => t.sections[i]).reduce((a, b) => (score(b, i) > score(a, i) ? b : a))
      m.set(best, [...(m.get(best) ?? []), i + 1])
    }
    return [...m].map(([t, n]) => `    ${style(t)} (section${n.length > 1 ? "s" : ""} ${n.join(", ")})`).join("\n")
  }
  return `  titles (the largest text in each section):\n${by((t, i) => parseFloat(t.size) * 1e6 + t.sections[i])}
  body text (most of the text in each section):\n${by((t, i) => t.sections[i])}
  all their styles (role: font size/line height, weight, letter spacing; characters set in it):
${other.slice(0, 20).map((t) => `    ${style(t)}; ${t.chars}`).join("\n")}`
}

const user = (snap, s) => {
  const { sections, tokens } = snap
  const k = sections.indexOf(s)
  const col = tokens.column, x0 = s.box.x
  const runs = (e) => (e ? `, its content runs from x ${e.left} to ${e.right}` : "")
  const around = (n) => n && `${n.background}, starts with ${JSON.stringify(texts(n)[0]?.text?.slice(0, 80) ?? "(no text)")}${runs(n.edges)}`
  const items = s.items.map((t, j) => {
    if (t.src) return `${j + 1}. ${t.kind}: ${t.src} (alt ${JSON.stringify(t.alt)}, aspect ratio ${t.aspect})`
    return `${j + 1}. ${t.kind}: ${JSON.stringify(t.text)}${t.href ? ` → ${t.href}` : ""}${t.clamped ? " (long: you may cut it off with an ellipsis)" : ""}`
  })
  return `Site: ${snap.title} (${snap.url})
Page tokens:
- fonts: heading ${tokens.fonts.heading}; subheading ${tokens.fonts.subheading}; body ${tokens.fonts.body}
- font faces loaded (family: weights): ${Object.entries(tokens.faces).map(([f, w]) => `${f}: ${w.join(", ")}`).join("; ")}
- type scale of the other sections:
${typeScale(tokens, s)}
- text colors: ${tokens.textColors.join("; ")}
- background colors: ${tokens.backgroundColors.join("; ")}
- page background: ${tokens.pageBackground}
- content column: from x ${col.left} to ${col.right} of the ${snap.size.w}px-wide page (${col.left - x0}px to ${col.right - x0}px in your box)
Section ${k + 1} of ${sections.length}. Its box runs from x ${x0} to ${x0 + s.box.w} of the page: ${s.box.w}px wide and exactly ${s.box.h}px tall.
- its backdrop (stays under your content): ${backdrop(s)}
- section above: ${around(sections[k - 1]) ?? "none"}
- section below: ${around(sections[k + 1]) ?? "none"}

Content, in reading order:
${items.join("\n")}`
}

const plainSystem = `You are a web designer. Design one section of a website for a 1440px-wide desktop page, from its content.

Output one HTML fragment: a <style> block followed by the markup. Rules:
- It is inserted into a shadow root at the full width of its slot. Style the outer box with :host or a wrapper class, never html or body.
- Use every text item exactly as given (same words, same case); do not add, drop or rewrite text. Links and buttons keep their href.
- Images, illustrations and icons are given by a src (a URL, or asset:<n>); use them as <img src="..."> or as a CSS url() with exactly that src. You may drop icons, not images or illustrations.
- The section's box is exactly the width and height given. Everything has to fit inside it, with nothing cut off.
- Plain CSS only: no frameworks, no external stylesheets, scripts or fonts, no position: fixed.
Reply with the fragment inside one \`\`\`html fenced block and nothing else.`

const plainUser = (s) => `The section's box: ${s.box.w}px wide and exactly ${s.box.h}px tall.

Content, in reading order:
${s.items.map((t, j) => t.src
    ? `${j + 1}. ${t.kind}: ${t.src} (alt ${JSON.stringify(t.alt)}, aspect ratio ${t.aspect})`
    : `${j + 1}. ${t.kind}: ${JSON.stringify(t.text)}${t.href ? ` → ${t.href}` : ""}${t.clamped ? " (long: you may cut it off with an ellipsis)" : ""}`).join("\n")}`

// The first messages of a section's conversation: the text above, then the screenshot
// of the page around the section and each image as it looks (site.mjs, looks/<i>.json),
// as image parts; with GEN_PROMPT=plain, the plain brief and the images.
const image = (url) => ({ type: "image_url", image_url: { url } })
export const start = (snap, s, look) => {
  const shown = s.items.map((t, j) => [t, j]).filter(([, j]) => look.items[j])
  return [{ role: "system", content: PLAIN ? plainSystem : system }, { role: "user", content: [
    ...(PLAIN ? [{ type: "text", text: plainUser(s) }] : [
      { type: "text", text: user(snap, s) },
      { type: "text", text: `The page around the section, at half size. The dashed outline (${s.box.w}x${s.box.h}px) is the section's box, with its content removed and its backdrop showing: your fragment goes there. The page above and below stays as it is.` },
      image(look.slot),
    ]),
    ...(shown.length ? [{ type: "text", text: "How the images, illustrations and icons look, each as it appears on the page:" }] : []),
    ...shown.flatMap(([t, j]) => [{ type: "text", text: `${j + 1}. ${t.kind} ${t.src.length > 100 ? t.src.slice(0, 100) + "..." : t.src}` }, image(look.items[j])]),
  ] }]
}

// What the model is told when its section failed a check (site.mjs, the pair's
// checks: it does not fit its box, shows a seam, leaves out or changes text, leaves
// out an image, runs past the sides, uses a face the page has not loaded or leaves the
// page's grid the original keeps to; with GEN_PROMPT=plain, only those in REVISED), with how it rendered: the generated image at
// half size, with the page above and below. Only these, which are not matters of
// taste, are sent back.
export const revision = (snap, s, p, rendered) => {
  const h = s.box.h, col = snap.tokens.column
  const failed = p.failed.filter((f) => REVISED.includes(f))
  const wrong = []
  if (failed.includes("fit")) wrong.push(`your content reaches ${p.spill}px past the top or bottom edge of the ${h}px box: everything has to fit inside ${h}px, with nothing cut off`)
  if (failed.includes("seam")) {
    const sides = Object.entries(p.seam).filter(([, v]) => v > 0.02).map(([side, v]) => `${side} (${Math.round(v * 100)}% of it)`)
    wrong.push(`a visible line runs along the ${sides.join(", ")} edge of the box, where the original joins the page with none: something you paint (a background, panel, border or shadow) meets the edge of the box. The section's backdrop is ${backdrop(s)} and stays under your fragment: leave the outer box unpainted, with panels clear of its edges`)
  }
  if (failed.includes("text")) wrong.push(`these text items are missing or changed: ${p.missingText.map((t) => JSON.stringify(t)).join("; ")}. Every text item has to appear, word for word as given`)
  if (failed.includes("images") && p.missingImages.length) wrong.push(`these images are not used: ${p.missingImages.join(", ")}. Every image and illustration has to appear, with exactly that src`)
  if (failed.includes("images") && p.brokenImages.length) wrong.push(`these images did not load: ${p.brokenImages.join(", ")}. Use each src exactly as given`)
  if (failed.includes("overflow")) wrong.push(`${p.overflow} elements reach past the left or right edge of the box`)
  if (failed.includes("fonts")) wrong.push(`these faces are not loaded by the page and fall back to another font: ${p.fontsMissing.join(", ")}. Use only the families, weights and styles the page has loaded`)
  if (failed.includes("grid")) wrong.push(`your content runs from x ${p.edges?.left} to ${p.edges?.right} of the page, off the page's grid: the sections around keep their content to the column from x ${col.left} to ${col.right} (${col.left - s.box.x}px to ${col.right - s.box.x}px in your box). Start your content's left edge on the column's, or center your layout on the page`)
  return { role: "user", content: [
    { type: "text", text: `Rendered in the page, the section has these problems:\n${wrong.map((w, k) => `${k + 1}. ${w}`).join("\n")}\nThis is how it looks (half size, with the page above and below):` },
    image(rendered),
    { type: "text", text: "Fix them, keeping every rule above. Reply with the whole fragment again." },
  ] }
}

// One request, retried after 10s, 30s and 60s when the endpoint is busy (429, 5xx),
// the connection drops or the request takes over REQUEST_SECONDS, or the reply comes
// back empty (it now and then does, with no error): with many sites at once the
// endpoint does get busy. The model's own default temperature.
async function complete(model, messages) {
  for (const wait of [10, 30, 60, null]) {
    try {
      const res = await fetch(URL_, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${KEY}` },
        body: JSON.stringify({ model, messages, max_tokens: MAX_TOKENS }),
        signal: AbortSignal.timeout(REQUEST_SECONDS * 1000),
      })
      if (res.ok) {
        const body = await res.json()
        const reply = body.choices?.[0]?.message?.content
        if (typeof reply === "string" && reply.trim()) return { reply, usage: body.usage, finish: body.choices[0].finish_reason }
        throw new Error(`empty reply, finish_reason ${body.choices?.[0]?.finish_reason}, usage ${JSON.stringify(body.usage)}`)
      }
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
// fragment. Returns the fragment, or null when the reply has none, with why the reply
// ended (finish: "length" when it was cut off at MAX_TOKENS).
export async function turn(model, messages) {
  const { reply, usage, finish } = await complete(model, messages)
  messages.push({ role: "assistant", content: reply })
  const m = reply.match(/```html\s*\n([\s\S]*?)```/)
  return { fragment: m?.[1] ?? null, usage, finish }
}
