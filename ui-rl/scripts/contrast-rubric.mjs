// 照 OpenRubrics(arXiv 2510.07743)的做法给报告页面写评分表、按表判:对比一对已知好坏的页面写出评分表
// (硬规定 + 质量原则),先检验它能不能判对这一对,再拿去判别的页面对。
//
//   source ~/.config/ui-rl/judge.env && NODE_USE_ENV_PROXY=1 node ui-rl/scripts/contrast-rubric.mjs <实验目录> <输出目录> [--sets P0,P-small,S0,S-bare,S-mix] [--workers 8]
//
// 实验目录是 data-ablation.mjs 那次的:data/<集>.json 是报告数据,gen/<集>/{design,editorial}-<k>.png 是
// plain-report.mjs 用 design、editorial 两种提示词各出 3 版的整页截图。已知 editorial 那版更好(人看过)。
// 每个集:
//   1. 对比评分表(contrast):看请求、报告数据和一对页面(editorial-1 更好、design-1 更差),写评分表
//   2. 只看请求的评分表(blind):不给页面,只看请求和报告数据(OpenRubrics 生成器用的时候就是这样;论文没比过这两种)
//   3. 一致性检验:按对比评分表判 editorial-1 对 design-1(两种顺序),都判对这张表才算过
//   4. 其余 8 对(editorial-i 对 design-j,去掉 1 对 1)各按两种顺序,用四种判法判:
//        none 不给评分表直接问哪版好;blind、contrast 用第 2、1 步的评分表;
//        cross 用另一类数据的对比评分表(销售 S* 用 P0 的,牛仔裤口袋 P* 用 S0 的),看评分表搬到别的报告上还行不行
// 页面截图切成 1440 高的块给模型(tile-shot.py)。每次调用的结果存在 <输出目录>/rubrics/、<输出目录>/judge/<判法>/,
// 已有的跳过,断了可以重跑。最后打印每种判法判对的比例,写 <输出目录>/summary.json 和 rubrics.md(给人看的评分表)。
import fs from "node:fs"
import path from "node:path"
import { call } from "../lib/llm.mjs"
import { request as requestOf, shot as shotOf, NONE, askWinner } from "../lib/report-pages.mjs"

const [dir, out] = process.argv.slice(2)
if (!dir || !out) throw new Error("usage: contrast-rubric.mjs <实验目录> <输出目录> [--sets P0,P-small,S0,S-bare,S-mix] [--workers 8]")
const arg = (k, d) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : d)
const SETS = arg("sets", "P0,P-small,S0,S-bare,S-mix").split(",")
const WORKERS = Number(arg("workers", 8))
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")
const MODEL = process.env.JUDGE_MODEL ?? "deepseek-v4.1-flash"
const EFFORT = process.env.JUDGE_EFFORT ?? "high"
for (const d of ["tiles", "rubrics", "judge"]) fs.mkdirSync(path.join(out, d), { recursive: true })

const request = (set) => requestOf(path.join(dir, "data", `${set}.json`))
const shot = (set, name, label) => shotOf(path.join(dir, "gen", set, `${name}.png`), path.join(out, "tiles", `${set}-${name}`), label)

