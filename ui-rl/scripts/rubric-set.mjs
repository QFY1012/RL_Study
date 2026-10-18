// 照 Auto-Rubric as Reward(arXiv 2605.08354)的做法,从几对已知好坏的报告页面归纳出一套通用评分标准,
// 再拿没参与归纳的页面对检验它。contrast-rubric.mjs 那轮的教训都改进来了:
// 不许写「完整呈现全部数据」这类条(editorial 不列原始表不算错);内容组织和版面(对齐、留白、字号层次、图表清不清楚)
// 两类都要写,只挡纯装饰偏好(圆角、阴影、颜色字体本身);只写截图上看得出的条;只适用于某类报告的条写成「如果有……就……」。
//
//   source ~/.config/ui-rl/judge.env && NODE_USE_ENV_PROXY=1 node ui-rl/scripts/rubric-set.mjs <实验目录> <输出目录> \
//     [--seed S0,P0,S-mix] [--test S-bare,P-small] [--none-from <contrast-rubric 输出目录>/judge/none] [--workers 8]
//
// 实验目录同 contrast-rubric.mjs:data/<集>.json,gen/<集>/{design,editorial}-<k>.png(k = 1..3),已知 editorial 那版更好。
//   1. 写:种子集每份取 editorial-k 对 design-k(k = 1..3)共 3 对,看请求、数据和两版截图(告诉它哪版好),写这一对的标准
//   2. 验:按这份标准判这一对(两种顺序),都判对才留下;判错就把评委的理由反馈回去重写(要再看两版截图),
//      最多重写 REVISE 次,还不对就扔掉
//   3. 合:把留下的标准合成一套通用标准(几个主题,每个主题几条要点),只看文字
//   4. 测:种子集里没用来写标准的 6 对(editorial-i 对 design-j,i ≠ j)、测试集的全部 9 对,每对两种顺序,
//      用合并后的标准判(merged);不给标准的判法(none)和 contrast-rubric.mjs 一样,--none-from 里已有的直接拿来用,缺的补跑
// 每次调用的结果存在 <输出目录>/seed/、merged.json、judge/<判法>/,已有的跳过,断了可以重跑。
// 最后打印每种判法判对的比例和选 A 的比例,写 <输出目录>/summary.json 和 rubric-set.md(给人看的标准和验证过程)。
import fs from "node:fs"
import path from "node:path"
import { call } from "../lib/llm.mjs"
import { request as requestOf, shot as shotOf, NONE } from "../lib/report-pages.mjs"

const [dir, out] = process.argv.slice(2)
if (!dir || !out) throw new Error("usage: rubric-set.mjs <实验目录> <输出目录> [--seed S0,P0,S-mix] [--test S-bare,P-small] [--none-from <dir>] [--workers 8]")
const arg = (k, d) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : d)
const SEED = arg("seed", "S0,P0,S-mix").split(","), TEST = arg("test", "S-bare,P-small").split(",")
const NONE_FROM = arg("none-from", null)
const WORKERS = Number(arg("workers", 8))
const REVISE = 2
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")
const MODEL = process.env.JUDGE_MODEL ?? "deepseek-v4.1-flash"
const EFFORT = process.env.JUDGE_EFFORT ?? "high"
for (const d of ["tiles", "seed", "judge/none", "judge/merged"]) fs.mkdirSync(path.join(out, d), { recursive: true })
const ask = (sys, content, label) => call(sys, content, { key: KEY, model: MODEL, effort: EFFORT, label })
const request = (set) => requestOf(path.join(dir, "data", `${set}.json`))
const shot = (set, name, label) => shotOf(path.join(dir, "gen", set, `${name}.png`), path.join(out, "tiles", `${set}-${name}`), label)
const save = (f, x) => fs.writeFileSync(f, JSON.stringify(x, null, 1))
const load = (f) => JSON.parse(fs.readFileSync(f, "utf8"))

