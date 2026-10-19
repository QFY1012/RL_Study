// 拿你在标注页(labels/report-marks.html)标过的页面对测评委:每对按两种顺序,用不给标准(none)和
// rubric-set.mjs 合成的标准(merged)各判一次,看和你选的是不是同一版。
//
//   source ~/.config/ui-rl/judge.env && NODE_USE_ENV_PROXY=1 node ui-rl/scripts/judge-marks.mjs <实验目录> <标注目录> <rubric-set 输出目录> <输出目录> [--workers 8]
//
// 标注目录是 ArtifactData 把 marks 集合存下来的目录(每对一个 <对>.json);页面编号对应哪一版查 labels/report-marks-key.json。
// 标准用 <rubric-set 输出目录>/merged.json;那次已经判过的同一对(judge/{none,merged}/<集>-<A>-<B>.json)直接拿来用,
// 缺的补跑,结果存在 <输出目录>/judge/<判法>/。你选「差不多」的对不算对错,单独列出。
// 左右调换的重复对只看你自己前后一不一致,不拿去判。
// 打印每对你选的、两种判法各两次的结果,按同类(editorial 之间、design 之间)和跨类分开数一致的次数,写 <输出目录>/summary.json。
import fs from "node:fs"
import path from "node:path"
import { call } from "../lib/llm.mjs"
import { request as requestOf, shot as shotOf, NONE, RUBRIC_JUDGE, listThemes, rubricBlock, askWinner } from "../lib/report-pages.mjs"

const [dir, marksDir, rubricDir, out] = process.argv.slice(2)
if (!out) throw new Error("usage: judge-marks.mjs <实验目录> <标注目录> <rubric-set 输出目录> <输出目录> [--workers 8]")
const arg = (k, d) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : d)
const WORKERS = Number(arg("workers", 8))
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")
const MODEL = process.env.JUDGE_MODEL ?? "deepseek-v4.1-flash"
const EFFORT = process.env.JUDGE_EFFORT ?? "high"
const ask = (sys, content, label) => call(sys, content, { key: KEY, model: MODEL, effort: EFFORT, label })
const load = (f) => JSON.parse(fs.readFileSync(f, "utf8"))
const pageKey = load(path.join(import.meta.dirname, "..", "labels", "report-marks-key.json"))
const rubricText = listThemes(load(path.join(rubricDir, "merged.json")).themes)
for (const m of ["none", "merged"]) fs.mkdirSync(path.join(out, "judge", m), { recursive: true })
fs.mkdirSync(path.join(out, "tiles"), { recursive: true })

const CHOICE = { left2: "左明显好", left1: "左稍好", tie: "差不多", right1: "右稍好", right2: "右明显好" }
// 你的标注:choice 是 left2/left1/tie/right1/right2,换成你选的那一版
const marks = fs.readdirSync(marksDir).filter((f) => f.endsWith(".json")).map((f) => load(path.join(marksDir, f))).map((m) => {
  const [l, r] = [pageKey[m.left].version, pageKey[m.right].version]
  const pick = m.choice === "tie" ? null : m.choice.startsWith("left") ? l : r
  const kind = l.split("-")[0] === r.split("-")[0] ? "同类" : "跨类"
  return { ...m, l, r, pick, kind, strong: m.choice.endsWith("2") }
}).sort((a, b) => a.pair.localeCompare(b.pair))
// 左右调换的重复对(repeat)只用来看你自己前后一不一致,不拿去判
const repeats = marks.filter((m) => m.repeat)
for (const r of repeats) {
  const o = marks.find((m) => m.pair === r.repeat)
  console.log(`重复 ${r.repeat}:第一次 ${CHOICE[o.choice]}(${o.pick ?? "差不多"}),第二次 ${CHOICE[r.choice]}(${r.pick ?? "差不多"}),${o.pick === r.pick ? "一致" : "不一致"}`)
}
marks.splice(0, marks.length, ...marks.filter((m) => !m.repeat))

