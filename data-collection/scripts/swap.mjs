// Swapping a generated section into the loaded page (site.mjs), in place of the
// original's content, and back.
import { freeze } from "./browser.mjs"

// A section's content is hidden with visibility (nothing moves) and its backdrop, the
// layers marked data-backdrop (read-page.mjs), left showing; unhide puts every style back.
export const hide = (page, secs) => page.evaluate((secs) => {
  window.__styles = secs.flatMap((i) => [...document.querySelector(`[data-sec="${i}"]`).querySelectorAll("*")].map((e) => [e, e.getAttribute("style")]))
  for (const [e] of window.__styles) e.style.setProperty("visibility", e.hasAttribute("data-backdrop") ? "visible" : "hidden", "important")
}, secs)
export const unhide = async (page) => {
  await page.evaluate(() => { for (const [e, style] of window.__styles) style === null ? e.removeAttribute("style") : e.setAttribute("style", style) })
  // restored styles can start transitions: they are put at their end
  await freeze(page)
}

// The section's box as it is in the page now, screenshot.
export const shoot = (page, box) => page.screenshot({ clip: { x: box.x, y: box.y, width: box.w, height: box.h }, fullPage: true, timeout: 60000 })

// Renders a fragment in place of section s: its content hidden, its backdrop left as
// it is, and a host element put inside the section, over its box, exactly its size,
// with the fragment in its shadow root (the fragment's CSS and the page's cannot reach
// each other). Inside the section the host inherits the section's text properties and
// is clipped as its content was. It is painted on the layer the content was: the
// highest z-index among the content's layers in the section's stacking context, so
// what the page lays over the section (a fixed header, an image from a neighbouring
// section) stays over the new content, and what lies under it stays under it. The host
// is a grid, so the fragment's outer box stretches to fill it.
// Returns the box screenshot and how the fragment did (check).
export async function swap(page, snap, s, fragment) {
  await hide(page, [s.i])
  // whatever happens, the section is put back as it was
  try {
    await page.evaluate(({ sec, fragment }) => {
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
      const box = old.getBoundingClientRect()
      const set = (style) => { for (const [p, v] of Object.entries(style)) host.style.setProperty(p, v, "important") }
      set({ position: "absolute", display: "grid", "box-sizing": "border-box", margin: "0", padding: "0", border: "0", float: "none", left: "0px", top: "0px", right: "auto", bottom: "auto", width: `${box.width}px`, height: `${box.height}px`, "min-width": "0", "min-height": "0", "max-width": "none", "max-height": "none", transform: "none", translate: "none", scale: "none", rotate: "none", opacity: "1", visibility: "visible", filter: "none", animation: "none", transition: "none", "z-index": top > 0 ? String(top) : "auto" })
      old.append(host)
      // where its containing block put it: moved by what is left over
      const at = host.getBoundingClientRect()
      set({ left: `${box.left - at.left}px`, top: `${box.top - at.top}px` })
      host.attachShadow({ mode: "open" }).innerHTML = fragment
    }, { sec: s.i, fragment: fragment.replace(/asset:(\d+)/g, (m, n) => snap.assets[Number(n)] ?? m) })
    await freeze(page)
    return { png: await shoot(page, s.box), ...(await check(page, s, fragment)) }
  } finally {
    await page.evaluate((sec) => document.querySelector(`[data-gen="${sec}"]`)?.remove(), s.i)
    await unhide(page)
  }
}

// How the swapped-in fragment did: how far its content reaches past the top or bottom
// of the box (spill: anything past it does not fit, cut off or not) and the content
// checks. No callbacks into the page (a TreeWalker filter, say): with its scripts off,
// the browser runs none.
async function check(page, s, fragment) {
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
  return { spill: r.spill, fits: r.spill <= 1, checks: r.checks }
}