// ---------------------------------------------------------------- 写、改、合用的规矩
const RULES = `- 只写能从页面截图上看出来的标准(不写 HTML 文件、代码块、外部资源这类截图上看不到的要求)。
- 页面不必逐条列出原始数据:挑哪些数据、怎么汇总、哪些放进正文,都是设计的一部分。不要写「完整呈现全部数据、字段、条目」这类条目;可以要求页面上写出的数字和事实与数据一致、不编造。
- 内容组织和版面两类都要写:内容组织指结论、顺序、分组、图表解读这些;版面指同类元素对不对齐、留白有没有把内容分组分清楚、字号层次有没有区分标题正文和注释、图表的刻度标签和数值清不清楚、有没有重叠截断溢出或大片空白。两类都影响读者能不能看清、看懂。
- 每条都要说清楚它让读者更容易看清或理解什么;不写只关于装饰偏好的条目(要不要圆角、阴影,用什么颜色和字体本身)。
- 每条都必须是通用的:不许出现这份报告里的具体名称、地点、产品、数字,换一份别的报告也能用;只适用于某类报告的(例如有时间序列、有待办事项的)写成「页面如果有……,就……」。
- 每条以「页面」开头,写成一句可以判断做得好坏的话;不提这两版页面(不写「更好的那版」之类)。`
const WRITE = `你的任务是从一个报告页面的请求、报告数据和照这个请求做出的两版页面里,总结出评分标准,用来比较同一个请求做出的页面哪版更好。
已知两版里哪版更好。先对比两版:更好的那版好在哪、更差的那版差在哪,再把这些差别写成 8–14 条标准,让按这些标准比较的人能判出更好的那版。
${RULES}
只输出 JSON:{"differences":"两版的主要差别,几句话","rubric":["页面……"]}`
const REWRITE = `你之前从这两版页面总结了评分标准,但评委按这些标准比较这两版时,判了更差的那版赢。下面给出旧标准和评委的理由。
先找出旧标准为什么判不对:是漏了更好的那版真正好的地方,还是有条目在奖励不重要的东西、或者条目本身不对。再重写 8–14 条标准。
${RULES}
只输出 JSON:{"diagnosis":"旧标准为什么判不对,几句话","rubric":["页面……"]}`
const MERGE = `下面是从几对报告页面里分别总结的评分标准,每份都验证过能判出这一对里更好的那版。把它们合成一套通用的评分标准,用来比较任何一份报告做出的两版页面:
- 合并意思相同的条目;只在一份里出现、又和别的冲突的去掉。
- 分成 4–8 个主题,每个主题 2–5 条要点;内容组织和版面都要有主题;主题按对读者看清、看懂内容的影响从大到小排。
${RULES}
只输出 JSON:{"themes":[{"name":"主题名","tips":["页面……"]}]}`
const JUDGE = `你是公正的评委。按给定的请求和评分标准,比较页面 A 和页面 B 哪版做得更好。
先逐条对照评分标准:这条上 A 好、B 好还是差不多,引用页面上的具体证据。再综合决定赢家:标准之间按对读者看清、看懂内容的影响大小取舍。只能选一个。A、B 的先后顺序是随意的,不要受它影响。
只输出 JSON:{"criteria":[{"no":"条目编号","better":"A 或 B 或 一样","why":"证据"}],"reason":"一到三句话","winner":"A 或 B"}`

const listFlat = (rubric) => rubric.map((t, i) => `${i + 1}. ${t}`).join("\n")
const listThemes = (themes) => themes.map((t, i) => `${i + 1}. ${t.name}\n${t.tips.map((x, j) => `   ${i + 1}.${j + 1} ${x}`).join("\n")}`).join("\n")
const rubricBlock = (text) => ({ type: "text", text: `<评分标准>\n${text}\n</评分标准>` })

