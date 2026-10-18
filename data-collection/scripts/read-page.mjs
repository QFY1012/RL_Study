// Reads a loaded page (site.mjs): splits it into sections, takes each section's
// content in reading order, and measures the page's design tokens. Sections are marked
// data-sec="<i>" in the page.
import { alone } from "./browser.mjs"

export async function readPage(page) {
  // Sections are the bands the page is stacked from, top to bottom. From <body> down:
  // an element whose children (those in flow) lie one under the other, none beside
  // another, is a stack, and each child is a section, or, if taller than MAX or only a
  // wrapper (one child in flow), split the same way; an element whose children sit
  // side by side (columns, a grid of cards) is one section, however tall, as cutting
  // it would cut a band apart. What is placed out of flow (absolute or fixed) lies over
  // the stack, not in it: a section's background layer, a header laid over the page;
  // content placed over a section (a heading over a picture) is a part of it (below).
  // A child shorter than MIN with nothing in it (a spacer, a rule) is no section. Each
  // section gets data-sec="<i>".
  const MIN = 120, MAX = 1800
  const { secs: sections, assets } = await page.evaluate(({ MIN, MAX }) => {
    // read afresh (site.mjs reads again once the page has come to rest)
    for (const e of document.querySelectorAll("[data-sec], [data-backdrop], [data-part], [data-shoot]")) for (const a of ["data-sec", "data-backdrop", "data-part", "data-shoot"]) e.removeAttribute(a)
    // shown: rendered, not hidden, not fully transparent (itself or an ancestor), with a size
    const visible = (el) => {
      const r = el.getBoundingClientRect()
      return el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) && r.height > 0 && r.width > 0
    }
    // children as laid out: an element with display: contents has no box of its own,
    // its children are laid out as its parent's (Framer wraps whole pages in them)
    const laidOut = (el) => [...el.children].flatMap((c) => (getComputedStyle(c).display === "contents" ? laidOut(c) : [c]))
    const kids = (el) => laidOut(el).filter((c) => !["SCRIPT", "STYLE", "NOSCRIPT", "LINK", "TEMPLATE"].includes(c.tagName) && visible(c))
    const outOfFlow = (c) => ["absolute", "fixed"].includes(getComputedStyle(c).position)
    const inFlow = (el) => kids(el).filter((c) => !outOfFlow(c))
    // one under the other: no two side by side, that is sharing rows (more than 2px)
    // while apart across (sharing less than half the narrower one's width). Two
    // sharing rows and the same width are stacked too, one laid over the other (a
    // negative margin pulling a block up over the one before).
    const stacked = (els) => {
      const rs = els.map((c) => c.getBoundingClientRect())
      return rs.every((a, k) => rs.slice(k + 1).every((b) => {
        const rows = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
        const across = Math.min(a.right, b.right) - Math.max(a.left, b.left)
        return rows <= 2 || across >= Math.min(a.width, b.width) / 2
      }))
    }
    const empty = (el) => !el.textContent.trim() && !el.querySelector("img, svg, video, canvas, picture, iframe")
    const split = (el) => {
      const k = inFlow(el)
      if (!k.length || !stacked(k)) return [el]
      return k.flatMap((c) => {
        const h = c.getBoundingClientRect().height
        if (h > MAX || inFlow(c).length === 1) return split(c)
        return h < MIN && empty(c) ? [] : [c]
      })
    }
    const list = split(document.body).sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
    list.forEach((el, i) => el.setAttribute("data-sec", String(i)))

    const abs = (r) => ({ x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) })
    const W = document.documentElement.scrollWidth, H = document.documentElement.scrollHeight
    // the part of a box that lies on the page (only that can show), or null
    const onPage = (r) => {
      const x0 = Math.max(0, r.left + scrollX), y0 = Math.max(0, r.top + scrollY)
      const x1 = Math.min(W, r.right + scrollX), y1 = Math.min(H, r.bottom + scrollY)
      return x1 - x0 >= 1 && y1 - y0 >= 1 ? { x: Math.round(x0), y: Math.round(y0), w: Math.round(x1 - x0), h: Math.round(y1 - y0) } : null
    }
    const PICTURES = ["IMG", "svg", "CANVAS", "VIDEO", "IFRAME"]
    const ownText = (e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())

    // What lies over a section from outside it. A page's framework can put part of a
    // section's content in a layer of its own elsewhere in the document, placed over the
    // section (vercel's hero picture and its link sit in a fixed layer at the end of
    // <body>; a heading placed over the picture its wrapper holds): a reader sees it as
    // the section's, and left out, it would stay over the
    // new content when the section is swapped. So a layer placed out of flow (absolute,
    // fixed) outside every section, the outermost such, with something in it to see
    // (text, a picture), is part of the section that at least half of what it shows lies
    // over: marked data-part="<i>", read with it and hidden with it (swap.mjs). One
    // mostly over no one section (a header across the top of the page) stays the page's.
    const holders = new Set()
    for (const el of list) for (let a = el.parentElement; a; a = a.parentElement) holders.add(a)
    const loose = [...document.body.querySelectorAll("*")].filter((e) => !holders.has(e) && !e.closest("[data-sec]") && !e.parentElement.closest("svg") && ["absolute", "fixed"].includes(getComputedStyle(e).position))
    const placed = new Set(loose)
    const secBoxes = list.map((el) => onPage(el.getBoundingClientRect()))
    for (const layer of loose) {
      let outer = true
      for (let a = layer.parentElement; a && outer; a = a.parentElement) if (placed.has(a)) outer = false
      if (!outer) continue
      const shown = [layer, ...layer.querySelectorAll("*")]
        .filter((e) => !e.parentElement.closest("svg") && (PICTURES.includes(e.tagName) || ownText(e)) && e.checkVisibility({ opacityProperty: true, visibilityProperty: true }))
        .map((e) => onPage(e.getBoundingClientRect())).filter(Boolean)
      if (!shown.length) continue
      const x0 = Math.min(...shown.map((b) => b.x)), y0 = Math.min(...shown.map((b) => b.y))
      const x1 = Math.max(...shown.map((b) => b.x + b.w)), y1 = Math.max(...shown.map((b) => b.y + b.h))
      const over = secBoxes.map((b) => (b ? Math.max(0, Math.min(x1, b.x + b.w) - Math.max(x0, b.x)) * Math.max(0, Math.min(y1, b.y + b.h) - Math.max(y0, b.y)) : 0))
      const best = over.indexOf(Math.max(...over))
      if (over[best] >= 0.5 * (x1 - x0) * (y1 - y0)) layer.setAttribute("data-part", String(best))
    }
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
    // are copied into <defs>. swap.mjs puts them back as data: URLs.
    const assets = [], shots = []
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
      return asset("data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(new XMLSerializer().serializeToString(clone)))))
    }
    // An image given as a data: URL is an asset too: it can run to many kilobytes
    const asset = (url) => { assets.push(url); return `asset:${assets.length - 1}` }
    const source = (url) => (url.startsWith("data:") ? asset(url) : url)
    // A picture shot from the page (pictures, below, for the sections a model gets):
    // marked data-shoot="<k>", its item's src shot:<k> until then
    let shoots = 0
    const shoot = (el) => { el.setAttribute("data-shoot", String(shoots)); return shoots++ }

    // A drawing: what the page marks as one picture (role=img), or keeps from screen
    // readers (aria-hidden) while its text is nowhere else on the page to read (not the
    // visible copy of a heading also given to screen readers whole, nor a carousel's
    // repeat of its cards): a product's screen, a diagram, a keyboard, built of HTML.
    // Its labels are part of the picture, not the section's copy, so it is one picture,
    // shot as it shows, not text items.
    const norm = (t) => t.toLowerCase().replace(/\s+/g, "")
    const readable = (() => {
      let out = ""
      const add = (n) => {
        for (const c of n.childNodes) {
          if (c.nodeType === 3) out += c.textContent
          else if (c.nodeType === 1 && !["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(c.tagName) && c.getAttribute("aria-hidden") !== "true") add(c)
        }
      }
      add(document.body)
      return norm(out)
    })()
    const drawing = (el) => {
      if (PICTURES.includes(el.tagName)) return false
      if (el.getAttribute("role") === "img") return true
      const t = el.getAttribute("aria-hidden") === "true" && norm(el.textContent)
      return !!t && !readable.includes(t)
    }

    // Rendered: laid out, not inside content-visibility: hidden, and not transparent
    // (itself or an ancestor). What is not rendered shows nothing of what is in it;
    // visibility: hidden does not go that far (a child can be visible again), so it is
    // looked at for each text and image.
    const rendered = (el) => el.checkVisibility({ opacityProperty: true })
    const seen = (el) => getComputedStyle(el).visibility === "visible"
    // The text of an element as a reader sees it: from the text nodes of elements that
    // are rendered and visible, a <br> as a line break, white space collapsed where the
    // page collapses it. Not innerText, which also gives text kept at opacity 0 (a card
    // that appears on hover) and screen-reader-only text squeezed into a 1px box; nor
    // what is inside an SVG (an icon's title), which is the icon's.
    const shownText = (el) => {
      let out = ""
      const add = (n) => {
        const cs = getComputedStyle(n), r = n.getBoundingClientRect()
        const shows = cs.visibility === "visible" && !(cs.overflow !== "visible" && (r.width <= 1 || r.height <= 1))
        for (const c of n.childNodes) {
          if (c.nodeType === 3) { if (shows) out += /^(pre|break-spaces)/.test(cs.whiteSpace) ? c.textContent : c.textContent.replace(/\s+/g, " ") }
          else if (c.nodeType !== 1 || ["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "svg"].includes(c.tagName)) continue
          else if (c.tagName === "BR") { if (shows) out += "\n" }
          else if (getComputedStyle(c).display === "contents" || rendered(c)) add(c)
        }
      }
      if (rendered(el)) add(el)
      return out.replace(/ *\n */g, "\n").replace(/ {2,}/g, " ").trim()
    }

    // Content of a section, in reading order. Text comes from leaf blocks: elements
    // that are not inline and either have text of their own or lay out no rendered
    // non-inline element with text.
    const content = (sec) => {
      const items = []
      const isBlock = (el) => getComputedStyle(el).display !== "inline"
      // An element that is not rendered shows nothing in it; one with no size of its
      // own still can (a <picture> around an absolutely placed <img> is 0x0, an element
      // with display: contents has no box at all), so only the first ends the walk.
      // A picture is given only for the part of it on the page, all that can show
      const walk = (el) => {
        if (getComputedStyle(el).display === "contents") { for (const c of el.children) walk(c); return }
        if (!rendered(el)) return
        const tag = el.tagName
        if (tag === "IMG") {
          const r = el.getBoundingClientRect(), box = onPage(r)
          if (seen(el) && box && r.width >= 24 && r.height >= 24) items.push({ kind: "image", src: source(el.currentSrc || el.src), alt: el.alt || "", aspect: +(el.naturalWidth / el.naturalHeight || r.width / r.height).toFixed(3), box })
          return
        }
        // what a video or canvas shows, and a drawing, is shot as it shows
        if (tag === "VIDEO" || tag === "CANVAS" || drawing(el)) {
          const box = onPage(el.getBoundingClientRect())
          const least = tag === "VIDEO" || tag === "CANVAS" ? 48 : 8
          if (seen(el) && box && box.w >= least && box.h >= least) {
            const k = shoot(el)
            items.push({ kind: box.w <= 48 && box.h <= 48 ? "icon" : "illustration", src: `shot:${k}`, alt: tag === "VIDEO" ? "video" : tag === "CANVAS" ? "canvas" : el.getAttribute("aria-label") || "", aspect: +(box.w / box.h).toFixed(3), box, shoot: k })
          }
          return
        }
        // an inline SVG is kept as its own source, and shot too: one that does not render
        // alone as it does in the page is given as its shot (pictures)
        if (tag === "svg") {
          const r = el.getBoundingClientRect(), box = onPage(r)
          if (seen(el) && box && r.width >= 8 && r.height >= 8) items.push({ kind: r.width <= 48 && r.height <= 48 ? "icon" : "illustration", src: svgAsset(el), alt: el.getAttribute("aria-label") || "", aspect: +(r.width / r.height).toFixed(3), box, shoot: shoot(el) })
          return
        }
        // a background image: an element showing only that, with nothing in it, is an
        // image like any other (a logo set as a background); one holding content shows
        // it behind the content, a picture when big enough
        // (the first url() of the computed value, which writes it in double quotes)
        const m = getComputedStyle(el).backgroundImage.match(/url\("((?:[^"\\]|\\.)*)"\)/)
        const r = el.getBoundingClientRect(), box = onPage(r)
        const bare = !el.children.length && !el.textContent.trim()
        if (m && seen(el) && box && !el.hasAttribute("data-backdrop") && (bare ? r.width >= 8 && r.height >= 8 : r.width >= 100 && r.height >= 100)) {
          items.push({ kind: bare && r.width <= 48 && r.height <= 48 ? "icon" : "image", src: source(m[1].replace(/\\(.)/g, "$1")), alt: bare ? el.getAttribute("aria-label") || el.getAttribute("title") || "" : "background", aspect: +(r.width / r.height).toFixed(3), box })
        }
        // text of its own (not in a child element) makes el a leaf, whatever is in it besides:
        // the text runs on around the rest, one sentence (chris-corby.com: "<a>Chris Corby</a>
        // is an independent ... <button>[...]</button>, as well as ..." in one <p>; read
        // child by child, only the link and the button were left of it)
        const blockKids = laidOut(el).filter((c) => rendered(c) && isBlock(c) && shownText(c))
        const text = shownText(el)
        const leaf = text && (blockKids.length === 0 || ownText(el)) && r.width > 0 && r.height > 0
        if (leaf) {
          const kind = /^H[1-6]$/.test(tag) || el.closest("h1,h2,h3,h4,h5,h6") ? "heading"
            : tag === "BUTTON" || el.closest("button,[role=button]") ? "button"
            : tag === "A" || el.closest("a") ? "link"
            : tag === "LI" ? "list-item" : "text"
          const href = el.closest("a")?.getAttribute("href")
          // text the original cuts off (ellipsis, line clamp) is marked, so the check and the prompt know
          const cs = getComputedStyle(el)
          const clamped = (cs.overflow !== "visible" || cs.webkitLineClamp !== "none") && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
          items.push({ kind, text, ...(href ? { href } : {}), ...(clamped ? { clamped: true } : {}) })
          // images and icons inside a text leaf (an icon in a button, say) still count
          for (const sub of el.querySelectorAll("img, svg")) if (!sub.closest("svg") || sub.tagName === "svg") walk(sub)
          return
        }
        for (const c of el.children) walk(c)
      }
      walk(sec)
      // and what lies over it from outside (data-part, above), after it
      for (const part of document.querySelectorAll(`[data-part="${sec.dataset.sec}"]`)) walk(part)
      return items
    }

    // A section's backdrop: what in it belongs to the page rather than to the section's
    // design. That is the section itself and, in it, the elements that only paint a
    // background or a border (no text of their own; not an image, video, canvas or svg)
    // and either cover (nearly) all of its box, such as layers of gradient behind the
    // content, or run from its top edge to its bottom edge, such as the frame lines of a
    // page whose grid runs through every section: what reaches both edges carries on
    // into the sections above and below. When a section is swapped (swap.mjs) the
    // backdrop stays and only the content on top is redesigned, so the generated
    // version keeps the original's band of color and the page's lines run on through
    // it. Marked data-backdrop; their backgrounds are not content items.
    const backdrop = (sec) => {
      const R = sec.getBoundingClientRect()
      const layers = [sec, ...sec.querySelectorAll("*")].filter((e) => {
        if (["IMG", "VIDEO", "CANVAS", "PICTURE"].includes(e.tagName) || e.closest("svg")) return false
        if (!e.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false
        if ([...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) return false
        const cs = getComputedStyle(e)
        const border = ["Top", "Right", "Bottom", "Left"].some((d) => parseFloat(cs[`border${d}Width`]) > 0 && cs[`border${d}Style`] !== "none")
        if (cs.backgroundColor === "rgba(0, 0, 0, 0)" && cs.backgroundImage === "none" && !border) return false
        const r = e.getBoundingClientRect()
        const w = Math.min(r.right, R.right) - Math.max(r.left, R.left), h = Math.min(r.bottom, R.bottom) - Math.max(r.top, R.top)
        return e === sec || (w > 0 && h > 0 && (w * h >= 0.9 * R.width * R.height || (r.top <= R.top + 2 && r.bottom >= R.bottom - 2)))
      })
      return layers.map((e) => {
        e.setAttribute("data-backdrop", "")
        const cs = getComputedStyle(e), r = e.getBoundingClientRect()
        const borders = ["top", "right", "bottom", "left"].filter((d) => parseFloat(cs.getPropertyValue(`border-${d}-width`)) > 0 && cs.getPropertyValue(`border-${d}-style`) !== "none")
          .map((d) => `${d} ${cs.getPropertyValue(`border-${d}-width`)} ${cs.getPropertyValue(`border-${d}-color`)}`)
        return {
          x: Math.round(r.left - R.left), w: Math.round(r.width),
          color: cs.backgroundColor, image: cs.backgroundImage === "none" ? null : cs.backgroundImage.slice(0, 400),
          border: borders.length ? borders.join(", ") : null, opacity: +cs.opacity,
        }
      })
    }

    const secs = list.map((el, i) => {
      // text right in the section element is wrapped in a plain <span>, so that, like the
      // rest of its content, it can be hidden on its own when the section is swapped
      // (swap.mjs): hiding the section element would hide its backdrop with it
      for (const n of [...el.childNodes]) if (n.nodeType === 3 && n.textContent.trim()) n.replaceWith(Object.assign(document.createElement("span"), { textContent: n.textContent }))
      const layers = backdrop(el)
      const items = content(el)
      return { i, tag: el.tagName.toLowerCase(), box: abs(el.getBoundingClientRect()), background: bg(el), backdrop: layers, items }
    })
    return { secs, assets }
  }, { MIN, MAX })

  // Where each section's content runs across the page (extent), and from that the
  // page's column: the left edge most sections' content starts at (within 2px), and as
  // far from the right edge of the page
  for (const s of sections) s.edges = await page.evaluate(extent, { sec: s.i })
  const W = await page.evaluate(() => document.documentElement.scrollWidth)
  const lefts = sections.map((s) => s.edges?.left).filter((x) => x != null && x < W / 2)
  const count = (x) => lefts.filter((y) => Math.abs(y - x) <= 2).length
  const left = lefts.length ? lefts.reduce((a, b) => (count(b) > count(a) || (count(b) === count(a) && b < a) ? b : a)) : 0
  const column = { left, right: W - left }

  // Page-level design tokens: the fonts actually used for headings and body text, the
  // font faces the page has loaded (family, weight, style: only these render), the type
  // scale, the most used text and background colors, and the page's column.
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
    // The page's type scale: every style the sections' copy is set in (font, size, line
    // height, weight, letter spacing), with its role (heading level, button, link, text)
    // and how many characters use it in each section; not the labels of a picture
    // (data-shoot: a drawing, an SVG). generate.mjs gives the model the styles of the
    // other sections than the one it redesigns.
    const styles = new Map()
    for (const el of document.querySelectorAll("[data-sec] *, [data-part], [data-part] *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join("")
      if (!own || el.closest("[data-shoot]") || !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue
      const cs = getComputedStyle(el)
      const h = el.closest("h1,h2,h3,h4,h5,h6")
      const role = h ? h.tagName.toLowerCase() : el.closest("button,[role=button]") ? "button" : el.closest("a") ? "link" : "text"
      const key = [role, cs.fontFamily.split(",")[0].trim().replace(/^["']|["']$/g, ""), cs.fontSize, cs.lineHeight, cs.fontWeight, cs.letterSpacing, cs.textTransform].join("|")
      const st = styles.get(key) ?? { chars: 0, sections: {} }
      const i = el.closest("[data-sec]")?.getAttribute("data-sec") ?? el.closest("[data-part]").getAttribute("data-part")
      st.chars += own.length
      st.sections[i] = (st.sections[i] ?? 0) + own.length
      styles.set(key, st)
    }
    const typeScale = [...styles.entries()].sort((a, b) => b[1].chars - a[1].chars).map(([key, st]) => {
      const [role, family, size, lineHeight, weight, letterSpacing, transform] = key.split("|")
      return { role, family, size, lineHeight, weight, letterSpacing, transform, chars: st.chars, sections: st.sections }
    })
    const faces = {}
    for (const f of document.fonts) if (f.status === "loaded") (faces[f.family.replace(/^["']|["']$/g, "")] ??= new Set()).add(`${f.weight}${f.style === "normal" ? "" : ` ${f.style}`}`)
    return {
      fonts: { heading: font("h1") ?? font("h2"), subheading: font("h2") ?? font("h3"), body: font("p") ?? getComputedStyle(document.body).fontFamily },
      faces: Object.fromEntries(Object.entries(faces).map(([k, v]) => [k, [...v].sort()])),
      typeScale,
      textColors: top(text, 6),
      backgroundColors: top(back, 6),
      pageBackground: getComputedStyle(document.body).backgroundColor,
    }
  })
  return { sections, assets, tokens: { ...tokens, column } }
}

// Where content runs across the page: from the left edge of the leftmost thing it shows
// to the right edge of the rightmost, cut to the page ({ left, right }, or null if it
// shows nothing), and the same of its text alone (text). Things shown are lines of
// text, pictures (img, svg, canvas, video, iframe) and boxes painted with a background,
// border or shadow (a card, a panel), not the section's backdrop. Of section i with its
// parts as the page has it ({ sec: i }), or of the fragment swapped in for it
// ({ gen: i }, swap.mjs). Run in the page (page.evaluate).
export function extent({ sec, gen }) {
  const roots = gen != null ? [document.querySelector(`[data-gen="${gen}"]`).shadowRoot] : [...document.querySelectorAll(`[data-sec="${sec}"], [data-part="${sec}"]`)]
  const W = document.documentElement.scrollWidth
  const all = { left: Infinity, right: -Infinity }, text = { left: Infinity, right: -Infinity }
  const add = (e, r) => { if (r.width > 0 && r.height > 0) { e.left = Math.min(e.left, r.left + scrollX); e.right = Math.max(e.right, r.right + scrollX) } }
  const range = document.createRange()
  for (const root of roots) {
    for (const el of [...(root.nodeType === 1 ? [root] : []), ...root.querySelectorAll("*")]) {
      if (el.parentElement?.closest("svg") || !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue
      if (["IMG", "svg", "CANVAS", "VIDEO", "IFRAME"].includes(el.tagName)) { add(all, el.getBoundingClientRect()); continue }
      for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim()) { range.selectNodeContents(n); const r = range.getBoundingClientRect(); add(all, r); add(text, r) }
      const cs = getComputedStyle(el)
      const painted = cs.backgroundColor !== "rgba(0, 0, 0, 0)" || cs.backgroundImage !== "none" || cs.boxShadow !== "none" || ["Top", "Right", "Bottom", "Left"].some((d) => parseFloat(cs[`border${d}Width`]) > 0 && cs[`border${d}Style`] !== "none")
      if (painted && !el.hasAttribute("data-backdrop")) add(all, el.getBoundingClientRect())
    }
  }
  const cut = (e) => (e.left < e.right ? { left: Math.round(Math.max(0, e.left)), right: Math.round(Math.min(W, e.right)) } : null)
  return all.left < all.right ? { ...cut(all), text: cut(text) } : null
}

// Whether content running across the page as e does (extent) keeps to its grid, all of
// it or its text: starts at the page's column (within 2px) or at the page's edge, or
// is centered on the page (within 3px). Text can keep to the grid while a picture runs
// past it (stripe's background of dots), and the edge of a card to it while the text in
// it is set in.
export const onGrid = (e, column, W) => {
  const keeps = (x) => !!x && (Math.abs(x.left - column.left) <= 2 || x.left <= 2 || Math.abs((x.left + x.right) / 2 - W / 2) <= 3)
  return !!e && (keeps(e) || keeps(e.text))
}

// The pictures in the given sections' items that are shot from the page (data-shoot):
// each shot alone (browser.mjs) into an asset, a PNG. An inline SVG kept as its own
// source (svgAsset) is shot too and compared with it (images.mjs, shot: unlike, the
// share of its pixels that differ), and given as its shot where it does not render
// alone as it does in the page: an SVG used as an image has no page around it, so none
// of the page's CSS (a keyboard drawn in HTML inside an SVG lays out as a column of
// labels), fonts or images. A picture that shows nothing in its shot (none of it on
// the page; or hidden there, say one of two logos stacked to cross-fade, cut away by
// what holds it) is no item. Done only for the sections a model gets: a shot is a
// full-page capture. Returns how many were shot, which SVGs are given as their shot
// (with how much they differed) and how many pictures showed nothing.
const UNLIKE = 0.01
export async function pictures(page, snap, sections, shotOf) {
  let shot = 0, unseen = 0
  const unlikeSvgs = []
  for (const s of sections) {
    const items = []
    for (const t of s.items) {
      if (t.shoot == null) { items.push(t); continue }
      const png = await alone(page, `[data-shoot="${t.shoot}"]`)
      const svg = t.src.startsWith("asset:") ? snap.assets[Number(t.src.slice("asset:".length))] : null
      const seen = png && (await shotOf(png, svg))
      if (!seen?.shows) { unseen++; continue }
      const url = `data:image/png;base64,${png.toString("base64")}`
      const { shoot, ...item } = t
      if (!svg) {
        snap.assets.push(url)
        item.src = `asset:${snap.assets.length - 1}`
        shot++
      } else if (seen.unlike > UNLIKE) {
        snap.assets[Number(t.src.slice("asset:".length))] = url
        unlikeSvgs.push(`#${s.i} ${t.src} ${t.box.w}x${t.box.h} ${(seen.unlike * 100).toFixed(1)}%`)
      }
      items.push(item)
    }
    s.items = items
  }
  return { shot, unlikeSvgs, unseen }
}
