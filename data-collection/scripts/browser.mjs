// How a page is loaded: once per site (site.mjs), and everything after happens in that
// one loaded page. The page runs its own scripts while it loads, with page time
// standing still from its first script on and moved only by us, in fixed steps, with
// the network let go quiet in between, and with Math.random and
// crypto.getRandomValues seeded (INIT): every page gets the same load. Once loaded,
// the page's scripts are switched off: from then on it is one fixed rendered state. A
// page left running reacts to being measured and screenshot (a full-page capture
// resizes the window and sets off its resize and visibility observers) and comes out
// differently each time; switched off, nothing in it changes but what we change.
// Google Chrome, not the Chromium Playwright ships: Chromium has no H.264 or AAC, so
// the MP4 videos most sites use would not play (README: setup).
import fs from "node:fs"
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

const T0 = Date.UTC(2026, 9, 1, 12)
// A video is shown at this point (or halfway, if shorter): its first frame is often
// black, the start of a fade.
const VIDEO_AT = 1

// Runs before the page's own scripts: seeded random numbers. What a page observes for
// visibility (IntersectionObserver) is left alone: scrolling through the page below
// sets off its lazy loading and reveals, and reporting every element as on screen
// would have every animation and WebGL scene on the page drawing at once, which with no
// GPU here takes the whole machine.
const INIT = `(() => {
  let s = 42
  const next = () => (s = (s * 1664525 + 1013904223) >>> 0)
  Math.random = () => next() / 4294967296
  crypto.getRandomValues = (a) => { const b = new Uint8Array(a.buffer, a.byteOffset, a.byteLength); for (let i = 0; i < b.length; i++) b[i] = next() & 255; return a }
})()`

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// What the page is still waiting for, run in it: fonts loading, images not in yet,
// videos seeking or loading their frame. Covers shadow roots, where a swapped-in
// section lives.
const pending = () => {
  const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
  const all = (sel) => roots.flatMap((r) => [...r.querySelectorAll(sel)])
  return [
    ...[...document.fonts].filter((f) => f.status === "loading").map((f) => `font ${f.family} ${f.weight}`),
    ...all("img").filter((i) => !i.complete).map((i) => `image ${(i.currentSrc || i.src).slice(0, 100)}`),
    ...all("video").filter((v) => v.seeking || (v.readyState < 2 && v.networkState === HTMLMediaElement.NETWORK_LOADING)).map((v) => `video ${v.currentSrc.slice(0, 100)}`),
  ]
}

// Waits on this side (the page's timers stand still; once its scripts are off, its
// events do not run either) until nothing is pending, at most 8s; what is still not
// in then is logged.
async function settle(page) {
  const end = Date.now() + 8000
  let left
  while ((left = await page.evaluate(pending)).length && Date.now() < end) await sleep(100)
  if (left.length) console.log(`still not in after 8s, going on without: ${left.slice(0, 5).join(" | ")}${left.length > 5 ? ` and ${left.length - 5} more` : ""}`)
}

// The network is quiet when no request has started or ended for 400ms; a request open
// for over 5s is a stream (live updates, analytics) and not waited on. At most 10s.
function network(page) {
  const open = new Map()
  let last = Date.now()
  page.on("request", (r) => { open.set(r, Date.now()); last = Date.now() })
  const done = (r) => { open.delete(r); last = Date.now() }
  page.on("requestfinished", done)
  page.on("requestfailed", done)
  return async () => {
    const end = Date.now() + 10000
    while (Date.now() < end) {
      const now = Date.now()
      if (now - last >= 400 && [...open.values()].every((t) => now - t > 5000)) return true
      await sleep(100)
    }
    return false
  }
}

export async function load(page, url) {
  const quiet = network(page)
  await page.clock.install({ time: T0 })
  await page.clock.pauseAt(T0)
  await page.addInitScript(INIT)
  const t0 = Date.now()
  const mark = (what) => console.log(`${what} (${((Date.now() - t0) / 1000).toFixed(1)}s)`)
  // page time moves only here: ms at a time, then the network is let go quiet, so what
  // the page asked for in that time has come in before time moves on, however slow
  let pageTime = 0
  const step = async (ms) => { await page.clock.runFor(ms); pageTime += ms; await quiet() }

  await page.goto(url, { waitUntil: "load", timeout: 60000 })
  mark("loaded")
  // content-visibility: auto skips painting what is off screen, which a full-page
  // screenshot then shows as blank. <noscript> stays hidden: the page was loaded with
  // its scripts on, but once they are switched off the browser would show what is in
  // it (as raw text, since it was read with scripts on: "<style>...</style>").
  await page.addStyleTag({ content: "* { content-visibility: visible !important } noscript { display: none !important }" })
  for (let k = 0; k < 4; k++) await step(1000)
  mark("4s of page time")

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

  // Scroll through the page so lazy images and scroll-triggered reveals load, then back
  // to the top: at each stop a few real frames for the page to see what came into view,
  // then 250ms of page time for it to act on it. Smooth scrolling is turned off first.
  await page.evaluate(() => { for (const el of [document.documentElement, document.body]) el.style.setProperty("scroll-behavior", "auto", "important") })
  const to = (y) => page.evaluate((y) => { window.scrollTo({ top: y, behavior: "instant" }); return document.documentElement.scrollHeight }, y)
  let stops = 0
  for (let y = 0, height = 1; y < height; y += CONTEXT.viewport.height * 0.7, stops++) {
    height = await to(y)
    await sleep(100)
    await step(250)
  }
  await to(0)
  await sleep(100)
  await step(250)
  mark(`scrolled through, ${stops} stops`)

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
    return gone
  })
  console.log(`hid ${hidden.length}:`, hidden.join(" | ") || "nothing")

  // Content that came in late (an image on a slow network) has its reveal run: more
  // page time, the same amount every time.
  for (let k = 0; k < 4; k++) await step(1000)
  await freeze(page)
  mark(`${(pageTime / 1000).toFixed(2)}s of page time in all, frozen`)

  // The page's scripts off: it is now one fixed state. A first full-page capture (thrown
  // away) has the browser load what only a capture of the whole page asks for (lazy
  // frames and images far from the window); after it, every capture is the same.
  const cdp = await page.context().newCDPSession(page)
  await cdp.send("Emulation.setScriptExecutionDisabled", { value: true })
  await page.screenshot({ fullPage: true, timeout: 120000 })
  await quiet()
  await freeze(page)
  mark("scripts off")
}

// Puts the page at rest: every image and frame loaded (a lazy one far from the window
// would never load, so all are made eager), fonts in, every animation at its end
// (finite ones) or its first frame (infinite ones), every video paused at VIDEO_AT
// with that frame shown. Covers shadow roots, where a swapped-in section lives.
export async function freeze(page) {
  await page.evaluate(() => {
    const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
    for (const root of roots) for (const el of root.querySelectorAll("img[loading=lazy], iframe[loading=lazy]")) el.loading = "eager"
  })
  await settle(page)
  await page.evaluate((VIDEO_AT) => {
    const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
    for (const root of roots) {
      for (const a of root.getAnimations()) {
        try { a.finish() } catch { a.pause(); a.currentTime = 0 }
      }
      for (const v of root.querySelectorAll("video")) {
        v.pause()
        const at = Math.min(VIDEO_AT, (v.duration || 0) / 2)
        if (Math.abs(v.currentTime - at) > 0.01) v.currentTime = at
      }
    }
  }, VIDEO_AT)
  await settle(page)
}
