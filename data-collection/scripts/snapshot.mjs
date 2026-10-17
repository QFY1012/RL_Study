// Freezes one live page so it can be re-rendered offline, and splits it into sections.
//   node scripts/snapshot.mjs <url> <out-dir>
// Writes to <out-dir>:
//   page.har.zip    every response the page loaded (replayed by render.mjs, no network)
//   page.html       the DOM after JS ran, scripts removed, each section marked data-sec="<i>"
//   live.png        full-page screenshot of the live page after the same cleanup
//   sections.json   the page URL, design tokens, per section its box and content,
//                   and the inline SVGs as standalone files (assets)
import fs from "node:fs"
import path from "node:path"
import { chromium } from "playwright-core"
import { CONTEXT, settle } from "./browser.mjs"

const [url, out] = process.argv.slice(2)
if (!url || !out) throw new Error("usage: snapshot.mjs <url> <out-dir>")
fs.mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", proxy: { server: process.env.HTTPS_PROXY } })
const context = await browser.newContext({ ...CONTEXT, recordHar: { path: path.join(out, "page.har.zip"), mode: "full", content: "attach" } })
const page = await context.newPage()
await page.goto(url, { waitUntil: "load", timeout: 60000 })
await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => console.log("networkidle timed out, going on"))

// Some pages scroll inside a full-screen container instead of the window; such a
// container is opened up to its full height, so the page is as tall as its content.
const opened = await page.evaluate(() => {
  let n = 0
  for (const el of document.querySelectorAll("body *")) {
    const s = getComputedStyle(el)
    if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 100 && el.clientWidth > innerWidth * 0.5 && el.clientHeight >= innerHeight * 0.5) {
      el.style.setProperty("overflow", "visible", "important")
      el.style.setProperty("height", "auto", "important")
      el.style.setProperty("max-height", "none", "important")
      n++
    }
  }
  if (n) for (const el of [document.documentElement, document.body]) {
    el.style.setProperty("overflow", "visible", "important")
    el.style.setProperty("height", "auto", "important")
  }
  return n
})
if (opened) console.log(`opened ${opened} scroll containers`)

// Scroll through the page so lazy images and scroll-triggered reveals load, then back to the top.
await page.evaluate(async () => {
  const step = innerHeight * 0.7
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
    scrollTo(0, y)
    await new Promise((r) => setTimeout(r, 250))
  }
  scrollTo(0, 0)
})
await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => console.log("networkidle timed out after scrolling, going on"))

// Remove what is not the page's design: consent banners, chat widgets, modals, and
// fixed elements away from the top (a fixed header stays).
const removed = await page.evaluate(() => {
  const gone = []
  const drop = (el, why) => { gone.push(`${why}: <${el.tagName.toLowerCase()} class="${(el.className?.baseVal ?? el.className ?? "").toString().slice(0, 60)}">`); el.remove() }
  for (const el of document.querySelectorAll("[role=dialog], [aria-modal=true], dialog[open]")) drop(el, "dialog")
  const junk = /cookie|consent|gdpr|onetrust|intercom|drift-|crisp|hubspot-messages|zendesk|chat-widget/i
  for (const el of document.querySelectorAll("body *")) {
    if (!el.isConnected) continue
    const s = getComputedStyle(el)
    const id = `${el.id} ${el.className?.baseVal ?? el.className ?? ""}`
    if ((s.position === "fixed" || s.position === "sticky") && junk.test(id)) drop(el, "widget")
    else if (s.position === "fixed" && el.getBoundingClientRect().top > 50) drop(el, "fixed")
  }
  for (const img of document.querySelectorAll("img[loading=lazy]")) img.loading = "eager"
  for (const v of document.querySelectorAll("video")) { v.removeAttribute("autoplay"); v.pause() }
  return gone
})
console.log(`removed ${removed.length}:`, removed.join(" | ") || "nothing")
await settle(page)

