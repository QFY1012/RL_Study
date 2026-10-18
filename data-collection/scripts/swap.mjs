// Swapping a generated section into the loaded page (site.mjs), in place of the
// original's content, and back.
import { freeze } from "./browser.mjs"
import { extent, onGrid } from "./read-page.mjs"

// A section's content is hidden with visibility (nothing moves) and its backdrop, the
// layers marked data-backdrop (read-page.mjs), left showing; and with it, whole, what
// lies over it from outside (its parts, data-part); at once, with no transition (a
// page's "transition: all" would keep it showing for a while). By a style sheet of
// ours and an attribute on the section and its parts (data-hiding), not by writing the
// page's own styles: a style attribute does not always read back as it was set (a
// shorthand set to a var() reads back with its longhands empty), so one written back
// as it was read can lose what it had (a button its background).
export const hide = (page, secs) => page.evaluate((secs) => {
  if (!document.getElementById("gen-hiding")) {
    document.head.append(Object.assign(document.createElement("style"), {
      id: "gen-hiding",
      textContent: "[data-hiding] *:not([data-backdrop]), [data-part][data-hiding] { visibility: hidden !important; transition-property: none !important } [data-hiding] [data-backdrop] { visibility: visible !important; transition-property: none !important }",
    }))
  }
  for (const i of secs) for (const e of document.querySelectorAll(`[data-sec="${i}"], [data-part="${i}"]`)) e.setAttribute("data-hiding", "")
}, secs)
export const unhide = async (page) => {
  await page.evaluate(() => { for (const e of document.querySelectorAll("[data-hiding]")) e.removeAttribute("data-hiding") })
  // shown again, with its transitions: they are put at their end
  await freeze(page)
}

// The section's box as it is in the page now, screenshot.
export const shoot = (page, box) => page.screenshot({ clip: { x: box.x, y: box.y, width: box.w, height: box.h }, fullPage: true, timeout: 60000 })

// A host element for section s: put inside the section's element, over box, exactly
// its size, with html in its shadow root (the fragment's CSS and the page's cannot
// reach each other). Inside the section the host inherits the section's text
// properties and is clipped as its content was. It is painted on the layer the content
// was: the highest z-index among the content's layers in the section's stacking
// context, so what the page lays over the section (a fixed header, an image from a
// neighbouring section) stays over the new content, and what lies under it stays under
// it. The host is a grid, so the fragment's outer box stretches to fill it.
const put = (page, s, box, html) => page.evaluate(({ sec, B, html }) => {
  const old = document.querySelector(`[data-sec="${sec}"]`)
  const forms = (e) => {
    const cs = getComputedStyle(e)
    const z = cs.zIndex !== "auto" && (cs.position !== "static" || /flex|grid/.test(getComputedStyle(e.parentElement).display))
    return { z: z ? Number(cs.zIndex) : 0, context: z || cs.position === "fixed" || cs.position === "sticky" || Number(cs.opacity) < 1 || cs.transform !== "none" || cs.filter !== "none" || cs.backdropFilter !== "none" || cs.perspective !== "none" || cs.clipPath !== "none" || cs.maskImage !== "none" || cs.mixBlendMode !== "normal" || cs.isolation === "isolate" || /transform|opacity|filter|perspective/.test(cs.willChange) || /paint|layout|strict|content/.test(cs.contain), positioned: cs.position !== "static" }
  }
  let top = 0
  const visit = (e) => {
    if (e.tagName === "svg") return
    const f = forms(e)
    if (f.positioned || f.context) top = Math.max(top, f.z)
    if (!f.context) for (const c of e.children) visit(c)
  }
  for (const c of old.children) visit(c)
  const host = document.createElement("gen-section")
  host.setAttribute("data-gen", String(sec))
  const box = { left: B.x - scrollX, top: B.y - scrollY, width: B.w, height: B.h }
  const set = (style) => { for (const [p, v] of Object.entries(style)) host.style.setProperty(p, v, "important") }
  set({ position: "absolute", display: "grid", "box-sizing": "border-box", margin: "0", padding: "0", border: "0", float: "none", left: "0px", top: "0px", right: "auto", bottom: "auto", width: `${box.width}px`, height: `${box.height}px`, "min-width": "0", "min-height": "0", "max-width": "none", "max-height": "none", transform: "none", translate: "none", scale: "none", rotate: "none", opacity: "1", visibility: "visible", filter: "none", animation: "none", transition: "none", "z-index": top > 0 ? String(top) : "auto" })
  old.append(host)
  // where its containing block put it: moved by what is left over
  const at = host.getBoundingClientRect()
  set({ left: `${box.left - at.left}px`, top: `${box.top - at.top}px` })
  host.attachShadow({ mode: "open" }).innerHTML = html
}, { sec: s.i, B: box, html })
const takeOut = (page, s) => page.evaluate((sec) => document.querySelector(`[data-gen="${sec}"]`)?.remove(), s.i)

