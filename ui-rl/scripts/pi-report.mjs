// 让 DeepSeek 在 pi agent 里写报告网页:提示词和 plain-report.mjs 的 design 一样(不给组件库、规范、示例),
// 只是多了工具:能渲染自己的页面、读截图(检查脚本 shoot-page.mjs,最多 --shoots 次),看能看图之后会不会做得不一样。
//
//   source ~/.config/ui-rl/judge.env && NODE_USE_ENV_PROXY=1 node ui-rl/scripts/pi-report.mjs <数据 json> <工作目录> [--shoots 6]
//
// 工作目录里放数据 json 和它的 image 字段引用的截图(从数据 json 所在目录拷过来),agent 写 page.html;数据也原样作为用户消息给它。
// 最后一次检查的 page.png、page-part-<i>.png 也在里面,还有 session.jsonl(整个会话)和 meta.json。
// 会话、工具、沙箱都是 gen/scripts/agent.mjs 的,模型按它的规则选(GEN_MODEL,默认 deepseek-v4.1-flash)。
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { execFileSync } from "node:child_process"
import { runAgent, SANDBOX } from "../gen/scripts/agent.mjs"

const [dataFile, wsArg] = process.argv.slice(2)
if (!dataFile || !wsArg) throw new Error("usage: pi-report.mjs <数据 json> <工作目录> [--shoots 6]")
const arg = (k, d) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : d)
const SHOOTS = Number(arg("shoots", 6))
const SHOOT = path.resolve(import.meta.dirname, "shoot-page.mjs")
const ws = path.resolve(wsArg)
const name = path.basename(dataFile)

// 工作目录:数据 json 和它引用的截图,别的都不放(别的模型的页面在数据目录里,不能让它看到)
fs.rmSync(ws, { recursive: true, force: true })
fs.mkdirSync(ws, { recursive: true })
const raw = fs.readFileSync(dataFile, "utf8")
fs.writeFileSync(path.join(ws, name), raw)
const images = [...raw.matchAll(/"image"\s*:\s*"([^"]+)"/g)].map((m) => m[1])
for (const img of new Set(images)) {
  fs.mkdirSync(path.dirname(path.join(ws, img)), { recursive: true })
  fs.copyFileSync(path.join(path.dirname(dataFile), img), path.join(ws, img))
}

// 前两句和 plain-report.mjs 的 design 提示词一字不差,用户消息也一样是 JSON 原文;只把「回复一个 html 代码块」换成写文件和怎么检查
const system = `Design a web page that presents the report described by the user, for a 1440px-wide desktop screen. The report's data is the JSON the user gives; its image fields are relative paths of screenshots, use them as they are.
Output one complete HTML file with its CSS inside; no external resources (no fonts or scripts from elsewhere; the screenshots are the only images).
Write the HTML file to page.html. To see how it renders, run \`node $SHOOT page.html\` with bash (at most ${SHOOTS} times): it writes a full-page screenshot page.png and the page cut into 1440x1600 slices page-part-<i>.png (view them with read), and prints the height, script errors, broken images, "undefined"/"NaN" in the text and horizontal overflow.`
const prompt = raw

const run = await runAgent({
  name: name.replace(/\.json$/, ""), ws, priv: path.join(os.tmpdir(), `pi-report-${path.basename(ws)}`), system, prompt,
  nudges: ["page.html 还没有写。现在把页面写进 page.html,再用 node $SHOOT page.html 检查。"],
  missing: () => !fs.existsSync(path.join(ws, "page.html")),
  maxShoots: SHOOTS, shoot: SHOOT, shootCommand: "node $SHOOT page.html",
})
// 最后一次改动之后不一定检查过:再截一次,截图和 meta 都是最终页面的
let final = null
if (fs.existsSync(path.join(ws, "page.html"))) final = JSON.parse(execFileSync(SANDBOX, [ws, "node $SHOOT page.html"], { env: { PATH: process.env.PATH, SHOOT }, encoding: "utf8" }))
fs.writeFileSync(path.join(ws, "meta.json"), JSON.stringify({ ...run, final }, null, 1))
console.log(`${name}: ${run.shoots} 次检查,${run.seconds} 秒,token ${JSON.stringify(run.usage)},结束 ${run.stop};最终 ${final ? `1440×${final.height},报错 ${final.scriptErrors.length},坏图 ${final.broken.length},undefined/NaN ${final.undefinedOrNaN},横向溢出 ${final.horizontalOverflow}` : "没有 page.html"}`)
