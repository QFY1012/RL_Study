// 框选标注:从训练产物里挑页面,重新渲染出整页截图和每个组件的位置,给 labels/critique.html 用。
//
//   node scripts/critique-pages.mjs [--run pilot] [--per-step 3]
//
// 每一步按分数挑最高、中间、最低各一版(--per-step 3),复制 Page.tsx 和 data.json 到
// runs/critique/pages/<id>/<报告>/,用 gen/scripts/shoot.mjs 重新渲染(仓库里只留了缩略图),
// 再量出页面上每个组件(带 data-slot 的元素)的位置。重新渲染的缩略图和训练时的逐像素比对,不一致就报出来。
//
// 写出:
//   labels/critique.json              给标注页:页面编号、图、尺寸,不含分数和版本
//   labels/critique-key.json          每页来自哪一步、哪一版、分数;标注页不发布这个文件
//   labels/critique-pages/<id>.webp   整页截图(1248px 宽)
//   labels/critique-pages/<id>.json   组件位置:节名、data-slot、开头的文字、x y w h(截图坐标)
import fs from "node:fs"
import path from "node:path"
import http from "node:http"
import { execFileSync } from "node:child_process"
import { createRequire } from "node:module"

const ROOT = path.resolve(import.meta.dirname, "..")
const require = createRequire(path.join(ROOT, "gen", "package.json"))
const { chromium } = require("playwright-core")

const arg = (k, d) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : d)
const RUN = arg("run", "pilot")
const PER_STEP = Number(arg("per-step", "3"))
const OUT = path.join(ROOT, "runs", "critique", "pages")
const LABELS = path.join(ROOT, "labels")
const SHOOT = path.join(ROOT, "gen", "scripts", "shoot.mjs")
// shoot.mjs 的截图范围:1440 宽的视口里,1152 的版心左右各留 48
const VIEWPORT = { width: 1440, height: 900 }
const CLIP_X = (VIEWPORT.width - 1152) / 2 - 48

// ---------- 挑页面 ----------
const stepsDir = path.join(ROOT, "runs", RUN, "steps")
const picks = []
for (const s of fs.readdirSync(stepsDir).sort()) {
  const f = path.join(stepsDir, s, "score.json")
  if (!fs.existsSync(f)) continue
  const { score } = JSON.parse(fs.readFileSync(f, "utf8"))
  const ranked = Object.entries(score).sort((a, b) => b[1] - a[1])
  const at = PER_STEP === 1 ? [0] : [...new Set(Array.from({ length: PER_STEP }, (_, i) => Math.round(i * (ranked.length - 1) / (PER_STEP - 1))))]
  for (const i of at) {
    const [v, sc] = ranked[i]
    const dir = path.join(ROOT, "runs", RUN, "pages", s, v)
    const [report] = fs.readdirSync(dir).filter((c) => fs.existsSync(path.join(dir, c, "Page.tsx")))
    if (report) picks.push({ id: `${s}-${v}`, step: s, version: v, report, score: sc, rank: i + 1, src: path.join(dir, report) })
  }
}

// ---------- 量组件位置 ----------
async function measure(build) {
  const MIME = { ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".woff2": "font/woff2", ".woff": "font/woff" }
  const server = http.createServer((req, res) => {
    const p = path.join(build, decodeURIComponent(new URL(req.url, "http://x").pathname))
    if (!p.startsWith(build) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) return res.writeHead(404).end()
    res.writeHead(200, { "content-type": MIME[path.extname(p)] ?? "application/octet-stream" })
    fs.createReadStream(p).pipe(res)
  })
  await new Promise((r) => server.listen(0, "127.0.0.1", r))
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium" })
  try {
    const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 })
    await page.goto(`http://127.0.0.1:${server.address().port}/index.html`)
    await page.waitForFunction(() => window.__READY__ === true, null, { timeout: 30000 })
    return await page.evaluate((clipX) => {
      const title = (sec) => sec?.querySelector(":scope [data-slot=section-header]")?.innerText.split("\n")[0].trim() ?? ""
      const nodes = []
      for (const el of document.querySelectorAll("main [data-slot]")) {
        const slot = el.getAttribute("data-slot")
        if (slot === "page" || slot === "section-body") continue
        const r = el.getBoundingClientRect()
        if (r.width < 2 || r.height < 2) continue
        nodes.push({
          slot,
          section: title(el.closest("[data-slot=section]")),
          text: (el.innerText || el.getAttribute("alt") || "").replace(/\s+/g, " ").trim().slice(0, 40),
          x: Math.round(r.left + scrollX - clipX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height),
        })
      }
      return nodes
    }, CLIP_X)
  } finally {
    await browser.close()
    server.close()
  }
}