// Videos and canvases show what scripts and media streams put there, which the
// replay does not have; each is swapped for a screenshot of itself, at its size.
let swapped = 0
for (const handle of await page.$$("video, canvas")) {
  const box = await handle.boundingBox()
  if (!box || box.width < 16 || box.height < 16) continue
  const png = await handle.screenshot({ timeout: 15000 }).catch(() => null)
  if (!png) continue
  await handle.evaluate((el, src) => {
    const img = document.createElement("img")
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el)
    img.src = src
    img.className = el.className?.baseVal ?? el.className ?? ""
    img.style.cssText = el.style.cssText
    img.style.width = `${r.width}px`
    img.style.height = `${r.height}px`
    img.style.objectFit = "fill"
    if (cs.display === "inline") img.style.display = "inline-block"
    el.replaceWith(img)
  }, `data:image/png;base64,${png.toString("base64")}`)
  swapped++
}
console.log(`swapped ${swapped} videos and canvases for screenshots`)

// Scripted animations (element.animate, as Framer and Motion use) hold their end
// state only while the animation exists; it is written into inline styles so the
// frozen DOM keeps it. settle() has already put every animation at its end.
const committed = await page.evaluate(() => {
  let n = 0
  const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
  for (const root of roots) {
    for (const a of root.getAnimations()) {
      try { a.commitStyles(); a.cancel(); n++ } catch {}
    }
  }
  return n
})
console.log(`committed ${committed} animations`)
await settle(page)

