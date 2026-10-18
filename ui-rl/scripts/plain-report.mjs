// 只给报告数据(JSON)让模型直接写一个报告网页:不给组件库、设计规范、网格和示例,看模型自己会做成什么样。
//
//   source judge.env && NODE_USE_ENV_PROXY=1 node ui-rl/scripts/plain-report.mjs <数据 json> <输出目录> [--n 3] [--tag plain]
//
// 截图(json 里 image 字段的相对路径)要先放在 <输出目录> 里(data/draw.mjs 的 phone() 画)。每一版写
// <输出目录>/<tag>-<k>.html,并在 1440px 宽下截整页图 <tag>-<k>.png;请求和回复存在 <tag>-<k>.json。
// --tag 区分不同模型或端点的结果(默认 plain)。
// 模型用 JUDGE_URL 的端点,GEN_MODEL 选模型(默认 deepseek-v4.1-flash),默认温度。
import fs from "node:fs"
import path from "node:path"
import { createRequire } from "node:module"

const [dataFile, out] = process.argv.slice(2)
if (!dataFile || !out) throw new Error("usage: plain-report.mjs <数据 json> <输出目录> [--n 3] [--tag plain]")
const arg = (k, d) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : d)
const N = Number(arg("n", 3)), TAG = arg("tag", "plain")
const URL_ = process.env.JUDGE_URL ?? "https://api.deepseek.com/chat/completions"
const MODEL = process.env.GEN_MODEL ?? "deepseek-v4.1-flash"
const KEY = process.env.DEEPSEEK_API_KEY
if (!KEY) throw new Error("set DEEPSEEK_API_KEY (source judge.env)")
const { chromium } = createRequire(import.meta.url)("../gen/node_modules/playwright-core")
const CHROME = process.env.CHROME ?? "/opt/pw-browsers/chromium"

const SYSTEM = `把用户给的报告数据(JSON)做成一个网页。
输出一个完整的 HTML 文件,CSS 和 JS 都写在文件里,不引用外部资源(图片除外)。JSON 里 image 字段是截图的相对路径,直接用。
只回复放在一个 \`\`\`html 代码块里的 HTML。`
const data = fs.readFileSync(dataFile, "utf8")

async function one(k) {
  const t = Date.now()
  const messages = [{ role: "system", content: SYSTEM }, { role: "user", content: data }]
  const res = await fetch(URL_, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${KEY}` },
    body: JSON.stringify({ model: MODEL, messages, max_tokens: 65536 }),
    signal: AbortSignal.timeout(900_000),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status} ${(await res.text()).slice(0, 300)}`)
  const body = await res.json()
  const reply = body.choices?.[0]?.message?.content ?? ""
  fs.writeFileSync(path.join(out, `${TAG}-${k}.json`), JSON.stringify({ model: MODEL, messages, reply, usage: body.usage, finish: body.choices?.[0]?.finish_reason }, null, 1))
  const html = reply.match(/```html\s*\n([\s\S]*?)```/)?.[1]
  if (!html) throw new Error(`第 ${k} 版:回复里没有 html 代码块(结束原因 ${body.choices?.[0]?.finish_reason})`)
  fs.writeFileSync(path.join(out, `${TAG}-${k}.html`), html)
  console.log(`第 ${k} 版:${html.length} 字符,${Math.round((Date.now() - t) / 1000)} 秒,token ${JSON.stringify(body.usage)}`)
}

const results = await Promise.allSettled(Array.from({ length: N }, (_, k) => one(k + 1)))
for (const r of results) if (r.status === "rejected") console.log(r.reason.message)

const browser = await chromium.launch({ executablePath: CHROME })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
for (let k = 1; k <= N; k++) {
  const f = path.join(out, `${TAG}-${k}.html`)
  if (!fs.existsSync(f)) continue
  await page.goto(`file://${path.resolve(f)}`, { waitUntil: "load" })
  // 页面常给图片写 loading="lazy":改成立即加载,等每张图都加载完再截
  await page.evaluate(() => Promise.all([...document.images].map((i) => { i.loading = "eager"; return i.complete ? null : new Promise((r) => { i.onload = i.onerror = r }) })))
  // 也常有滚动到才淡入的内容(IntersectionObserver):一屏一屏滚到底再回顶,等动画走完
  await page.evaluate(async () => {
    for (let y = 0; y < document.documentElement.scrollHeight; y += 400) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)) }
    scrollTo(0, 0)
  })
  await page.waitForTimeout(1500)
  await page.screenshot({ path: path.join(out, `${TAG}-${k}.png`), fullPage: true })
  const h = await page.evaluate(() => document.documentElement.scrollHeight)
  console.log(`第 ${k} 版:截图 1440×${h}`)
}
await browser.close()
