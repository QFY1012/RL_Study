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

// Page time a WebGL context that draws on every frame is drawn on at most once in,
// while the page loads (INIT).
const DRAWN_EVERY = 1000

// Runs before the page's own scripts: seeded random numbers, visibility and WebGL as
// follows.
// Visibility: a page shows much of itself only while it is in view, by observing the
// window (IntersectionObserver): reveals, but also parts dimmed (arc.net) or not even
// there (raycast mounts a section's demo only while it is in view) the rest of the
// time. A reader sees each part in view; a full-page capture has the whole page at one
// scroll position. So once window.__inView() is called (load, at the end), every
// observer of the window reports everything it watches as in view, and goes on doing
// so for whatever it is given to watch; observers of anything else (a carousel's
// track) are left alone. Before that, observers report as usual: scrolling through the
// page sets off what it loads as it is scrolled to.
// WebGL: with no GPU here, every frame of a WebGL scene is drawn on the CPU, and a big
// one takes seconds a frame (raycast: 2s), while page time runs at 60 frames a second.
// The page still runs every frame (animations need their frames to get where they are
// going), but a context drawing on every animation frame, a render loop, has its draw
// calls carried out on one frame per DRAWN_EVERY of page time and skipped on the rest;
// a context that draws only now and then (a scene redrawn when something in it
// changes) always draws. window.__drawAll lifts the limit (load: the last frames, so
// every loop shows where it has got to). Drawing buffers are kept
// (preserveDrawingBuffer), so what a canvas shows can be read after the frame it was
// drawn in (load: canvases are pinned before scripts go off).
const INIT = `(() => {
  let s = 42
  const next = () => (s = (s * 1664525 + 1013904223) >>> 0)
  Math.random = () => next() / 4294967296
  crypto.getRandomValues = (a) => { const b = new Uint8Array(a.buffer, a.byteOffset, a.byteLength); for (let i = 0; i < b.length; i++) b[i] = next() & 255; return a }

  const IO = window.IntersectionObserver
  if (IO) {
    const observers = new Set()
    let inView = false
    const entry = (target) => {
      const r = target.getBoundingClientRect()
      return { target, isIntersecting: true, isVisible: true, intersectionRatio: 1, boundingClientRect: r, intersectionRect: r, rootBounds: new DOMRect(0, 0, innerWidth, innerHeight), time: performance.now() }
    }
    const CB = Symbol(), WINDOW = Symbol(), TARGETS = Symbol()
    const tell = (o, targets) => { try { o[CB](targets.map(entry), o) } catch (e) { console.error(e) } }
    window.IntersectionObserver = class IntersectionObserver extends IO {
      constructor(cb, options) {
        super((entries, o) => { if (!(inView && o[WINDOW])) cb(entries, o) }, options)
        this[CB] = cb
        this[WINDOW] = !options?.root || options.root === document
        this[TARGETS] = new Set()
        observers.add(this)
      }
      observe(t) { this[TARGETS].add(t); super.observe(t); if (inView && this[WINDOW]) queueMicrotask(() => this[TARGETS].has(t) && tell(this, [t])) }
      unobserve(t) { this[TARGETS].delete(t); super.unobserve(t) }
      disconnect() { this[TARGETS].clear(); super.disconnect() }
    }
    window.__inView = () => { inView = true; for (const o of observers) if (o[WINDOW] && o[TARGETS].size) tell(o, [...o[TARGETS]]) }
  }

  const getContext = HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.getContext = function (type, attrs) {
    return getContext.call(this, type, /webgl/.test(type) ? { ...attrs, preserveDrawingBuffer: true } : attrs)
  }
  // the animation frame being run (callbacks of one frame share its time) and the one before
  let frame = null, before = null, inFrame = false
  const raf = window.requestAnimationFrame
  window.requestAnimationFrame = (cb) => raf.call(window, (t) => {
    if (t !== frame) { before = frame; frame = t }
    inFrame = true
    try { return cb(t) } finally { inFrame = false }
  })
  // per context: the last frame it drew or tried to, whether that frame is drawn, the last drawn
  const contexts = new WeakMap()
  const drawn = (gl) => {
    if (window.__drawAll || !inFrame) return true
    let c = contexts.get(gl)
    if (!c) contexts.set(gl, (c = {}))
    if (c.frame !== frame) {
      const loop = c.frame === before
      c.draw = !loop || !(frame - c.last < ${DRAWN_EVERY})
      c.frame = frame
      if (c.draw) c.last = frame
    }
    return c.draw
  }
  const DRAW = ["drawArrays", "drawElements", "drawArraysInstanced", "drawElementsInstanced", "drawRangeElements", "clear", "clearBufferfv", "clearBufferiv", "clearBufferuiv", "clearBufferfi", "blitFramebuffer"]
  for (const P of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) if (P) for (const m of DRAW) {
    const f = P.prototype[m]
    if (f) P.prototype[m] = function (...a) { if (drawn(this)) return f.apply(this, a) }
  }
})()`

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// What the page is still waiting for, run in it: fonts loading, images not in yet,
// videos not yet holding the frame they are at (seeking, or no data for it yet; one
// that failed to load, or is pinned, is not waited for). Covers shadow roots, where a
// swapped-in section lives. Laid out first: a face starts loading when text set in it
// is laid out, so one that new content (a swapped-in section) needs is not yet
// loading, nor waited for, until then.
const pending = () => {
  document.documentElement.getBoundingClientRect()
  const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
  const all = (sel) => roots.flatMap((r) => [...r.querySelectorAll(sel)])
  return [
    ...[...document.fonts].filter((f) => f.status === "loading").map((f) => `font ${f.family} ${f.weight}`),
    ...all("img").filter((i) => !i.complete).map((i) => `image ${(i.currentSrc || i.src).slice(0, 100)}`),
    ...all("video:not([data-pinned])").filter((v) => v.currentSrc && !v.error && v.checkVisibility() && (v.seeking || v.readyState < HTMLMediaElement.HAVE_CURRENT_DATA)).map((v) => `video ${v.currentSrc.slice(0, 100)}`),
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
  // installed clocks run in real time until paused, and pausing can only go forward:
  // started an hour early, page time stands at T0 however long the pause takes to
  // come (on a busy machine, past 100ms, a clock started at T0 is already past it)
  await page.clock.install({ time: T0 - 3600_000 })
  await page.clock.pauseAt(T0)
  await page.addInitScript(INIT)
  const t0 = Date.now()
  const mark = (what) => console.log(`${what} (${((Date.now() - t0) / 1000).toFixed(1)}s)`)
  // page time moves only here: ms at a time, then the network is let go quiet, so what
  // the page asked for in that time has come in before time moves on, however slow
  let pageTime = 0
  const step = async (ms) => { await page.clock.runFor(ms); pageTime += ms; await quiet() }

  // a network error on the way to the page (a connection timing out) is tried again,
  // up to three times in all
  for (let k = 1; ; k++) {
    try { await page.goto(url, { waitUntil: "load", timeout: 60000 }); break } catch (e) {
      if (k === 3 || !/net::ERR_/.test(e.message)) throw e
      console.log(`${e.message.split("\n")[0]}, trying again in 5s`)
      await sleep(5000)
    }
  }
  mark("loaded")
  // content-visibility: auto skips painting what is off screen, which a full-page
  // screenshot then shows as blank. What HTML shows only without scripting stays as it
  // is with scripts on, for once they are switched off: <noscript> hidden (else shown
  // as raw text, since it was read with scripts on: "<style>...</style>"), and a video
  // without the controls attribute without controls (else they come up whenever it is
  // moved to a frame).
  await page.addStyleTag({ content: "* { content-visibility: visible !important } noscript { display: none !important } video:not([controls])::-webkit-media-controls { display: none !important }" })
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
  // then a second of page time for it to act on it, and how everything looks there is
  // recorded (look). Smooth scrolling is turned off first.
  await page.evaluate(() => { for (const el of [document.documentElement, document.body]) el.style.setProperty("scroll-behavior", "auto", "important") })
  const to = (y) => page.evaluate((y) => { window.scrollTo({ top: y, behavior: "instant" }); return document.documentElement.scrollHeight }, y)
  let stops = 0
  for (let y = 0, height = 1; y < height; y += CONTEXT.viewport.height * 0.7, stops++) {
    height = await to(y)
    await sleep(100)
    await step(1000)
    await page.evaluate(look, LOOK)
  }
  await to(0)
  await sleep(100)
  await step(1000)
  mark(`scrolled through, ${stops} stops`)

  // Everything in view at once (INIT: visibility), then more page time, the same
  // amount every time: for what that brings in, and for content that came in late (an
  // image on a slow network) to have its reveal run.
  for (const f of page.frames()) await f.evaluate(() => window.__inView?.()).catch(() => {})
  for (let k = 0; k < 4; k++) await step(1000)

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

  // A few frames with every WebGL context drawing, so each render loop shows where it
  // has got to (INIT); then how everything looks at the top, and each element put back
  // to how it looks in view (look).
  for (const f of page.frames()) await f.evaluate(() => { window.__drawAll = true }).catch(() => {})
  await step(50)
  await page.evaluate(look, LOOK)
  const restyled = await page.evaluate(lookBack, LOOK)
  if (restyled) console.log(`${restyled} elements put back to how they look in view`)
  await freeze(page)
  mark(`${(pageTime / 1000).toFixed(2)}s of page time in all, frozen`)

  // The page's scripts off: it is now one fixed state. That must not change how it
  // renders, but HTML renders some things differently without scripting: <noscript>
  // and video controls (both kept as with scripts, above), canvases (pinned first,
  // with videos) and @media (scripting); so everything's layout and paint is compared
  // before and after (unchanged). A first full-page capture (thrown away) has the
  // browser load what only a capture of the whole page asks for (lazy frames and images
  // far from the window); after it, every capture is the same.
  const pinned = await pin(page)
  console.log(`pinned ${pinned.read} canvases and videos as read${pinned.shot.length ? `, ${pinned.shot.length} as shot alone: ${pinned.shot.slice(0, 5).join(" | ")}` : ""}${pinned.unshown ? `; ${pinned.unshown} videos did not show their frame in 5s` : ""}`)
  await freeze(page)
  const before = await page.evaluate(rendering)
  const cdp = await page.context().newCDPSession(page)
  await cdp.send("Emulation.setScriptExecutionDisabled", { value: true })
  const changed = await page.evaluate(unchanged, before)
  if (changed.n) console.log(`${changed.n} elements render differently with scripts off (marked data-changed-without-scripts): ${changed.some.join(" | ")}`)
  await page.screenshot({ fullPage: true, timeout: 120000 })
  await quiet()
  await freeze(page)
  mark("scripts off")
}

// How an element looks while a reader has it in view, recorded at every scroll stop
// (look) and put back once the page is at the top again (lookBack). Besides observing
// what is in view (INIT: visibility), a page can change how an element looks with the
// scroll position itself (scroll listeners, scroll-driven animations: a heading that
// fades as it nears the top, a parallax image), while a full-page capture has one
// scroll position, the top, for all of it: a section further down would show as it
// does from the top of the page. Kept is how each element looks at the stop that has
// it most in view (its middle nearest the middle of the window, or the window inside
// it; on a tie the later stop, so for what is at the top the last look there counts),
// in the properties that change how it looks without moving anything; an inherited one
// only where the element sets it itself. Animations under
// way are finished first, as they would be by the time a reader looks; an element with
// an endless one is left as freeze leaves it.
const LOOK = ["opacity", "visibility", "transform", "translate", "scale", "rotate", "filter", "backdrop-filter", "clip-path", "color", "background-color", "stroke-dashoffset"]
function look(LOOK) {
  const INHERITED = ["visibility", "color"]
  const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
  const endless = new Set()
  for (const root of roots) for (const a of root.getAnimations()) {
    if (!(a.timeline instanceof DocumentTimeline) || a.playState !== "running") continue
    try { a.finish() } catch { endless.add(a.effect?.target) }
  }
  const seen = (window.__looks ??= new Map())
  for (const root of roots) for (const el of root.querySelectorAll("*")) {
    if (endless.has(el)) continue
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) continue
    const off = Math.max(0, Math.abs((r.top + r.bottom - innerHeight) / 2) - Math.max(0, (r.height - innerHeight) / 2))
    if (seen.get(el)?.off < off) continue
    const cs = getComputedStyle(el), up = el.parentElement ?? el.getRootNode().host
    const ups = up && getComputedStyle(up)
    seen.set(el, { off, look: LOOK.map((p) => (INHERITED.includes(p) && ups?.getPropertyValue(p) === cs.getPropertyValue(p) ? null : cs.getPropertyValue(p))) })
  }
}
// Put back by a style sheet of ours (one per document or shadow root), each element
// it changes marked data-look="<n>", not by writing the page's own styles (swap.mjs,
// hide: why), and below the hiding of a swap's section in the cascade.
function lookBack(LOOK) {
  const rules = new Map()
  let n = 0
  for (const [el, { look }] of window.__looks ?? []) {
    if (!el.isConnected) continue
    const cs = getComputedStyle(el)
    const set = LOOK.flatMap((p, k) => (look[k] !== null && cs.getPropertyValue(p) !== look[k] ? [`${p}: ${look[k]} !important`] : []))
    if (!set.length) continue
    el.setAttribute("data-look", String(n))
    const root = el.getRootNode()
    rules.set(root, [...(rules.get(root) ?? []), `[data-look="${n}"] { ${set.join("; ")}; transition-property: none !important }`])
    n++
  }
  for (const [root, list] of rules) (root === document ? document.head : root).append(Object.assign(document.createElement("style"), { textContent: list.join("\n") }))
  delete window.__looks
  return n
}