// ---------- 渲染 ----------
fs.mkdirSync(path.join(LABELS, "critique-pages"), { recursive: true })
const pub = [], key = [], differ = []
for (const p of picks) {
  const ws = path.join(OUT, p.id, p.report)
  if (!fs.existsSync(path.join(ws, "shot.png"))) {
    fs.rmSync(ws, { recursive: true, force: true })
    fs.mkdirSync(ws, { recursive: true })
    for (const f of ["Page.tsx", "data.json"]) fs.copyFileSync(path.join(p.src, f), path.join(ws, f))
    const assets = path.join(ROOT, "data", "flow", p.report)
    if (fs.existsSync(assets)) fs.cpSync(assets, path.join(ws, "assets"), { recursive: true })
    fs.writeFileSync(path.join(ws, "tsconfig.json"), JSON.stringify({ compilerOptions: { jsx: "react-jsx", resolveJsonModule: true } }))
    execFileSync("node", [SHOOT, ws], { stdio: "ignore" })
  }
  if (!fs.existsSync(path.join(ws, "shot.png"))) { console.error(`${p.id}: 没有渲染出来,跳过(看 ${path.relative(ROOT, ws)}/checks.json)`); continue }
  if (!fs.readFileSync(path.join(ws, "thumb.png")).equals(fs.readFileSync(path.join(p.src, "thumb.png")))) differ.push(p.id)
  const nodes = await measure(path.join(ws, ".build"))
  const img = `critique-pages/${p.id}.webp`
  // 尺寸和 webp 由 Python 的 PIL 做(build-pairs.py 也这样转)
  const [w, h] = execFileSync("python3", ["-c", `
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB")
im.save(sys.argv[2], quality=82)
print(*im.size)`, path.join(ws, "shot.png"), path.join(LABELS, img)]).toString().trim().split(" ").map(Number)
  fs.writeFileSync(path.join(LABELS, "critique-pages", `${p.id}.json`), JSON.stringify(nodes))
  pub.push({ id: p.id, image: img, nodes: `critique-pages/${p.id}.json`, w, h })
  key.push({ id: p.id, step: p.step, version: p.version, report: p.report, score: p.score, rank: p.rank, page: path.relative(ROOT, p.src) })
  console.log(`${p.id}: ${p.report},${w}×${h},${nodes.length} 个组件`)
}

// 标注顺序按步打乱同一步的三版,免得总是先看到高分的
const order = pub.map((p, i) => [p, (i * 7919) % 3]).sort((a, b) => a[0].id.slice(0, 3).localeCompare(b[0].id.slice(0, 3)) || a[1] - b[1]).map(([p]) => p)
fs.writeFileSync(path.join(LABELS, "critique.json"), JSON.stringify(order, null, 1) + "\n")
fs.writeFileSync(path.join(LABELS, "critique-key.json"), JSON.stringify(key, null, 1) + "\n")
const mb = fs.readdirSync(path.join(LABELS, "critique-pages")).reduce((s, f) => s + fs.statSync(path.join(LABELS, "critique-pages", f)).size, 0) / 1e6
console.log(`共 ${pub.length} 页,${mb.toFixed(1)} MB`)
if (differ.length) console.log(`重新渲染的缩略图和训练时不一致:${differ.join("、")}(组件库或数据变过?)`)
