// Render a workspace's Page.tsx with the book-grid component library (book/app)
// and check it: everything gen/scripts/shoot.mjs checks (columns, sections on
// field lines, data, bounds), then the book grid (book/check.mjs: line heights,
// every line of type on the 24px lines, pictures a whole number of fields from a
// field line). Nothing outside book/ is changed: shoot.mjs already renders with
// <workspace>/app when there is one, so this links book/app there for the run.
//
//   node book/shoot.mjs <workspace>
//
// Writes what shoot.mjs writes; the book findings are added to checks.json as
// 「书网格」. BOOK_OVERLAY=1 also writes book-grid.png, the page with the book
// check drawn on it (SHOOT_OVERLAY=1 still draws the column check as grid.png).
import fs from "node:fs"
import path from "node:path"
import http from "node:http"
import { spawnSync } from "node:child_process"
import { chromium } from "playwright-core"
import { bookOffenders } from "./check.mjs"

const ws = path.resolve(process.argv[2] ?? ".")
const link = path.join(ws, "app")
if (fs.existsSync(link) && !fs.lstatSync(link).isSymbolicLink()) {
  console.error(`${link} already holds a component library; move it away first`)
  process.exit(1)
}
fs.rmSync(link, { force: true })
fs.symlinkSync(path.resolve(import.meta.dirname, "app"), link)
let run
try {
  run = spawnSync(process.execPath, [path.resolve(import.meta.dirname, "..", "scripts", "shoot.mjs"), ws], { encoding: "utf8" })
} finally {
  fs.rmSync(link, { force: true })
}
const checksFile = path.join(ws, "checks.json")
const findings = fs.existsSync(checksFile) ? JSON.parse(fs.readFileSync(checksFile, "utf8")) : []
const OUT = path.join(ws, ".build")
// no build means shoot.mjs already reported why (能渲染)
if (run.status !== 0 || !fs.existsSync(path.join(OUT, "index.html"))) {
  process.stdout.write(run.stdout)
  process.stderr.write(run.stderr)
  process.exit(run.status ?? 1)
}

const MIME = { ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".woff2": "font/woff2", ".woff": "font/woff" }
const server = http.createServer((req, res) => {
  const p = path.join(OUT, decodeURIComponent(new URL(req.url, "http://x").pathname))
  if (!p.startsWith(OUT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) return res.writeHead(404).end()
  res.writeHead(200, { "content-type": MIME[path.extname(p)] ?? "application/octet-stream" })
  fs.createReadStream(p).pipe(res)
})
await new Promise((r) => server.listen(0, "127.0.0.1", r))
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium" })
let book = []
try {
  // the same viewport and frame as shoot.mjs, so the page lays out the same
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await page.goto(`http://127.0.0.1:${server.address().port}/index.html`)
  await page.waitForFunction(() => window.__READY__ === true, null, { timeout: 30000 })
  const draw = process.env.BOOK_OVERLAY === "1"
  book = await page.evaluate(bookOffenders, draw)
  if (draw) {
    const height = await page.evaluate(() => Math.ceil(document.documentElement.scrollHeight))
    await page.screenshot({ path: path.join(ws, "book-grid.png"), clip: { x: (1440 - 1152) / 2 - 48, y: 0, width: 1152 + 96, height }, fullPage: true })
  }
} finally {
  await browser.close()
  server.close()
}

const shown = book.slice(0, 12)
if (book.length > 12) shown.push(`还有 ${book.length - 12} 处不在书网格上`)
const all = [...findings, ...shown.map((msg) => ({ check: "书网格", msg }))]
fs.writeFileSync(checksFile, JSON.stringify(all, null, 1))
// shoot.mjs's own summary line is replaced by one that counts the book findings too
const lines = run.stdout.split("\n").filter((l) => l && !/^程序检查/.test(l) && !/^- \[/.test(l))
console.log(all.length ? `程序检查发现 ${all.length} 个问题:` : "程序检查全部通过。")
for (const f of all) console.log(`- [${f.check}]${f.line ? ` Page.tsx 第 ${f.line} 行:` : " "}${f.msg}`)
for (const l of lines) console.log(l)