// 判一次:rubricText 为 null 时不给标准(NONE)。结果存在 file,已有就直接读
async function judge(file, set, a, b, rubricText, label) {
  if (fs.existsSync(file)) return load(file)
  const content = [request(set), ...(rubricText ? [rubricBlock(rubricText)] : []), ...shot(set, a, "页面 A"), ...shot(set, b, "页面 B")]
  // 回复偶尔只在理由里写谁赢、没有 winner 这一项:没有 A 或 B 就重问,不能当成选了哪边
  let res, winner
  for (let t = 1; ; t++) {
    res = await ask(rubricText ? JUDGE : NONE, content, label)
    winner = String(res.json.winner ?? "").trim().replace(/^页面\s*/, "")
    if (winner === "A" || winner === "B") break
    if (t === 3) throw new Error(`${label}:三次回复都没有 A 或 B 的 winner`)
    console.log(`  ↻ ${label}:回复里没有 A 或 B 的 winner,重问`)
  }
  const r = { set, A: a, B: b, winner, correct: (winner === "A" ? a : b).startsWith("editorial"), json: res.json, usage: res.usage, latencyMs: res.latencyMs }
  save(file, r)
  return r
}

async function pool(jobs, run) {
  let next = 0, done = 0
  const results = []
  await Promise.all(Array.from({ length: Math.min(WORKERS, jobs.length) }, async () => {
    while (next < jobs.length) {
      const j = jobs[next++]
      try { results.push(await run(j)) } catch (e) { console.log(`失败:${j.label}:${String(e.message).slice(0, 200)}`) }
      if (++done % 10 === 0 || done === jobs.length) console.log(`  ${done}/${jobs.length}`)
    }
  }))
  return results
}

// ---------------------------------------------------------------- 1–2. 写、验、改
// 一对种子:第 0 版是写出来的,之后每版是按上一版的判定理由重写的;两种顺序都判对就停
async function seedPair(set, k) {
  const [e, d] = [`editorial-${k}`, `design-${k}`], tag = `${set}-${k}`
  const pages = [...shot(set, e, "更好的一版"), ...shot(set, d, "更差的一版")]
  const history = []
  for (let v = 0; v <= REVISE; v++) {
    const f = path.join(out, "seed", `${tag}-v${v}.json`)
    let r
    if (fs.existsSync(f)) r = load(f)
    else if (v === 0) r = (await ask(WRITE, [request(set), ...pages], `写 ${tag}`)).json
    else {
      const prev = history.at(-1)
      const why = prev.checks.filter((c) => !c.correct).map((c) => `(页面 A 是${c.A.startsWith("editorial") ? "更好" : "更差"}的那版)${c.json.reason}`).join("\n")
      r = (await ask(REWRITE, [request(set), ...pages, { type: "text", text: `<旧标准>\n${listFlat(prev.rubric)}\n</旧标准>\n<评委的理由>\n${why}\n</评委的理由>` }], `改 ${tag} 第 ${v} 次`)).json
    }
    save(f, r)
    const checks = []
    for (const [a, b] of [[e, d], [d, e]]) checks.push(await judge(path.join(out, "seed", `${tag}-v${v}-check-${a}-${b}.json`), set, a, b, listFlat(r.rubric), `验 ${tag} v${v} ${a}/${b}`))
    history.push({ ...r, version: v, checks })
    console.log(`${tag} 第 ${v} 版:${r.rubric.length} 条,验证 ${checks.filter((c) => c.correct).length}/2`)
    if (checks.every((c) => c.correct)) return { tag, set, kept: true, history }
  }
  return { tag, set, kept: false, history }
}

console.log(`写标准:种子集 ${SEED.join("、")} 各 3 对`)
const seeds = await pool(SEED.flatMap((set) => [1, 2, 3].map((k) => ({ set, k, label: `${set}-${k}` }))), ({ set, k }) => seedPair(set, k))
const kept = seeds.filter((s) => s.kept)
console.log(`留下 ${kept.length}/${seeds.length} 对的标准`)
if (!kept.length) throw new Error("没有一对的标准通过验证")

// ---------------------------------------------------------------- 3. 合
const mergedFile = path.join(out, "merged.json")
if (!fs.existsSync(mergedFile)) {
  const text = kept.map((s, i) => `<第 ${i + 1} 份>\n${listFlat(s.history.at(-1).rubric)}\n</第 ${i + 1} 份>`).join("\n")
  save(mergedFile, (await ask(MERGE, [{ type: "text", text }], "合并")).json)
}
const merged = load(mergedFile)
console.log(`合并成 ${merged.themes.length} 个主题、${merged.themes.reduce((n, t) => n + t.tips.length, 0)} 条要点`)

