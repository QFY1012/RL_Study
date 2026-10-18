// 让模型看报告页面、判两版哪版好的共用部分:页面照的请求、报告数据、整页截图切块,判定提示词(不给标准、按一套主题加要点的标准),
// 和问到有 A 或 B 的赢家为止。scripts/contrast-rubric.mjs、rubric-set.mjs、judge-marks.mjs 用。
import fs from "node:fs"
import path from "node:path"
import { execFileSync } from "node:child_process"

const TILE = path.join(import.meta.dirname, "..", "scripts", "tile-shot.py")

// 页面是照这个请求做的(和 plain-report.mjs 的 design 提示词一字不差):editorial 版换过提示词,
// 但评分标准和判定都按同一个请求来,看的是「同一个请求下哪版做得好」
export const REQUEST = `Design a web page that presents the report described by the user, for a 1440px-wide desktop screen. The report's data is the JSON the user gives; its image fields are relative paths of screenshots, use them as they are.
Output one complete HTML file with its CSS inside; no external resources (no fonts or scripts from elsewhere; the screenshots are the only images).
Reply with the HTML inside one \`\`\`html fenced block and nothing else.`
export const request = (dataFile) => ({ type: "text", text: `<请求>\n${REQUEST}\n</请求>\n<报告数据>\n${fs.readFileSync(dataFile, "utf8")}\n</报告数据>` })

// 一版页面的整页截图切成 1440 高的块(缓存在 <prefix>-<k>.jpg),给「<label>:整页截图(1440px 宽),共 n 张,从上到下:」和这些图
export function shot(png, prefix, label) {
  if (!fs.existsSync(`${prefix}-1.jpg`)) execFileSync("python3", [TILE, png, prefix])
  const dir = path.dirname(prefix), base = path.basename(prefix)
  const files = fs.readdirSync(dir).filter((f) => f.startsWith(`${base}-`) && /^\d+\.jpg$/.test(f.slice(base.length + 1)))
    .sort((a, b) => parseInt(a.slice(base.length + 1)) - parseInt(b.slice(base.length + 1)))
  return [{ type: "text", text: `${label}:整页截图(1440px 宽),共 ${files.length} 张,从上到下:` },
    ...files.map((f) => ({ type: "image_url", image_url: { url: `data:image/jpeg;base64,${fs.readFileSync(path.join(dir, f)).toString("base64")}` } }))]
}

// 不给评分标准,直接问哪版好
export const NONE = `你是公正的评委。按给定的请求比较页面 A 和页面 B 哪版做得更好。先写两版的主要差别,再写理由,最后给结论。只能选一个。
只输出 JSON:{"diff":"两版的主要差别","reason":"理由","winner":"A 或 B"}`

// 按一套评分标准(rubric-set.mjs 合成的主题加要点)判
export const RUBRIC_JUDGE = `你是公正的评委。按给定的请求和评分标准,比较页面 A 和页面 B 哪版做得更好。
先逐条对照评分标准:这条上 A 好、B 好还是差不多,引用页面上的具体证据。再综合决定赢家:标准之间按对读者看清、看懂内容的影响大小取舍。只能选一个。A、B 的先后顺序是随意的,不要受它影响。
只输出 JSON:{"criteria":[{"no":"条目编号","better":"A 或 B 或 一样","why":"证据"}],"reason":"一到三句话","winner":"A 或 B"}`
export const listThemes = (themes) => themes.map((t, i) => `${i + 1}. ${t.name}\n${t.tips.map((x, j) => `   ${i + 1}.${j + 1} ${x}`).join("\n")}`).join("\n")
export const rubricBlock = (text) => ({ type: "text", text: `<评分标准>\n${text}\n</评分标准>` })

// 问一次判定。回复偶尔只在理由里写谁赢、没有 winner 这一项:没有 A 或 B 就重问(最多 3 次),不能当成选了哪边。
// ask(sys, content, label) 返回 lib/llm.mjs 的 call 的结果
export async function askWinner(ask, sys, content, label) {
  for (let t = 1; ; t++) {
    const res = await ask(sys, content, label)
    const winner = String(res.json.winner ?? "").trim().replace(/^页面\s*/, "")
    if (winner === "A" || winner === "B") return { winner, res }
    if (t === 3) throw new Error(`${label}:三次回复都没有 A 或 B 的 winner`)
    console.log(`  ↻ ${label}:回复里没有 A 或 B 的 winner,重问`)
  }
}