// Section s's box (site.mjs): the part of the page where its content shows, or new
// content in its place would. Content can show past its element (a heading set tighter
// than its font, a carousel running past the edge, a shadow), and part of the element
// can be covered by what lies over it (the next section pulled up over its foot);
// outside the box a generated image is the original's own pixels (images.mjs, pair),
// so none of the original may show there, and no part of the box may be out of sight.
// So, in a band around the section (the full width of the page, W x H), shot as it
// is, then with the content hidden, then with a host as a generated section would have
// over the element's own box, filled with one colour (each shot of the same band: a
// band and a full-page capture of the same place need not agree, a frosted panel
// rendering a little differently): wherever hiding the content changes the band (by
// more than NOISE), the original's content showed; wherever the host then changes it
// plainly (by more than 32 in some channel: the colour itself, not the little of it a
// frosted panel elsewhere lets through), new content would show. The band starts
// 400px above and below and is doubled until nothing differs at its edges.
// NOISE: hiding anything can change how the browser splits the page into layers, and
// what it then paints into a different layer can come out a few levels apart where
// nothing about it changed (cloudflare's dot grid, an SVG pattern the height of the
// page behind every section: up to 14 apart across the whole page when one section is
// hidden). Content that shows differs by more than that.
const NOISE = 16
export async function measure(page, s, W, H, differs) {
  for (let m = 400; ; m *= 2) {
    const top = Math.max(0, s.own.y - m), bottom = Math.min(H, s.own.y + s.own.h + m)
    const clip = { x: 0, y: top, width: W, height: bottom - top }
    const shown = await page.screenshot({ clip, fullPage: true, timeout: 60000 })
    await hide(page, [s.i])
    let hidden, probed
    try {
      hidden = await page.screenshot({ clip, fullPage: true, timeout: 60000 })
      await put(page, s, s.own, "<div style='background: #f0f'></div>")
      probed = await page.screenshot({ clip, fullPage: true, timeout: 60000 })
    } finally {
      await takeOut(page, s)
      await unhide(page)
    }
    const found = [await differs(hidden, top, shown, NOISE), await differs(probed, top, hidden, 32)].filter(Boolean)
    if (!found.length) return s.own
    const x0 = Math.min(...found.map((d) => d.x)), y0 = Math.min(...found.map((d) => d.y))
    const x1 = Math.max(...found.map((d) => d.x + d.w)), y1 = Math.max(...found.map((d) => d.y + d.h))
    if ((top > 0 && y0 <= top) || (bottom < H && y1 >= bottom)) continue
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
  }
}

// The section, other than s, whose content shows inside s's box (measure), if any:
// within the box, the page as it is against the page with that section's content
// hidden (by more than NOISE). Sections more than 1500px from the box are not looked at.
export async function crowded(page, snap, s, differs) {
  const clip = { x: s.box.x, y: s.box.y, width: s.box.w, height: s.box.h }
  const shown = await page.screenshot({ clip, fullPage: true, timeout: 60000 })
  for (const o of snap.sections) {
    const b = o.own ?? o.box
    if (o.i === s.i || b.y > s.box.y + s.box.h + 1500 || b.y + b.h < s.box.y - 1500) continue
    await hide(page, [o.i])
    let hidden
    try { hidden = await page.screenshot({ clip, fullPage: true, timeout: 60000 }) } finally { await unhide(page) }
    if (await differs(hidden, s.box.y, shown, NOISE)) return o.i
  }
  return null
}