// ---------------------------------------------------------------- 写评分表
// OpenRubrics 生成器的提示词(RubricRM-8B-Rubric-v2 的模型说明里的原文)译成中文,「回答」换成「页面」
const RUBRIC_RULES = `- 两类:
  - [Hard Rule]:只来自请求里明说的要求(格式、尺寸、结构、必须有或不许有的东西等)。
  - [Principle]:把具体的线索抽象成和题材无关的质量标准(例如清楚、正确、推理可靠、好读)。
- 每条都必须是通用的:不许出现这份报告里的具体名称、地点、产品、数字。带这些的条目一律作废。
- 全面:覆盖请求明说的要求和隐含的质量标准。
- 简洁、不重复:每条是一个不同的标准,重叠的合成一条,措辞准确。
- 每条以「页面」开头,第三人称;只写标准本身,不写理由和例子。`
const BLIND = `你的任务是从用户的请求里总结出一张评分表,用来检查做出来的页面是否完全满足请求。
${RUBRIC_RULES}
只输出 JSON:{"rubric":[{"text":"页面……","type":"Hard Rule 或 Principle"}]}`
// 对比着写(OpenRubrics 造数据时的做法):给出一对页面并说明哪版更好,从两版的差别里总结
const CONTRAST = `你的任务是从用户的请求和照这个请求做出的两版页面里,总结出一张评分表,用来检查做出来的页面是否完全满足请求。
已知两版里哪版更好。先对比两版:更好的那版好在哪、更差的那版差在哪,再把这些差别和请求明说的要求一起写成评分条目,让按这张表打分的人能判出更好的那版。
${RUBRIC_RULES}
- 条目里不要提这两版页面(不写「更好的那版」之类),评分表要能拿去评别的页面。
只输出 JSON:{"differences":"两版的主要差别,几句话","rubric":[{"text":"页面……","type":"Hard Rule 或 Principle"}]}`

async function rubric(set, kind) {
  const file = path.join(out, "rubrics", `${set}-${kind}.json`)
  if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, "utf8"))
  const content = kind === "blind" ? [request(set)]
    : [request(set), ...shot(set, "editorial-1", "更好的一版"), ...shot(set, "design-1", "更差的一版")]
  const res = await call(kind === "blind" ? BLIND : CONTRAST, content, { key: KEY, model: MODEL, effort: EFFORT, label: `${set} ${kind} 评分表` })
  const r = { set, kind, ...res.json, usage: res.usage, latencyMs: res.latencyMs }
  fs.writeFileSync(file, JSON.stringify(r, null, 1))
  console.log(`${set} ${kind} 评分表:${r.rubric.length} 条,${Math.round(r.latencyMs / 1000)} 秒`)
  return r
}

// ---------------------------------------------------------------- 判一对
// OpenRubrics 评委的提示词(RubricRM-8B-Judge-v2 的模型说明里的原文)译成中文,输出改成 JSON
const JUDGE = `你是公正的评委。按给定的请求和评分表,比较页面 A 和页面 B,分三步:
第一步 门槛检查:从评分表里找出最重要、最客观的一条「门槛条」。客观指不用主观判断就能核对,例如尺寸、必须的输出格式、必须有或不许有的部分、不许出现的内容;关于质量的主观条目(例如「有创意」「写得清楚」「好读」)不能当门槛。一两句话说明为什么选它。
第二步 逐条分析:对门槛条和评分表的其他每一条,分别看 A 和 B,先引用页面上的具体证据,再判「达到」「部分达到」或「没达到」。
第三步 最终判定:综合前两步决定赢家,先写理由再给结论。只能选一个。
只输出 JSON:{"gatekeeper":{"no":条目编号,"why":"一两句话"},"A":[{"no":1,"verdict":"达到 或 部分达到 或 没达到","why":"证据"}],"B":[同上],"summary":"一到三句话:门槛条和其他条怎么决定了结果","winner":"A 或 B"}`
const listRubric = (r) => r.rubric.map((c, i) => `${i + 1}. ${c.text} [${c.type}]`).join("\n")

async function judge(method, set, rub, a, b) {
  const file = path.join(out, "judge", method, `${set}-${a}-${b}.json`)
  if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, "utf8"))
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const content = [request(set), ...(rub ? [{ type: "text", text: `<评分表>\n${listRubric(rub)}\n</评分表>` }] : []),
    ...shot(set, a, "页面 A"), ...shot(set, b, "页面 B")]
  const { winner, res } = await askWinner((sys, c, label) => call(sys, c, { key: KEY, model: MODEL, effort: EFFORT, label }), rub ? JUDGE : NONE, content, `${method} ${set} ${a}/${b}`)
  const r = { method, set, A: a, B: b, rubric: rub ? `${rub.set}-${rub.kind}` : null, winner, correct: (winner === "A" ? a : b).startsWith("editorial"), json: res.json, usage: res.usage, latencyMs: res.latencyMs }
  fs.writeFileSync(file, JSON.stringify(r, null, 1))
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

