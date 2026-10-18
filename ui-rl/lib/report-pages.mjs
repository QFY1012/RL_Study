// 让模型看报告页面的共用部分:页面照的请求、报告数据、整页截图切块,和不给评分标准时的判定提示词。
// scripts/contrast-rubric.mjs 和 scripts/rubric-set.mjs 用。
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
