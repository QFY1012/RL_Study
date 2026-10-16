// 书网格检查(Müller-Brockmann《平面设计中的网格系统》的做法):正文 14px 字、24px 一行,其余纵向尺寸都是整行。
// 在 grid-check.mjs(左右边落在栏线上、每节从场线开始)之外再量三件事:
//   行高    页面上每段字的行高是 24 的倍数;
//   行      每一行字的行框上边落在 24px 的行线上(从页头上边算起);
//   图      截图和图表的上边落在行线上(接着上面的内容,和标签、说明同在一个场里),高度是整数行。
// 不量:图表里面的字(那是图的一部分)、跟着大号字落在同一条基线上的小字(数字后的单位)、标签徽章、
// 填满所在块的图表(它占的是块的场)。
//
// draw = true 时把检查画在页面上:淡红是 12 列,淡蓝是场,细蓝线是 24px 的行;
// 量过的图画绿框,出问题的字或图画红框并标上问题的编号。
export function bookOffenders(draw = false) {
  const main = document.querySelector("main")
  const head = main?.querySelector("[data-slot=page-header]")
  if (!main || !head) return []
  const LINE = 24, PITCH = 168
  const top = head.getBoundingClientRect().top
  const near = (y, step) => y - Math.round(y / step) * step
  const skipped = (el) =>
    !!el.closest("svg, [data-slot=chart], [data-slot=badge], [data-grid-overlay]") ||
    // a run of type on one baseline (a figure and its unit): the small type rides the big one's line
    (getComputedStyle(el.parentElement).display.includes("flex") && getComputedStyle(el.parentElement).alignItems === "baseline" && el.parentElement.children.length > 1)
  const label = (el) => {
    const slot = el.closest("[data-slot]")?.getAttribute("data-slot") ?? el.tagName.toLowerCase()
    return `${slot}「${(el.innerText || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 20)}」`
  }
  const out = [], marks = []

  // 行高和行:每个直接带字的元素量一次(它的第一行)。
  const heights = new Map()
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT) })
  const seen = new Set()
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement
    if (seen.has(el) || skipped(el)) continue
    seen.add(el)
    const lh = parseFloat(getComputedStyle(el).lineHeight)
    if (!(lh > 0) || Math.abs(near(lh, LINE)) > 0.5) {
      const key = `${el.closest("[data-slot]")?.getAttribute("data-slot")}|${lh}`
      if (!heights.has(key)) heights.set(key, { el, lh })
      continue
    }
    const range = document.createRange()
    range.selectNodeContents(n)
    const r = range.getClientRects()[0]
    if (!r) continue
    // the line box sits half the leading above the glyphs' box
    const d = near(r.top - (lh - r.height) / 2 - top, LINE)
    if (Math.abs(d) > 1.5) {
      out.push(`${label(el)}这一行没有落在 24px 的行线上:离最近的行线 ${Math.round(d)}px`)
      const b = el.getBoundingClientRect()
      marks.push([b.left, b.top, b.width, b.height, "off", out.length])
    }
  }
  for (const { el, lh } of heights.values()) {
    out.push(`${label(el)}的行高是 ${lh > 0 ? `${Math.round(lh * 10) / 10}px` : "没有设定"},不是 24px 的整数倍`)
    const b = el.getBoundingClientRect()
    marks.push([b.left, b.top, b.width, b.height, "off", out.length])
  }

  // 图:截图的图框、不是填满所在块的图表。一个场里可以放几样东西,图从哪条行线开始都行。
  for (const el of main.querySelectorAll("[data-slot=figure-image], [data-slot=custom-chart][data-picture]")) {
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) continue
    const dTop = near(r.top - top, LINE), dH = near(r.height, LINE)
    if (Math.abs(dTop) <= 1 && Math.abs(dH) <= 1) {
      marks.push([r.left, r.top, r.width, r.height, "ok"])
      continue
    }
    const where = []
    if (Math.abs(dTop) > 1) where.push(`上边离最近的行线 ${Math.round(dTop)}px`)
    if (Math.abs(dH) > 1) where.push(`高 ${Math.round(r.height)}px,不是整数行`)
    out.push(`${label(el)}没有落在行上:${where.join(",")}`)
    marks.push([r.left, r.top, r.width, r.height, "off", out.length])
  }

  if (draw) {
    const sy = window.scrollY, height = document.documentElement.scrollHeight
    const left = main.getBoundingClientRect().left
    const layer = document.createElement("div")
    layer.setAttribute("data-grid-overlay", "")
    layer.style.cssText = `position:absolute;left:0;top:0;width:100%;height:${height}px;pointer-events:none;z-index:2147483647`
    const box = (x, y, w, h, css) => {
      const d = document.createElement("div")
      d.style.cssText = `position:absolute;left:${x}px;top:${y + sy}px;width:${w}px;height:${h}px;box-sizing:border-box;${css}`
      layer.appendChild(d)
      return d
    }
    for (let k = 0; k < 12; k++) {
      box(left + k * 98, -sy, 74, height, "background:rgba(255,0,0,.06)")
      box(left + k * 98, -sy + 4, 74, 16, "font:11px/16px monospace;color:rgba(200,0,0,.8);text-align:center").textContent = k + 1
    }
    for (let y = top; y < height - sy; y += PITCH) box(left - 48, y, 1152 + 96, 144, "background:rgba(0,110,255,.05);border-top:1px solid rgba(0,110,255,.5)")
    for (let y = top; y < height - sy; y += LINE) box(left - 48, y, 1152 + 96, 1, "background:rgba(0,110,255,.18)")
    for (const [x, y, w, h, kind, n] of marks) {
      box(x, y, w, h, kind === "ok" ? "border:2px solid rgba(0,150,60,.8)" : "border:2px solid #e00;background:rgba(255,0,0,.06)")
      if (n) box(x, y - 20, 20, 20, "background:#e00;color:#fff;font:bold 12px/20px sans-serif;text-align:center;border-radius:10px").textContent = n
    }
    document.body.appendChild(layer)
  }
  return out
}
