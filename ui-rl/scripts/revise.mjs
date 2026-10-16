// 框选标注的第二步:按设计师在 labels/critique.html 里圈的意见改页面,得到「改后 ≻ 改前」的偏好对。
//
//   source judge.env && node scripts/revise.mjs [--critiques labels/critiques.json] [--only s01-v3,s04-v6] [--jobs 4]
//
// --critiques 是从标注页的 db 导出的 critiques 集合(数组,每条 {page, items:[{x,y,w,h,comment,hit}], note, fine, seconds})。
// 每页:在训练时的缩略图上画出框和编号(marked.png),交给生成 Agent 在原页面上改(generate.mjs 的 --base 加 change kind "critique",
// 用这页当时那一步的输出指南)。改后的页面在 runs/critique/revised/<页面>/<报告>/;
// 写出 labels/critique-pages/<页面>-after.webp 和 labels/critique-revisions.json(给标注页的「看改后」)。
// 已经改过的页面跳过;没写成的重试 1 次。
import fs from "node:fs"
import path from "node:path"
import { spawn, execFileSync } from "node:child_process"

const ROOT = path.resolve(import.meta.dirname, "..")
const GENERATE = path.join(ROOT, "gen", "scripts", "generate.mjs")
const arg = (k, d) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : d)
const LABELS = path.join(ROOT, "labels")
const PAGES = path.join(ROOT, "runs", "critique", "pages")
const REVISED = path.join(ROOT, "runs", "critique", "revised")
const JOBS = Number(arg("jobs", "4"))
const TIMEOUT_MIN = 20

const read = (f) => JSON.parse(fs.readFileSync(f, "utf8"))
const key = Object.fromEntries(read(path.join(LABELS, "critique-key.json")).map((k) => [k.id, k]))
const pub = Object.fromEntries(read(path.join(LABELS, "critique.json")).map((p) => [p.id, p]))
const only = arg("only")?.split(",")
const todo = read(path.resolve(ROOT, arg("critiques", "labels/critiques.json")))
  .filter((c) => !c.fine && (c.items.length || c.note) && key[c.page] && (!only || only.includes(c.page)))

// 框画在缩略图上(训练时生成 Agent 看的就是缩略图,宽度是截图的一半)
function mark(ws, items) {
  execFileSync("python3", ["-c", `
import json, sys
from PIL import Image, ImageDraw, ImageFont
im = Image.open(sys.argv[1]).convert("RGB"); d = ImageDraw.Draw(im)
k = im.width / 1248
font = ImageFont.load_default(size=18)
for i, b in enumerate(json.loads(sys.argv[3]), 1):
    x0, y0, x1, y1 = b["x"] * k, b["y"] * k, (b["x"] + b["w"]) * k, (b["y"] + b["h"]) * k
    d.rectangle([x0, y0, x1, y1], outline=(194, 65, 12), width=3)
    tw = d.textlength(str(i), font=font)
    d.rectangle([x0, y0 - 24, x0 + tw + 12, y0], fill=(194, 65, 12))
    d.text((x0 + 6, y0 - 22), str(i), fill="white", font=font)
im.save(sys.argv[2])`, path.join(ws, "thumb.png"), path.join(ws, "marked.png"), JSON.stringify(items)])
}

const built = (ws) => ["meta.json", "Page.tsx", "shot.png", "checks.json"].every((f) => fs.existsSync(path.join(ws, f)))
  && !read(path.join(ws, "checks.json")).some((c) => c.check === "能渲染")

function generate(c) {
  const k = key[c.page]
  const change = { kind: "critique", items: c.items.map((it, i) => ({ n: i + 1, comment: it.comment, hit: it.hit })), note: c.note || "" }
  const changeFile = path.join(REVISED, `${c.page}.change.json`)
  fs.writeFileSync(changeFile, JSON.stringify(change, null, 1))
  const guide = path.join(ROOT, "runs", "pilot", "steps", k.step, "guide.md")
  const args = [GENERATE, "--run", c.page, "--cases", k.report, "--traces", REVISED, "--base", path.relative(REVISED, path.join(PAGES, c.page)),
    "--change", changeFile, ...(fs.existsSync(guide) ? ["--guide", guide] : [])]
  return new Promise((resolve) => {
    const child = spawn(process.execPath, args, { env: process.env, detached: true, stdio: ["ignore", "pipe", "pipe"] })
    const relay = (s) => s.toString().split("\n").filter(Boolean).forEach((l) => console.log(`  [${c.page}] ${l}`))
    child.stdout.on("data", relay)
    child.stderr.on("data", relay)
    const timer = setTimeout(() => { console.log(`  [${c.page}] 超过 ${TIMEOUT_MIN} 分钟,结束`); try { process.kill(-child.pid, "SIGKILL") } catch {} }, TIMEOUT_MIN * 60_000)
    child.on("exit", () => { clearTimeout(timer); resolve() })
  })
}

async function revise(c) {
  const k = key[c.page]
  const ws = path.join(REVISED, c.page, k.report)
  if (!built(ws)) {
    mark(path.join(PAGES, c.page, k.report), c.items)
    for (let attempt = 0; attempt < 2 && !built(ws); attempt++) {
      if (fs.existsSync(ws)) fs.renameSync(ws, `${ws}.failed-${attempt + 1}`)
      const t0 = Date.now()
      await generate(c)
      console.log(`${c.page}:${built(ws) ? "改好了" : "没改成"},${Math.round((Date.now() - t0) / 1000)} 秒`)
    }
  }
  fs.rmSync(path.join(ws, ".build"), { recursive: true, force: true })
  if (!built(ws)) return null
  const after = `critique-pages/${c.page}-after.webp`
  const [w, h] = execFileSync("python3", ["-c", `
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB")
im.save(sys.argv[2], quality=82)
print(*im.size)`, path.join(ws, "shot.png"), path.join(LABELS, after)]).toString().trim().split(" ").map(Number)
  const meta = read(path.join(ws, "meta.json"))
  return { id: c.page, after, w, h, items: c.items.map(({ x, y, w, h, comment }) => ({ x, y, w, h, comment })), note: c.note || "",
    changedLines: meta.changedLines, checks: read(path.join(ws, "checks.json")).length, before: pub[c.page]?.image }
}

fs.mkdirSync(REVISED, { recursive: true })
console.log(`要改 ${todo.length} 页,同时 ${JOBS} 页`)
const out = []
const queue = [...todo]
await Promise.all(Array.from({ length: JOBS }, async () => {
  for (let c; (c = queue.shift());) { const r = await revise(c); if (r) out.push(r) }
}))
// 和已有的合并,按页面编号排
const file = path.join(LABELS, "critique-revisions.json")
const prev = fs.existsSync(file) ? read(file).filter((r) => !out.some((o) => o.id === r.id)) : []
const all = [...prev, ...out].sort((a, b) => a.id.localeCompare(b.id))
fs.writeFileSync(file, JSON.stringify(all, null, 1) + "\n")
console.log(`改好 ${out.length} / ${todo.length} 页;critique-revisions.json 共 ${all.length} 页`)