// Canvases and videos pinned as images of what they show (CSS content), for once
// scripts are off: with scripting disabled the browser renders a canvas as its
// fallback content (one laid out again goes blank, one sized by its width and height
// attributes alone collapses to nothing), and a video is a player that cannot be
// counted on to hold still (moved to its frame, it does not always show it in time,
// and shows it later). Pinned, neither changes again (freeze leaves them be). Each is
// read where it can be: a canvas's own pixels, a video's frame drawn on a canvas, once
// that frame is on screen (requestVideoFrameCallback; at most 5s). What cannot be read
// so (a canvas with an image from another origin drawn in it, a video from another
// origin, a canvas handed to a worker, a video with no frame) is shot alone (isolated).
async function pin(page) {
  const unshown = await page.evaluate(() => {
    const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
    window.__videos = roots.flatMap((r) => [...r.querySelectorAll("video")]).filter((v) => v.currentSrc && !v.error && v.checkVisibility())
    window.__shown = new Set()
    for (const v of window.__videos) {
      v.requestVideoFrameCallback?.(() => window.__shown.add(v))
      v.currentTime = v.currentTime
    }
    return window.__videos.length
  })
  let left = unshown
  for (const end = Date.now() + 5000; left && Date.now() < end; await sleep(100)) left = await page.evaluate(() => window.__videos.filter((v) => !window.__shown.has(v)).length)
  const { read, unread } = await page.evaluate(() => {
    const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
    window.__pins = []
    let read = 0
    for (const el of roots.flatMap((r) => [...r.querySelectorAll("canvas, video")])) {
      if (!el.checkVisibility()) continue
      try {
        let url
        if (el.tagName === "CANVAS") url = el.toDataURL()
        else {
          if (el.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !el.videoWidth) throw new Error("no frame")
          const c = document.createElement("canvas")
          c.width = el.videoWidth
          c.height = el.videoHeight
          c.getContext("2d").drawImage(el, 0, 0)
          url = c.toDataURL()
        }
        el.style.setProperty("content", `url("${url}")`, "important")
        el.setAttribute("data-pinned", "")
        read++
      } catch { window.__pins.push(el) }
    }
    return { read, unread: window.__pins.map((el) => `<${el.tagName.toLowerCase()} class="${(el.className?.baseVal ?? el.className ?? "").toString().slice(0, 40)}">`) }
  })
  const shot = []
  for (const [k, what] of unread.entries()) if (await isolated(page, k)) shot.push(what)
  return { read, shot, unshown: left }
}

