// How a page is loaded, shared by record.mjs (live, recording a HAR) and render.mjs
// (replaying that HAR). The page runs with its own scripts both times; what would make
// two runs differ is pinned down: the clock starts at T0 and is stopped at T0 + PAUSE,
// Math.random and crypto.getRandomValues are seeded (INIT), and the viewport, locale, time zone
// and color scheme are fixed. Once the clock is stopped, page timers and animation
// frames no longer run, so the page holds still between screenshots.
// Google Chrome, not the Chromium Playwright ships: Chromium has no H.264 or AAC, so
// the MP4 videos most sites use would not play, live or replayed (README: setup).
import fs from "node:fs"
import path from "node:path"
import crypto from "node:crypto"
export const CHROME = process.env.CHROME ?? "/opt/chrome-stable/opt/google/chrome/chrome"
if (!fs.existsSync(CHROME)) throw new Error(`no Chrome at ${CHROME}; see README (setup) or set CHROME`)

export const CONTEXT = {
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  locale: "en-US",
  timezoneId: "UTC",
  colorScheme: "light",
  reducedMotion: "reduce",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
}

// Video and audio come in as range requests, which a HAR keeps as the pieces asked
// for and cannot answer again. They are taken out of the HAR: when recording, each is
// fetched whole, saved under <dir>/media/ and given to the page in full; when
// replaying, it is served from there (a page accepts a whole file for a range request).
export async function routeMedia(context, dir, recording) {
  const store = path.join(dir, "media")
  fs.mkdirSync(store, { recursive: true })
  const file = (url) => path.join(store, crypto.createHash("sha1").update(url).digest("hex"))
  await context.route("**/*", async (route) => {
    const req = route.request()
    if (req.resourceType() !== "media") return route.fallback()
    const f = file(req.url())
    if (recording) {
      const headers = { ...req.headers() }
      delete headers.range
      const res = await route.fetch({ headers }).catch(() => null)
      if (!res || !res.ok()) return route.abort()
      const body = await res.body()
      fs.writeFileSync(f, body)
      fs.writeFileSync(`${f}.type`, res.headers()["content-type"] ?? "application/octet-stream")
      return route.fulfill({ status: 200, body, contentType: res.headers()["content-type"] })
    }
    if (!fs.existsSync(f)) return route.abort()
    return route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: fs.readFileSync(`${f}.type`, "utf8") })
  })
}

const T0 = Date.UTC(2026, 9, 1, 12)
const PAUSE = 10 * 60 * 1000

// Runs before the page's own scripts. Besides the seeded random numbers, every element
// a page observes for visibility is reported as on screen: reveal-on-scroll effects and
// lazy loading mostly hang on IntersectionObserver, and a full-page screenshot sees
// the whole page at once, not the part a reader has scrolled to.
const INIT = `(() => {
  let s = 42
  const next = () => (s = (s * 1664525 + 1013904223) >>> 0)
  Math.random = () => next() / 4294967296
  crypto.getRandomValues = (a) => { const b = new Uint8Array(a.buffer, a.byteOffset, a.byteLength); for (let i = 0; i < b.length; i++) b[i] = next() & 255; return a }
  window.IntersectionObserver = class {
    constructor(callback, options = {}) {
      this.callback = callback
      this.root = options.root ?? null
      this.rootMargin = options.rootMargin ?? "0px"
      this.thresholds = [].concat(options.threshold ?? 0)
      this.targets = new Set()
    }
    observe(target) {
      this.targets.add(target)
      queueMicrotask(() => {
        if (!this.targets.has(target)) return
        const r = target.getBoundingClientRect()
        this.callback([{ target, isIntersecting: true, intersectionRatio: 1, boundingClientRect: r, intersectionRect: r, rootBounds: null, time: performance.now() }], this)
      })
    }
    unobserve(target) { this.targets.delete(target) }
    disconnect() { this.targets.clear() }
    takeRecords() { return [] }
  }
})()`