// Sections: from <body>, go down through wrappers (one child holding most of the
// height) to the element whose children are stacked blocks; children taller than
// MAX are split the same way. Each section gets data-sec="<i>".
const MIN = 120, MAX = 1800
const { secs: sections, assets } = await page.evaluate(({ MIN, MAX }) => {
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect()
    return s.display !== "none" && s.visibility !== "hidden" && r.height > 0 && r.width > 0
  }
  const kids = (el) => [...el.children].filter((c) => !["SCRIPT", "STYLE", "NOSCRIPT", "LINK", "TEMPLATE"].includes(c.tagName) && visible(c))
  const unwrap = (el) => {
    for (;;) {
      const k = kids(el)
      const h = el.getBoundingClientRect().height
      const big = k.filter((c) => c.getBoundingClientRect().height >= 0.8 * h)
      if (k.length >= 1 && big.length === 1 && k.length <= 3) el = big[0]
      else return el
    }
  }
  const split = (el) => {
    const out = []
    for (const c of kids(unwrap(el))) {
      const r = c.getBoundingClientRect()
      if (r.width < innerWidth * 0.5) continue
      if (r.height > MAX && kids(unwrap(c)).length >= 2) out.push(...split(c))
      else if (r.height >= MIN || c.tagName === "HEADER" || c.tagName === "NAV" || c.tagName === "FOOTER") out.push(c)
    }
    return out
  }
  const list = split(document.body).sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)

  const abs = (r) => ({ x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) })
  const bg = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const c = getComputedStyle(e).backgroundColor
      if (c && c !== "rgba(0, 0, 0, 0)" && c !== "transparent") return c
    }
    return "rgb(255, 255, 255)"
  }
  // Inline SVGs become standalone SVG files (assets), referenced as asset:<n>: the
  // styles that come from the page's CSS are written onto each shape, the color
  // that currentColor stands for onto the root, and symbols pulled in with <use>
  // are copied into <defs>. render.mjs puts them back as data: URLs.
  const assets = []
  const PAINT = ["fill", "stroke", "stroke-width", "stroke-opacity", "fill-opacity", "opacity", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "stop-color", "stop-opacity"]
  const svgAsset = (el) => {
    const clone = el.cloneNode(true)
    const r = el.getBoundingClientRect()
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg")
    clone.setAttribute("width", String(Math.round(r.width)))
    clone.setAttribute("height", String(Math.round(r.height)))
    const src = [el, ...el.querySelectorAll("*")], dst = [clone, ...clone.querySelectorAll("*")]
    src.forEach((n, k) => {
      const cs = getComputedStyle(n)
      dst[k].style.cssText = PAINT.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";") + `;color:${cs.color}`
    })
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs")
    for (const u of clone.querySelectorAll("use")) {
      const ref = (u.getAttribute("href") || u.getAttribute("xlink:href") || "").trim()
      const id = ref.slice(1)
      if (ref.startsWith("#") && ![...clone.querySelectorAll("[id]")].some((e) => e.id === id)) {
        const target = document.getElementById(id)
        if (target) defs.append(target.cloneNode(true))
      }
    }
    if (defs.children.length) clone.prepend(defs)
    assets.push("data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(new XMLSerializer().serializeToString(clone)))))
    return `asset:${assets.length - 1}`
  }

  // Content of a section, in reading order. Text comes from leaf blocks: elements
  // that are not inline and hold no non-inline element with text of their own.
  const content = (sec) => {
    const items = []
    const isBlock = (el) => getComputedStyle(el).display !== "inline"
    const walk = (el) => {
      if (!visible(el)) return
      const tag = el.tagName
      if (tag === "IMG") {
        const r = el.getBoundingClientRect()
        if (r.width >= 24 && r.height >= 24) items.push({ kind: "image", src: el.currentSrc || el.src, alt: el.alt || "", aspect: +(el.naturalWidth / el.naturalHeight || r.width / r.height).toFixed(3) })
        return
      }
      if (tag === "VIDEO") {
        if (el.poster) items.push({ kind: "image", src: el.poster, alt: "video", aspect: +(el.getBoundingClientRect().width / el.getBoundingClientRect().height).toFixed(3) })
        return
      }
      if (tag === "svg") {
        const r = el.getBoundingClientRect()
        if (r.width >= 8 && r.height >= 8) items.push({ kind: r.width <= 48 && r.height <= 48 ? "icon" : "illustration", src: svgAsset(el), alt: el.getAttribute("aria-label") || "", aspect: +(r.width / r.height).toFixed(3) })
        return
      }
      const bgImg = getComputedStyle(el).backgroundImage
      const m = bgImg && bgImg.match(/url\("?([^")]+)"?\)/)
      const r = el.getBoundingClientRect()
      if (m && r.width >= 100 && r.height >= 100) items.push({ kind: "image", src: m[1], alt: "background", aspect: +(r.width / r.height).toFixed(3) })
      const blockKids = [...el.children].filter((c) => visible(c) && isBlock(c) && c.innerText?.trim())
      const text = el.innerText?.trim()
      const leaf = text && blockKids.length === 0
      if (leaf) {
        const kind = /^H[1-6]$/.test(tag) || el.closest("h1,h2,h3,h4,h5,h6") ? "heading"
          : tag === "BUTTON" || el.closest("button,[role=button]") ? "button"
          : tag === "A" || el.closest("a") ? "link"
          : tag === "LI" ? "list-item" : "text"
        const href = el.closest("a")?.getAttribute("href")
        // text the original cuts off (ellipsis, line clamp) is marked, so the check and the prompt know
        const cs = getComputedStyle(el)
        const clamped = (cs.overflow !== "visible" || cs.webkitLineClamp !== "none") && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
        items.push({ kind, text: text.replace(/\s+\n/g, "\n").replace(/[ \t]+/g, " "), ...(href ? { href } : {}), ...(clamped ? { clamped: true } : {}) })
        // images and icons inside a text leaf (an icon in a button, say) still count
        for (const sub of el.querySelectorAll("img, svg")) if (!sub.closest("svg") || sub.tagName === "svg") walk(sub)
        return
      }
      for (const c of el.children) walk(c)
    }
    walk(sec)
    return items
  }

  const secs = list.map((el, i) => {
    el.setAttribute("data-sec", String(i))
    const items = content(el)
    return { i, tag: el.tagName.toLowerCase(), box: abs(el.getBoundingClientRect()), background: bg(el), items }
  })
  return { secs, assets }
}, { MIN, MAX })