// Pinned element k (window.__pins) as shot from the page alone: everything else made
// invisible and the page's background transparent; and what it and its ancestors do to
// its pixels on the way to the screen (opacity, filters, blending, masks, transforms),
// which the pinned image goes through again, undone for the shot. By a style sheet of
// ours and attributes, taken out after (swap.mjs, hide: why). One reaching past the page
// is left as it is (false).
async function isolated(page, k) {
  const clip = await page.evaluate((k) => {
    const el = window.__pins[k]
    el.setAttribute("data-isolated", "")
    for (let a = el; a; a = a.parentElement ?? a.getRootNode().host) a.setAttribute("data-isolated-in", "")
    document.head.append(Object.assign(document.createElement("style"), {
      id: "gen-isolating",
      textContent: ":root *:not([data-isolated]) { visibility: hidden !important } :root * { transition-property: none !important } :root, :root body { background: transparent !important } :root [data-isolated] { visibility: visible !important } :root [data-isolated-in] { opacity: 1 !important; filter: none !important; mix-blend-mode: normal !important; mask: none !important; transform: none !important; translate: none !important; scale: none !important; rotate: none !important }",
    }))
    const r = el.getBoundingClientRect()
    const x = r.left + scrollX, y = r.top + scrollY
    const inside = x >= 0 && y >= 0 && x + r.width <= document.documentElement.scrollWidth && y + r.height <= document.documentElement.scrollHeight && r.width >= 1 && r.height >= 1
    return inside ? { x, y, width: r.width, height: r.height } : null
  }, k)
  const png = clip && (await page.screenshot({ clip, fullPage: true, omitBackground: true, timeout: 60000 }))
  await page.evaluate(({ k, url }) => {
    document.getElementById("gen-isolating").remove()
    for (const e of document.querySelectorAll("[data-isolated], [data-isolated-in]")) { e.removeAttribute("data-isolated"); e.removeAttribute("data-isolated-in") }
    for (const r of [...document.querySelectorAll("*")].filter((e) => e.shadowRoot)) for (const e of r.shadowRoot.querySelectorAll("[data-isolated], [data-isolated-in]")) { e.removeAttribute("data-isolated"); e.removeAttribute("data-isolated-in") }
    if (!url) return
    const el = window.__pins[k]
    el.style.setProperty("content", `url("${url}")`, "important")
    el.setAttribute("data-pinned", "")
  }, { k, url: png && `data:image/png;base64,${png.toString("base64")}` })
  return !!png
}