// ---------------------------------------------------------------- 4. 测
// none 判法和 contrast-rubric.mjs 的完全一样(同一个提示词、同样的输入),那次已有的直接拿来
if (NONE_FROM) for (const f of fs.readdirSync(NONE_FROM)) {
  const to = path.join(out, "judge", "none", f)
  if (!fs.existsSync(to)) fs.copyFileSync(path.join(NONE_FROM, f), to)
}
const pairsOf = (set) => {
  const ps = []
  for (let i = 1; i <= 3; i++) for (let j = 1; j <= 3; j++) if (TEST.includes(set) || i !== j) ps.push([`editorial-${i}`, `design-${j}`])
  return ps
}
const jobs = []
for (const set of [...SEED, ...TEST]) for (const [e, d] of pairsOf(set)) for (const [a, b] of [[e, d], [d, e]]) for (const method of ["none", "merged"])
  jobs.push({ method, set, a, b, label: `${method} ${set} ${a}/${b}` })
console.log(`判定:${jobs.length} 次(已有的跳过)`)
const results = await pool(jobs, async (j) => ({ method: j.method, group: TEST.includes(j.set) ? "test" : "seed", ...(await judge(path.join(out, "judge", j.method, `${j.set}-${j.a}-${j.b}.json`), j.set, j.a, j.b, j.method === "merged" ? listThemes(merged.themes) : null, j.label)) }))

// ---------------------------------------------------------------- 汇总
const summary = {}
for (const method of ["none", "merged"]) for (const group of ["seed", "test"]) {
  const rs = results.filter((r) => r.method === method && r.group === group)
  const pairKey = (r) => `${r.set} ${[r.A, r.B].sort().join(" ")}`
  const keys = [...new Set(rs.map(pairKey))]
  const both = keys.filter((k) => { const x = rs.filter((r) => pairKey(r) === k); return x.length === 2 && x.every((r) => r.correct) }).length
  const bySet = Object.fromEntries([...new Set(rs.map((r) => r.set))].map((s) => { const x = rs.filter((r) => r.set === s); return [s, `${x.filter((r) => r.correct).length}/${x.length}`] }))
  summary[`${method} ${group}`] = { judgments: `${rs.filter((r) => r.correct).length}/${rs.length}`, pairsBothOrders: `${both}/${keys.length}`, pickA: `${rs.filter((r) => r.winner === "A").length}/${rs.length}`, bySet }
  console.log(`${method.padEnd(6)} ${group === "seed" ? "种子集其余对" : "测试集      "} 判对 ${summary[`${method} ${group}`].judgments},两种顺序都对 ${both}/${keys.length},选 A ${summary[`${method} ${group}`].pickA};${Object.entries(bySet).map(([s, v]) => `${s} ${v}`).join(",")}`)
}
save(path.join(out, "summary.json"), { seeds: seeds.map((s) => ({ tag: s.tag, kept: s.kept, versions: s.history.length })), ...summary })

const md = [`# 通用评分标准(${new Date().toISOString().slice(0, 10)})`, "", `种子集 ${SEED.join("、")} 各 3 对写标准,${kept.length}/${seeds.length} 对通过验证;测试集 ${TEST.join("、")}。`, "",
  "## 合并后的标准", "", listThemes(merged.themes), "", "## 每对的标准和验证", ""]
for (const s of seeds) {
  md.push(`### ${s.tag}(${s.kept ? "留下" : "扔掉"})`, "")
  for (const h of s.history) md.push(`第 ${h.version} 版,验证 ${h.checks.filter((c) => c.correct).length}/2${h.diagnosis ? `。改写原因:${h.diagnosis}` : `。两版差别:${h.differences ?? ""}`}`, "", listFlat(h.rubric), "")
}
fs.writeFileSync(path.join(out, "rubric-set.md"), md.join("\n"))
console.log(`写了 ${path.join(out, "summary.json")}、${path.join(out, "rubric-set.md")}`)
