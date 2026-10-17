// Reads a loaded page: splits it into sections, takes each section's content in
// reading order, and measures the page's design tokens. record.mjs reads the live page
// with it, render.mjs the replay, and the two readings are compared section by section.
// Sections are marked data-sec="<i>" in the page.
export async function readPage(page) {
  // Sections: from <body>, go down through wrappers (one child holding most of the
  // height) to the element whose children are stacked blocks; children taller than
  // MAX are split the same way. Each section gets data-sec="<i>".
  const MIN = 120, MAX = 1800
  const { secs: sections, assets } = await page.evaluate(({ MIN, MAX }) => {
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
  return { sections, assets, tokens }
}

// What has to be the same in two readings of a section for it to count as the same
// section: its height and its content (inline SVGs by their size, as their data
// carries computed styles).
export function signature(s) {
  return JSON.stringify([s.box.h, s.items.map((t) => [t.kind, t.text ?? (t.src.startsWith("asset:") ? t.aspect : t.src), t.href ?? null])])
}
