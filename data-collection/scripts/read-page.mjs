// Reads a loaded page (site.mjs): splits it into sections, takes each section's
// content in reading order, and measures the page's design tokens. Sections are marked
// data-sec="<i>" in the page.
export async function readPage(page) {
  // Sections: from <body>, go down through wrappers (one child holding most of the
  // height) to the element whose children are stacked blocks; children taller than
  // MAX are split the same way. Each section gets data-sec="<i>".
  const MIN = 120, MAX = 1800
  const { secs: sections, assets, shots } = await page.evaluate(({ MIN, MAX }) => {
    // shown: rendered, not hidden, not fully transparent (itself or an ancestor), with a size
    const visible = (el) => {
      const r = el.getBoundingClientRect()
      return el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) && r.height > 0 && r.width > 0
    }
    // children as laid out: an element with display: contents has no box of its own,
    // its children are laid out as its parent's (Framer wraps whole pages in them)
    const laidOut = (el) => [...el.children].flatMap((c) => (getComputedStyle(c).display === "contents" ? laidOut(c) : [c]))
    const kids = (el) => laidOut(el).filter((c) => !["SCRIPT", "STYLE", "NOSCRIPT", "LINK", "TEMPLATE"].includes(c.tagName) && visible(c))
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
      assets.push("data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(new XMLSerializer().serializeToString(clone)))))
      return `asset:${assets.length - 1}`
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
    // that are not inline and lay out no rendered non-inline element with text of its own.
    const content = (sec) => {
      const items = []
      const isBlock = (el) => getComputedStyle(el).display !== "inline"
      // An element that is not rendered shows nothing in it; one with no size of its
      // own still can (a <picture> around an absolutely placed <img> is 0x0, an element
      // with display: contents has no box at all), so only the first ends the walk.
      const walk = (el) => {
        if (getComputedStyle(el).display === "contents") { for (const c of el.children) walk(c); return }
        if (!rendered(el)) return
        const tag = el.tagName
        if (tag === "IMG") {
          const r = el.getBoundingClientRect()
          if (seen(el) && r.width >= 24 && r.height >= 24) items.push({ kind: "image", src: el.currentSrc || el.src, alt: el.alt || "", aspect: +(el.naturalWidth / el.naturalHeight || r.width / r.height).toFixed(3), box: abs(r) })
          return
        }
        // what a video or canvas shows is screenshot into an asset (shots, below)
        if (tag === "VIDEO" || tag === "CANVAS") {
          const r = el.getBoundingClientRect()
          if (seen(el) && r.width >= 48 && r.height >= 48) {
            shots.push(abs(r))
            items.push({ kind: "illustration", src: `shot:${shots.length - 1}`, alt: tag === "VIDEO" ? "video" : "canvas", aspect: +(r.width / r.height).toFixed(3), box: abs(r) })
          }
          return
        }
        if (tag === "svg") {
          const r = el.getBoundingClientRect()
          if (seen(el) && r.width >= 8 && r.height >= 8) items.push({ kind: r.width <= 48 && r.height <= 48 ? "icon" : "illustration", src: svgAsset(el), alt: el.getAttribute("aria-label") || "", aspect: +(r.width / r.height).toFixed(3), box: abs(r) })
          return
        }
        const bgImg = getComputedStyle(el).backgroundImage
        const m = bgImg && bgImg.match(/url\("?([^")]+)"?\)/)
        const r = el.getBoundingClientRect()
        if (m && seen(el) && !el.hasAttribute("data-backdrop") && r.width >= 100 && r.height >= 100) items.push({ kind: "image", src: m[1], alt: "background", aspect: +(r.width / r.height).toFixed(3), box: abs(r) })
        const blockKids = laidOut(el).filter((c) => rendered(c) && isBlock(c) && shownText(c))
        const text = shownText(el)
        const leaf = text && blockKids.length === 0 && r.width > 0 && r.height > 0
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
      el.setAttribute("data-sec", String(i))
      // text right in the section element is wrapped in a plain <span>, so that, like the
      // rest of its content, it can be hidden on its own when the section is swapped
      // (swap.mjs): hiding the section element would hide its backdrop with it
      for (const n of [...el.childNodes]) if (n.nodeType === 3 && n.textContent.trim()) n.replaceWith(Object.assign(document.createElement("span"), { textContent: n.textContent }))
      const layers = backdrop(el)
      const items = content(el)
      return { i, tag: el.tagName.toLowerCase(), box: abs(el.getBoundingClientRect()), background: bg(el), backdrop: layers, items }
    })
    return { secs, assets, shots }
  }, { MIN, MAX })

  // Videos and canvases are screenshot as they are now, as JPEG assets. A clip of the
  // full page, not an element screenshot: that waits for the element to hold still,
  // which a canvas drawing every frame never does.
  // Only what lies on the page can be screenshot: the clip is cut to the page, and an
  // element entirely off it (placed outside, say) shows nothing and is no item.
  const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }))
  for (const [k, clip] of shots.entries()) {
    const x = Math.max(0, clip.x), y = Math.max(0, clip.y)
    const w = Math.min(clip.x + clip.w, size.w) - x, h = Math.min(clip.y + clip.h, size.h) - y
    let src = null
    if (w >= 1 && h >= 1) {
      const jpg = await page.screenshot({ clip: { x, y, width: w, height: h }, fullPage: true, type: "jpeg", quality: 90, timeout: 60000 })
      assets.push(`data:image/jpeg;base64,${jpg.toString("base64")}`)
      src = `asset:${assets.length - 1}`
    }
    for (const s of sections) s.items = s.items.flatMap((t) => (t.src !== `shot:${k}` ? [t] : src ? [{ ...t, src }] : []))
  }

  // Page-level design tokens: the fonts actually used for headings and body text, the
  // font faces the page has loaded (family, weight, style: only these render), the type
  // scale, the most used text
  // and background colors, and the width the content keeps to.
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
    // The page's type scale: every style text is set in, inside the sections (font, size,
    // line height, weight, letter spacing), with its role (heading level, button, link,
    // text), how many characters use it and in which sections. generate.mjs gives the
    // model the styles used in other sections than the one it redesigns.
    const styles = new Map()
    for (const el of document.querySelectorAll("[data-sec] *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join("")
      if (!own || !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue
      const cs = getComputedStyle(el)
      const h = el.closest("h1,h2,h3,h4,h5,h6")
      const role = h ? h.tagName.toLowerCase() : el.closest("button,[role=button]") ? "button" : el.closest("a") ? "link" : "text"
      const key = [role, cs.fontFamily.split(",")[0].trim().replace(/^["']|["']$/g, ""), cs.fontSize, cs.lineHeight, cs.fontWeight, cs.letterSpacing, cs.textTransform].join("|")
      const st = styles.get(key) ?? { chars: 0, sections: new Set() }
      st.chars += own.length
      st.sections.add(Number(el.closest("[data-sec]").getAttribute("data-sec")))
      styles.set(key, st)
    }
    const typeScale = [...styles.entries()].sort((a, b) => b[1].chars - a[1].chars).slice(0, 40).map(([key, st]) => {
      const [role, family, size, lineHeight, weight, letterSpacing, transform] = key.split("|")
      return { role, family, size, lineHeight, weight, letterSpacing, transform, chars: st.chars, sections: [...st.sections].sort((a, b) => a - b) }
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
      contentWidth: contentWidth && Math.round(contentWidth),
    }
  })
  return { sections, assets, tokens }
}