export async function load(page, url) {
  await page.clock.install({ time: T0 })
  await page.addInitScript(INIT)
  const t0 = Date.now()
  const mark = (what) => console.log(`${what} (${((Date.now() - t0) / 1000).toFixed(1)}s)`)
  await page.goto(url, { waitUntil: "load", timeout: 60000 })
  mark("loaded")
  // content-visibility: auto skips painting what is off screen, which a full-page
  // screenshot then shows as blank
  await page.addStyleTag({ content: "* { content-visibility: visible !important }" })
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
  mark("network idle")

  // Scroll through the page so lazy images and scroll-triggered reveals load, then back
  // to the top. Smooth scrolling is turned off first, or the page would still be gliding
  // back up when it is measured.
  await page.evaluate(async () => {
    for (const el of [document.documentElement, document.body]) el.style.setProperty("scroll-behavior", "auto", "important")
    const to = (y) => window.scrollTo({ top: y, behavior: "instant" })
    for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight * 0.7) {
      to(y)
      await new Promise((r) => setTimeout(r, 250))
    }
    for (let k = 0; k < 40 && (to(0), scrollY !== 0); k++) await new Promise((r) => setTimeout(r, 100))
  })
  mark("scrolled through")
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => console.log("networkidle timed out after scrolling, going on"))

  // Hide what is not the page's design: consent banners, chat widgets, modals, and
  // fixed elements away from the top (a fixed header stays). Hidden, not removed: the
  // page's framework still owns these nodes, and one it later fails to find in the
  // document (React unmounting it, say) crashes the whole page.
  const hidden = await page.evaluate(() => {
    const gone = []
    const drop = (el, why) => {
      if (el.closest("[data-hidden-by-load]")) return
      gone.push(`${why}: <${el.tagName.toLowerCase()} class="${(el.className?.baseVal ?? el.className ?? "").toString().slice(0, 60)}">`)
      el.setAttribute("data-hidden-by-load", "")
      el.style.setProperty("display", "none", "important")
    }
    for (const el of document.querySelectorAll("[role=dialog], [aria-modal=true], dialog[open]")) drop(el, "dialog")
    const junk = /cookie|consent|gdpr|onetrust|intercom|drift-|crisp|hubspot-messages|zendesk|chat-widget/i
    for (const el of document.querySelectorAll("body *")) {
      const s = getComputedStyle(el)
      const id = `${el.id} ${el.className?.baseVal ?? el.className ?? ""}`
      if ((s.position === "fixed" || s.position === "sticky") && junk.test(id)) drop(el, "widget")
      else if (s.position === "fixed" && el.getBoundingClientRect().top > 50) drop(el, "fixed")
    }
    for (const img of document.querySelectorAll("img[loading=lazy]")) img.loading = "eager"
    return gone
  })
  console.log(`hid ${hidden.length}:`, hidden.join(" | ") || "nothing")
  mark("network idle again")

  await freeze(page)
  await page.clock.pauseAt(T0 + PAUSE)
  mark("fonts and images in, clock paused")
  // Content that arrives late (an image or video loading on a busy machine) can start
  // its reveal after the clock stopped, and would stay at its first frame. Page time is
  // stepped on, with a pause between steps for the network, until the page's height
  // and the number of visible elements hold still.
  let last = ""
  let k = 0
  for (; k < 10; k++) {
    await page.clock.runFor(2000)
    await new Promise((r) => setTimeout(r, 500))
    const now = await page.evaluate(() => `${document.documentElement.scrollHeight}:${[...document.querySelectorAll("body *")].filter((e) => e.checkVisibility({ opacityProperty: true, visibilityProperty: true })).length}`)
    if (now === last) break
    last = now
  }
  mark(`settled after ${k + 1} steps of 2s page time`)
  await freeze(page)
  mark("frozen")
}

// Waits for fonts and images (with a timer on this side: the page's own timers stop
// with its clock), then puts every animation at its end (finite ones) or its first
// frame (infinite ones) and pauses videos. Covers shadow roots, where a swapped-in
// section lives.
export async function freeze(page) {
  const wait = page.evaluate(async () => {
    await document.fonts.ready
    const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
    const imgs = roots.flatMap((r) => [...r.querySelectorAll("img")]).filter((i) => !i.complete)
    await Promise.all(imgs.map((i) => new Promise((r) => { i.addEventListener("load", r, { once: true }); i.addEventListener("error", r, { once: true }) })))
  })
  await Promise.race([wait, new Promise((r) => setTimeout(r, 8000))])
  await page.evaluate(() => {
    const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
    for (const root of roots) {
      for (const a of root.getAnimations()) {
        try { a.finish() } catch { a.pause(); a.currentTime = 0 }
      }
      for (const v of root.querySelectorAll("video")) v.pause()
    }
  })
}