async function judge(method, set, a, b) {
  const name = `${set}-${a}-${b}.json`, file = path.join(out, "judge", method, name), old = path.join(rubricDir, "judge", method, name)
  if (!fs.existsSync(file) && fs.existsSync(old)) fs.copyFileSync(old, file)
  if (fs.existsSync(file)) return load(file)
  const shot = (v, label) => shotOf(path.join(dir, "gen", set, `${v}.png`), path.join(out, "tiles", `${set}-${v}`), label)
  const content = [requestOf(path.join(dir, "data", `${set}.json`)), ...(method === "merged" ? [rubricBlock(rubricText)] : []), ...shot(a, "页面 A"), ...shot(b, "页面 B")]
  const { winner, res } = await askWinner(ask, method === "merged" ? RUBRIC_JUDGE : NONE, content, `${method} ${set} ${a}/${b}`)
  const r = { set, A: a, B: b, winner, json: res.json, usage: res.usage, latencyMs: res.latencyMs }
  fs.writeFileSync(file, JSON.stringify(r, null, 1))
  return r
}

const jobs = marks.flatMap((m) => ["none", "merged"].flatMap((method) => [[m.l, m.r], [m.r, m.l]].map(([a, b]) => ({ m, method, a, b }))))
let next = 0, done = 0
console.log(`${marks.length} 对标注,${jobs.length} 次判定(已有的直接用)`)
await Promise.all(Array.from({ length: Math.min(WORKERS, jobs.length) }, async () => {
  while (next < jobs.length) {
    const j = jobs[next++]
    try { const r = await judge(j.method, j.m.set, j.a, j.b); j.picked = r.winner === "A" ? r.A : r.B } catch (e) { console.log(`失败:${j.method} ${j.m.pair}:${String(e.message).slice(0, 200)}`) }
    if (++done % 10 === 0 || done === jobs.length) console.log(`  ${done}/${jobs.length}`)
  }
}))

const summary = {}
for (const m of marks) {
  const cells = ["none", "merged"].map((method) => jobs.filter((j) => j.m === m && j.method === method).map((j) => j.picked ?? "失败").join(" / "))
  console.log(`${m.pair.padEnd(11)} ${m.kind} 左 ${m.l} 右 ${m.r};你:${CHOICE[m.choice]}(${m.pick ?? "差不多"});none 两次选 ${cells[0]};merged 两次选 ${cells[1]}`)
}
for (const kind of ["同类", "跨类"]) for (const method of ["none", "merged"]) {
  const js = jobs.filter((j) => j.m.kind === kind && j.method === method && j.m.pick && j.picked)
  const pairs = [...new Set(js.map((j) => j.m))]
  const both = pairs.filter((m) => js.filter((j) => j.m === m).every((j) => j.picked === m.pick)).length
  summary[`${kind} ${method}`] = { agree: `${js.filter((j) => j.picked === j.m.pick).length}/${js.length}`, pairsBothOrders: `${both}/${pairs.length}` }
  console.log(`${kind} ${method.padEnd(6)} 和你一致 ${summary[`${kind} ${method}`].agree} 次,两种顺序都一致 ${both}/${pairs.length} 对`)
}
const ties = marks.filter((m) => !m.pick).map((m) => m.pair)
if (ties.length) console.log(`你选差不多的(不算):${ties.join("、")}`)
fs.writeFileSync(path.join(out, "summary.json"), JSON.stringify({ pairs: marks.map((m) => ({ pair: m.pair, kind: m.kind, left: m.l, right: m.r, choice: m.choice, judged: Object.fromEntries(["none", "merged"].map((method) => [method, jobs.filter((j) => j.m === m && j.method === method).map((j) => ({ A: j.a, B: j.b, picked: j.picked ?? null }))])) })), ...summary }, null, 1))