// ---------------------------------------------------------------- 跑
console.log(`写评分表:${SETS.length} 个集 × 对比、只看请求`)
const rubrics = {}
await pool(SETS.flatMap((set) => ["contrast", "blind"].map((kind) => ({ set, kind, label: `${set} ${kind}` }))),
  async ({ set, kind }) => { (rubrics[set] ??= {})[kind] = await rubric(set, kind) })
const crossOf = (set) => rubrics[set.startsWith("S") ? "P0" : "S0"]?.contrast

const pairs = []
for (let i = 1; i <= 3; i++) for (let j = 1; j <= 3; j++) pairs.push([`editorial-${i}`, `design-${j}`])
const both = ([e, d]) => [[e, d], [d, e]]
const jobs = []
for (const set of SETS) {
  if (!rubrics[set]?.contrast || !rubrics[set]?.blind) continue
  for (const [a, b] of both(pairs[0])) jobs.push({ method: "check", set, rub: rubrics[set].contrast, a, b })
  for (const p of pairs.slice(1)) for (const [a, b] of both(p)) {
    jobs.push({ method: "none", set, rub: null, a, b }, { method: "blind", set, rub: rubrics[set].blind, a, b }, { method: "contrast", set, rub: rubrics[set].contrast, a, b })
    if (crossOf(set)) jobs.push({ method: "cross", set, rub: crossOf(set), a, b })
  }
}
for (const j of jobs) j.label = `${j.method} ${j.set} ${j.a}/${j.b}`
console.log(`判定:${jobs.length} 次(已有的跳过)`)
const results = await pool(jobs, (j) => judge(j.method, j.set, j.rub, j.a, j.b))

// ---------------------------------------------------------------- 汇总
const summary = {}
for (const method of ["check", "none", "blind", "contrast", "cross"]) {
  const rs = results.filter((r) => r.method === method)
  const bySet = Object.fromEntries(SETS.map((s) => {
    const x = rs.filter((r) => r.set === s)
    return [s, `${x.filter((r) => r.correct).length}/${x.length}`]
  }))
  // 一对两种顺序都判对才算这对判对
  const pairKey = (r) => `${r.set} ${[r.A, r.B].sort().join(" ")}`
  const keys = [...new Set(rs.map(pairKey))]
  const pairOk = keys.filter((k) => rs.filter((r) => pairKey(r) === k).every((r) => r.correct) && rs.filter((r) => pairKey(r) === k).length === 2).length
  summary[method] = { judgments: `${rs.filter((r) => r.correct).length}/${rs.length}`, pairsBothOrders: `${pairOk}/${keys.length}`, bySet }
  console.log(`${method.padEnd(8)} 判对 ${summary[method].judgments},两种顺序都对的对 ${summary[method].pairsBothOrders};${Object.entries(bySet).map(([s, v]) => `${s} ${v}`).join(",")}`)
}
fs.writeFileSync(path.join(out, "summary.json"), JSON.stringify(summary, null, 1))

const md = [`# 评分表(${new Date().toISOString().slice(0, 10)})`, "", "对比评分表看了 editorial-1(更好)和 design-1(更差);只看请求的评分表只看了请求和报告数据。", ""]
for (const set of SETS) {
  const r = rubrics[set]
  if (!r) continue
  const check = results.filter((x) => x.method === "check" && x.set === set)
  md.push(`## ${set}`, "", `一致性检验(按对比评分表判 editorial-1 对 design-1,两种顺序):${check.filter((x) => x.correct).length}/${check.length} 判对`, "",
    "### 对比评分表", "", `两版的差别:${r.contrast?.differences ?? ""}`, "", listRubric(r.contrast ?? { rubric: [] }), "",
    "### 只看请求的评分表", "", listRubric(r.blind ?? { rubric: [] }), "")
}
fs.writeFileSync(path.join(out, "rubrics.md"), md.join("\n"))
console.log(`写了 ${path.join(out, "summary.json")}、${path.join(out, "rubrics.md")}`)