// Renders a fragment in place of section s: its content hidden, its backdrop left as
// it is, and the fragment in a host over the section's box (put).
// Returns the box screenshot and how the fragment did (check).
export async function swap(page, snap, s, fragment) {
  await hide(page, [s.i])
  // whatever happens, the section is put back as it was
  try {
    await put(page, s, s.box, fragment.replace(/asset:(\d+)/g, (m, n) => snap.assets[Number(n)] ?? m))
    await freeze(page)
    return { png: await shoot(page, s.box), ...(await check(page, snap, s, fragment)) }
  } finally {
    await takeOut(page, s)
    await unhide(page)
  }
}

// How the swapped-in fragment did: how far its content reaches past the top or bottom
// of the box (spill: anything past it does not fit, cut off or not), the content
// checks, and whether it keeps to the page's grid (read-page.mjs, onGrid) where the
// original does: the sections around keep to it, so a section that does not stands out
// by that alone (offGrid, with where its content runs: edges). No callbacks into the
// page (a TreeWalker filter, say): with its scripts off, the browser runs none.
async function check(page, snap, s, fragment) {
  const edges = await page.evaluate(extent, { gen: s.i })
  const offGrid = onGrid(s.edges, snap.tokens.column, snap.size.w) && !onGrid(edges, snap.tokens.column, snap.size.w)
  const r = await page.evaluate(({ sec, items, raw }) => {
    const host = document.querySelector(`[data-gen="${sec}"]`)
    const root = host.shadowRoot
    const hr = host.getBoundingClientRect()
    const boxes = [...root.querySelectorAll("*")].map((el) => el.getBoundingClientRect()).filter((r) => r.width && r.height)
    const spill = Math.round(Math.max(0, ...boxes.map((r) => Math.max(r.bottom - hr.bottom, hr.top - r.top))))
    const norm = (t) => t.toLowerCase().replace(/\s+/g, "")
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    let shown = ""
    for (let n; (n = walker.nextNode());) if (!n.parentElement?.closest("style")) shown += n.textContent
    shown = norm(shown)
    // clamped text only has to show its beginning
    const missingText = items.filter((t) => t.text && !shown.includes(norm(t.clamped ? t.text.slice(0, 24) : t.text))).map((t) => t.text)
    const imgs = [...root.querySelectorAll("img")]
    const brokenImages = imgs.filter((i) => !i.complete || !i.naturalWidth).map((i) => i.getAttribute("src") ?? "").map((src) => (src.startsWith("data:") ? `${src.slice(0, 40)}...` : src))
    // an image is used when an <img> has its src (as parsed: the raw HTML may write & as
    // &amp;) or the fragment's CSS names it; asset:N is replaced in the page, so it is
    // looked for in the raw fragment
    const srcs = imgs.map((i) => i.getAttribute("src"))
    const missingImages = items.filter((t) => (t.kind === "image" || t.kind === "illustration") && !(t.src.startsWith("asset:") ? new RegExp(`${t.src}(?!\\d)`).test(raw) : srcs.includes(t.src) || raw.includes(t.src))).map((t) => t.src)
    const overflow = boxes.filter((r) => r.right > hr.right + 1 || r.left < hr.left - 1).length
    // the face each element asks for (the first family of its stack, the rest are
    // fallbacks, in its weight and style) has to be loaded
    const fontsUsed = [...new Set([...root.querySelectorAll("*")].map((el) => { const cs = getComputedStyle(el); return `${cs.fontStyle} ${cs.fontWeight} 16px ${cs.fontFamily.split(",")[0].trim()}` }))]
    const fontsMissing = fontsUsed.filter((f) => !document.fonts.check(f))
    return { spill, checks: { missingText, brokenImages, missingImages, overflow, fontsMissing } }
  }, { sec: s.i, items: s.items, raw: fragment })
  return { spill: r.spill, fits: r.spill <= 1, checks: { ...r.checks, offGrid, edges } }
}