// Page-level design tokens: the fonts actually used for headings and body text,
// the most used text and background colors, and the width the content keeps to.
const tokens = await page.evaluate(() => {
  const font = (sel) => { const el = document.querySelector(sel); return el ? getComputedStyle(el).fontFamily : null }
  const count = (m, k, w = 1) => m.set(k, (m.get(k) ?? 0) + w)
  const text = new Map(), back = new Map()
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) continue
    const s = getComputedStyle(el)
    if ([...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) {
      count(text, s.color)
    }
    if (s.backgroundColor !== "rgba(0, 0, 0, 0)") count(back, s.backgroundColor, r.width * r.height)
  }
  const top = (m, n) => [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([k]) => k)
  const blocks = [...document.querySelectorAll("[data-sec] *")].map((el) => el.getBoundingClientRect()).filter((r) => r.width > 200 && r.width < innerWidth * 0.95)
  const contentWidth = blocks.length ? Math.max(...blocks.map((r) => r.width)) : null
  return {
    fonts: { heading: font("h1") ?? font("h2"), subheading: font("h2") ?? font("h3"), body: font("p") ?? getComputedStyle(document.body).fontFamily },
    textColors: top(text, 6),
    backgroundColors: top(back, 6),
    pageBackground: getComputedStyle(document.body).backgroundColor,
    contentWidth: contentWidth && Math.round(contentWidth),
  }
})

// The frozen document: same DOM, no scripts, so a replay renders what we saw.
// CSS-in-JS libraries add rules with insertRule, which leaves the <style> element's
// text empty, and constructed (adopted) style sheets have no element at all; both
// are written out as <style> text. Shadow roots are kept as declarative shadow DOM.
const finalUrl = page.url()
const html = await page.evaluate(() => {
  for (const el of document.querySelectorAll("script, noscript, link[rel=preload][as=script], link[rel=modulepreload]")) el.remove()
  const roots = []
  const collect = (root) => {
    for (const el of root.querySelectorAll("*")) if (el.shadowRoot) { roots.push(el.shadowRoot); collect(el.shadowRoot) }
  }
  collect(document)
  const cssOf = (sheet) => { try { return [...sheet.cssRules].map((r) => r.cssText).join("\n") } catch { return null } }
  for (const root of [document, ...roots]) {
    for (const el of root.querySelectorAll("style")) {
      const css = el.sheet && cssOf(el.sheet)
      if (css != null) el.textContent = css
    }
    for (const sheet of root.adoptedStyleSheets ?? []) {
      const style = document.createElement("style")
      style.textContent = cssOf(sheet) ?? ""
      if (root === document) document.head.append(style)
      else root.prepend(style)
    }
  }
  // getHTML is the inside of <html>; its attributes (a theme class, say) are added back
  const root = document.documentElement
  const attrs = [...root.attributes].map((a) => ` ${a.name}="${a.value.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}"`).join("")
  return `<!doctype html>\n<html${attrs}>${root.getHTML({ serializableShadowRoots: true, shadowRoots: roots })}</html>`
})
// right after the DOM is taken, so a carousel or ticker has had no time to move on
await page.screenshot({ path: path.join(out, "live.png"), fullPage: true, timeout: 120000 })
fs.writeFileSync(path.join(out, "page.html"), html)
fs.writeFileSync(path.join(out, "sections.json"), JSON.stringify({ url: finalUrl, title: await page.title(), tokens, sections, assets }, null, 1))
await context.close()
await browser.close()

console.log(`${finalUrl}: ${sections.length} sections`)
for (const s of sections) console.log(`  #${s.i} <${s.tag}> y=${s.box.y} h=${s.box.h} items=${s.items.length} ${JSON.stringify(s.items.find((t) => t.text)?.text?.slice(0, 50) ?? "")}`)
