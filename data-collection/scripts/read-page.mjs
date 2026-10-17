// Reads a loaded page: splits it into sections, takes each section's content in
// reading order, and measures the page's design tokens. record.mjs reads the live page
// with it, render.mjs the replay, and the two readings are compared section by section.
// Sections are marked data-sec="<i>" in the page.
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

    // Content of a section, in reading order. Text comes from leaf blocks: elements
    // that are not inline and hold no non-inline element with text of their own.
    const content = (sec) => {
      const items = []
      const isBlock = (el) => getComputedStyle(el).display !== "inline"
      // A hidden element hides everything in it; an element with no size of its own
      // does not (a <picture> around an absolutely placed <img> is 0x0), so only the
      // first ends the walk.
      const walk = (el) => {
        if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return
        const tag = el.tagName
        if (tag === "IMG") {
          const r = el.getBoundingClientRect()
          if (r.width >= 24 && r.height >= 24) items.push({ kind: "image", src: el.currentSrc || el.src, alt: el.alt || "", aspect: +(el.naturalWidth / el.naturalHeight || r.width / r.height).toFixed(3) })
          return
        }
        // what a video or canvas shows is screenshot into an asset (shots, below)
        if (tag === "VIDEO" || tag === "CANVAS") {
          const r = el.getBoundingClientRect()
          if (r.width >= 48 && r.height >= 48) {
            shots.push(abs(r))
            items.push({ kind: "illustration", src: `shot:${shots.length - 1}`, alt: tag === "VIDEO" ? "video" : "canvas", aspect: +(r.width / r.height).toFixed(3) })
          }
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

    // Elements outside a section that paint over its box (content positioned from
    // elsewhere on the page) would stay put when the section is swapped and land on
    // top of the new one. Counted are elements that paint something (text, an image,
    // a background, a border), are bigger than a hairline, and lie mostly over the
    // section, not page-wide decorations spanning several sections. A section is
    // covered when they take up more than COVERED of its area: a corner mark or a
    // guide line crossing it does not count.
    const COVERED = 0.03
    const paints = (e) => {
      if (["IMG", "VIDEO", "CANVAS", "svg"].includes(e.tagName)) return true
      const cs = getComputedStyle(e)
      return [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) || cs.backgroundColor !== "rgba(0, 0, 0, 0)" || cs.backgroundImage !== "none" || parseFloat(cs.borderTopWidth) > 0
    }
    const overlaps = (sec) => {
      const R = sec.getBoundingClientRect()
      let area = 0
      const found = []
      for (const e of document.querySelectorAll("body *")) {
        if (sec.contains(e) || e.contains(sec) || e.closest("svg") !== null && e.tagName !== "svg") continue
        const r = e.getBoundingClientRect()
        if (r.height > 2 * R.height || r.width < 4 || r.height < 4) continue
        const w = Math.min(r.right, R.right) - Math.max(r.left, R.left), h = Math.min(r.bottom, R.bottom) - Math.max(r.top, R.top)
        if (w <= 0 || h <= 0 || (w * h) < 0.25 * r.width * r.height || !visible(e) || !paints(e)) continue
        area += w * h
        if (found.length < 3) found.push(`<${e.tagName.toLowerCase()} class="${(e.className?.baseVal ?? e.className ?? "").toString().slice(0, 40)}">`)
      }
      return area > COVERED * R.width * R.height ? found : []
    }

    const secs = list.map((el, i) => {
      el.setAttribute("data-sec", String(i))
      const items = content(el)
      return { i, tag: el.tagName.toLowerCase(), box: abs(el.getBoundingClientRect()), background: bg(el), items, overlappedBy: overlaps(el) }
    })
    return { secs, assets, shots }
  }, { MIN, MAX })

  // Videos and canvases are screenshot as they are now, as JPEG assets. A clip of the
  // full page, not an element screenshot: that waits for the element to hold still,
  // which a canvas drawing every frame never does.
  for (const [k, clip] of shots.entries()) {
    const jpg = await page.screenshot({ clip: { x: clip.x, y: clip.y, width: clip.w, height: clip.h }, fullPage: true, type: "jpeg", quality: 90, timeout: 60000 })
    assets.push(`data:image/jpeg;base64,${jpg.toString("base64")}`)
    for (const s of sections) for (const t of s.items) if (t.src === `shot:${k}`) t.src = `asset:${assets.length - 1}`
  }

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
  return { sections, assets, tokens }
}

// What has to be the same in two readings of a section for it to count as the same
// section: its height and its content (assets by their shape: an SVG's data carries
// computed styles, a screenshot's the moment it was taken).
export function signature(s) {
  return JSON.stringify([s.box.h, s.items.map((t) => [t.kind, t.text ?? (t.src.startsWith("asset:") ? t.aspect : t.src), t.href ?? null])])
}