// Every element's box and paint, in document order (rendering), and which of them
// differ from an earlier reading (unchanged), marked data-changed-without-scripts.
function rendering() {
  const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
  return roots.flatMap((root) => [...root.querySelectorAll("*")].map((el) => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el)
    return [r.x, r.y, r.width, r.height, cs.display, cs.visibility, cs.opacity, cs.color, cs.backgroundColor, cs.backgroundImage.slice(0, 200), cs.transform].join("|")
  }))
}
function unchanged(before) {
  const roots = [document, ...[...document.querySelectorAll("*")].filter((el) => el.shadowRoot).map((el) => el.shadowRoot)]
  const els = roots.flatMap((root) => [...root.querySelectorAll("*")])
  const some = []
  let n = 0
  els.forEach((el, k) => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el)
    const now = [r.x, r.y, r.width, r.height, cs.display, cs.visibility, cs.opacity, cs.color, cs.backgroundColor, cs.backgroundImage.slice(0, 200), cs.transform].join("|")
    if (now === before[k]) return
    el.setAttribute("data-changed-without-scripts", "")
    if (some.length < 5) some.push(`<${el.tagName.toLowerCase()} class="${(el.className?.baseVal ?? el.className ?? "").toString().slice(0, 40)}"> ${before[k]} → ${now}`)
    n++
  })
  return { n, some }
}

// Puts the page at rest: every image and frame loaded (a lazy one far from the window
// would never load, so all are made eager), fonts in, every animation at its end
// (finite ones) or its first frame (infinite ones), every video paused at VIDEO_AT
// with that frame shown (once pinned, a video is left be). Covers shadow roots, where a swapped-in section lives. Only
// animations on page time: a scroll-driven one is where the scroll puts it, and how it
// looks in view was put back with the rest (look).
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
        if (!(a.timeline instanceof DocumentTimeline)) continue
        try { a.finish() } catch { a.pause(); a.currentTime = 0 }
      }
      for (const v of root.querySelectorAll("video:not([data-pinned])")) {
        v.pause()
        const at = Math.min(VIDEO_AT, (v.duration || 0) / 2)
        if (Math.abs(v.currentTime - at) > 0.01) v.currentTime = at
      }
    }
  }, VIDEO_AT)
  await settle(page)
}
