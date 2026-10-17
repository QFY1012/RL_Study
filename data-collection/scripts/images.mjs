// The image work of a site (site.mjs), done with canvases in a blank page of its own,
// where the page's screenshot (page.png) is decoded once and kept: where a section's
// content shows (differs), what the model is shown (look), and each pair with its seam
// (pair).
const MARGIN = 700 // page above and below the section in what the model is shown
const BAND = 300 // page above and below the section in a pair

export async function images(browser, pagePng) {
  const context = await browser.newContext()
  const blank = await context.newPage()
  await blank.evaluate(async (src) => {
    const img = new Image()
    img.src = src
    await img.decode()
    window.__page = img
    window.__jpeg = async (c, quality = 0.85) => {
      const blob = await c.convertToBlob({ type: "image/jpeg", quality })
      return await new Promise((ok) => { const f = new FileReader(); f.onload = () => ok(f.result); f.readAsDataURL(blob) })
    }
    window.__png = async (c) => {
      const blob = await c.convertToBlob({ type: "image/png" })
      return await new Promise((ok) => { const f = new FileReader(); f.onload = () => ok(f.result.split(",")[1]); f.readAsDataURL(blob) })
    }
    window.__open = async (src) => { const i = new Image(); i.src = src; await i.decode(); return i }
  }, `data:image/png;base64,${pagePng.toString("base64")}`)
  const url = (png) => `data:image/png;base64,${png.toString("base64")}`

  return {
    // Where a band of the page (a PNG of the page's full width, from top down) differs
    // from another band of the same place (base; or page.png), by more than over in
    // some channel: the box around every pixel that does, in page coordinates, or null.
    differs: (png, top, base = null, over = 0) => blank.evaluate(async ({ band, top, base, over }) => {
      const b = await window.__open(band)
      const a = base ? await window.__open(base) : window.__page
      const y = base ? 0 : top
      const w = Math.min(a.width, b.width), h = Math.min(b.height, a.height - y)
      const c = new OffscreenCanvas(w, h)
      const g = c.getContext("2d", { willReadFrequently: true })
      g.drawImage(a, 0, y, w, h, 0, 0, w, h)
      const p = g.getImageData(0, 0, w, h).data
      g.drawImage(b, 0, 0, w, h, 0, 0, w, h)
      const q = g.getImageData(0, 0, w, h).data
      let x0 = Infinity, y0 = Infinity, x1 = -1, y1 = -1
      for (let k = 0; k < p.length; k += 4) {
        if (Math.abs(p[k] - q[k]) <= over && Math.abs(p[k + 1] - q[k + 1]) <= over && Math.abs(p[k + 2] - q[k + 2]) <= over) continue
        const x = (k / 4) % w, yy = Math.floor(k / 4 / w)
        x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, yy); y1 = Math.max(y1, yy)
      }
      return x1 < 0 ? null : { x: x0, y: top + y0, w: x1 - x0 + 1, h: y1 - y0 + 1 }
    }, { band: url(png), top, base: base && url(base), over }),

    // What the model is shown for section s (generate.mjs), as JPEG data URLs:
    // - slot: the page around the section, MARGIN px above and below, at half size,
    //   with the section's content gone and its backdrop showing (empty: the box
    //   screenshot with the content hidden), its box outlined (dashed)
    // - items: each image, illustration and icon as it looks on the page, cut from
    //   page.png, at most 400px on its longer side
    look: (s, empty) => blank.evaluate(async ({ box, items, empty, MARGIN }) => {
      const a = window.__page, b = await window.__open(empty)
      const top = Math.max(0, box.y - MARGIN), bottom = Math.min(a.height, box.y + box.h + MARGIN)
      const c = new OffscreenCanvas(Math.round(a.width / 2), Math.round((bottom - top) / 2))
      const g = c.getContext("2d")
      g.scale(0.5, 0.5)
      g.drawImage(a, 0, top, a.width, bottom - top, 0, 0, a.width, bottom - top)
      g.drawImage(b, box.x, box.y - top)
      g.setLineDash([12, 8]); g.lineWidth = 4; g.strokeStyle = "rgb(255, 0, 128)"
      g.strokeRect(box.x + 2, box.y - top + 2, box.w - 4, box.h - 4)
      const look = { slot: await window.__jpeg(c), items: {} }
      for (const [j, r] of items) {
        const k = Math.min(1, 400 / Math.max(r.w, r.h))
        const ci = new OffscreenCanvas(Math.max(1, Math.round(r.w * k)), Math.max(1, Math.round(r.h * k)))
        ci.getContext("2d").drawImage(a, r.x, r.y, r.w, r.h, 0, 0, ci.width, ci.height)
        look.items[j] = await window.__jpeg(ci)
      }
      return look
    }, { box: s.box, items: s.items.map((t, j) => [j, t.box]).filter(([, b]) => b && b.w > 0 && b.h > 0), empty: url(empty), MARGIN }),

    // A pair: the original is page.png from BAND px above the section to BAND px below;
    // the generated one is the same with only the box's pixels taken from the render
    // (the box screenshot with the fragment swapped in), so everything around the box
    // is the original's own pixels. Returned as PNGs (orig, gen, side: both side by
    // side, for looking at) and genJpg, the generated one at half size as a JPEG data
    // URL (shown to the model in a revision).
    // Seam: the generated image must join the page the way the original does, or a
    // judge could tell the two apart by the edge of the box alone. For each side of the
    // box, the line of pixels just outside it is compared with the line just inside:
    // the share of pixels that differ (by more than 2 in any channel: a faint tint, a
    // near-white panel on white, is just what shows as a seam) is how much the page
    // breaks there. The original's own break is subtracted (a card it has flush with
    // the edge is not a seam). A side on the edge of the page has nothing outside it
    // and is not measured.
    pair: (s, rendered) => blank.evaluate(async ({ i, box, rendered, BAND }) => {
      const a = window.__page, b = await window.__open(rendered)
      const top = Math.max(0, box.y - BAND), bottom = Math.min(a.height, box.y + box.h + BAND)
      const band = (withGen) => {
        const c = new OffscreenCanvas(a.width, bottom - top)
        const g = c.getContext("2d", { willReadFrequently: true })
        g.drawImage(a, 0, top, a.width, bottom - top, 0, 0, a.width, bottom - top)
        if (withGen) g.drawImage(b, box.x, box.y - top)
        return c
      }
      const orig = band(false), gen = band(true)
      const y0 = box.y - top, y1 = y0 + box.h, x0 = box.x, x1 = box.x + box.w
      const line = (c, x, y, w, h) => c.getContext("2d").getImageData(x, y, w, h).data
      const breaks = (c, out, inn) => {
        const p = line(c, ...out), q = line(c, ...inn)
        let n = 0
        for (let k = 0; k < p.length; k += 4) if (Math.max(Math.abs(p[k] - q[k]), Math.abs(p[k + 1] - q[k + 1]), Math.abs(p[k + 2] - q[k + 2])) > 2) n++
        return n / (p.length / 4)
      }
      // (line just outside the box, line just inside), for each side that has an outside
      const sides = [
        ["top", [x0, y0 - 1, box.w, 1], [x0, y0, box.w, 1], box.y > 0],
        ["bottom", [x0, y1, box.w, 1], [x0, y1 - 1, box.w, 1], box.y + box.h < a.height],
        ["left", [x0 - 1, y0, 1, box.h], [x0, y0, 1, box.h], x0 > 0],
        ["right", [x1, y0, 1, box.h], [x1 - 1, y0, 1, box.h], x1 < a.width],
      ].filter(([, , , there]) => there)
      const seam = Object.fromEntries(sides.map(([side, out, inn]) => [side, Math.round(Math.max(breaks(gen, out, inn) - breaks(orig, out, inn), 0) * 1000) / 1000]))
      const pad = 32, head = 56
      const side = new OffscreenCanvas(a.width * 2 + pad * 3, bottom - top + head + pad)
      const g = side.getContext("2d")
      g.fillStyle = "white"; g.fillRect(0, 0, side.width, side.height)
      g.fillStyle = "black"; g.font = "22px sans-serif"; g.textBaseline = "top"
      g.fillText(`section ${i}: original`, pad, 16)
      g.fillText(`section ${i}: generated (${BAND}px of page above and below)`, a.width + pad * 2, 16)
      g.drawImage(orig, pad, head)
      g.drawImage(gen, a.width + pad * 2, head)
      const half = new OffscreenCanvas(Math.round(gen.width / 2), Math.round(gen.height / 2))
      half.getContext("2d").drawImage(gen, 0, 0, half.width, half.height)
      return { seam, orig: await window.__png(orig), gen: await window.__png(gen), side: await window.__png(side), genJpg: await window.__jpeg(half) }
    }, { i: s.i, box: s.box, rendered: url(rendered), BAND }).then((r) => ({ ...r, orig: Buffer.from(r.orig, "base64"), gen: Buffer.from(r.gen, "base64"), side: Buffer.from(r.side, "base64") })),

    close: () => context.close(),
  }
}
