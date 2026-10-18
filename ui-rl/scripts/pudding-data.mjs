// 把 The Pudding 公开的一篇专题的数据(github.com/the-pudding/data 里的一个目录:CSV 和说明它们的 README)
// 转成一份报告数据 JSON,给 plain-report.mjs:看模型只拿到数据时把这篇做成什么样,和 Pudding 的原文比。
//
//   node ui-rl/scripts/pudding-data.mjs <the-pudding/data 里的目录> <输出 json> [--count <文件>:<列>]
//
// JSON 是 {title, files: [{file, about, columns: [{name, description}], rows}]}:title 是 README 第一行链接的文章标题,
// about 是 README 里这个文件的说明(What is this、来源和方法、每行是什么),columns 是 README 的列表,rows 是 CSV 的全部行。
// --count 把太大的文件按一列汇总成每个值的行数(rows 换成 [{<列>, count}]),比如生日效应的 6900 万字节、57 万行。
import fs from "node:fs"
import path from "node:path"

const [dir, out] = process.argv.slice(2)
if (!dir || !out) throw new Error("usage: pudding-data.mjs <the-pudding/data 里的目录> <输出 json> [--count <文件>:<列>]")
const arg = (k) => (process.argv.includes(`--${k}`) ? process.argv[process.argv.indexOf(`--${k}`) + 1] : null)
const [countFile, countColumn] = arg("count")?.split(":") ?? []

const readme = fs.readFileSync(path.join(dir, fs.readdirSync(dir).find((f) => /^readme\.md$/i.test(f))), "utf8")
const title = readme.match(/\[([^\]]+)\]\(https:\/\/pudding\.cool[^)]*\)/)?.[1] ?? readme.match(/for the story (.+?) published/)?.[1]
if (!title) throw new Error("README 里找不到文章标题")
// README 里每个文件一节(## <文件名>):节里的列表项是说明,表格是列
const sections = Object.fromEntries(readme.split(/^## /m).slice(1).map((s) => [s.split("\n")[0].trim(), s]))
const clean = (s) => s.replace(/<br\s*\/?>/g, " ").replace(/&bull;/g, "•").replace(/\*\*|`/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/\s+/g, " ").trim()
function describe(file) {
  const s = sections[file] ?? ""
  const about = s.split("\n").map((l) => l.match(/^\s*-\s+\*\*(What is this\?|Source\(s\)[^*]*|Observations \(Rows\))\*\*:?\s*(.*)/)).filter(Boolean).map((m) => `${clean(m[1])}: ${clean(m[2])}`)
  const columns = s.split("\n").filter((l) => /^\s*\|/.test(l)).map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
    .filter((c) => c.length >= 2 && !/^-+$/.test(c[0]) && clean(c[0]) !== "Header").map(([name, description]) => ({ name: clean(name), description: clean(description) }))
  return { about: about.join(" "), columns }
}

// CSV:逗号分隔,双引号括起的字段里可以有逗号和 "" 转义的引号;数字转成数,空字段是 null
function parse(text) {
  const rows = []
  let row = [], field = "", quoted = false, wasQuoted = false
  const push = () => { row.push(wasQuoted ? field : field === "" ? null : isNaN(Number(field)) ? field : Number(field)); field = ""; wasQuoted = false }
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++ } else if (c === '"') quoted = false
      else field += c
    } else if (c === '"') { quoted = true; wasQuoted = true }
    else if (c === ",") push()
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; push(); rows.push(row); row = [] }
    else field += c
  }
  if (field || row.length) { push(); rows.push(row) }
  const [head, ...body] = rows.filter((r) => r.length > 1 || r[0] !== null)
  return body.map((r) => Object.fromEntries(head.map((h, j) => [h, r[j] ?? null])))
}

const files = fs.readdirSync(dir).filter((f) => f.endsWith(".csv")).sort().map((file) => {
  let rows = parse(fs.readFileSync(path.join(dir, file), "utf8"))
  if (file === countFile) {
    const counts = new Map()
    for (const r of rows) counts.set(r[countColumn], (counts.get(r[countColumn]) ?? 0) + 1)
    rows = [...counts].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([v, count]) => ({ [countColumn]: v, count }))
  }
  return { file, ...describe(file), ...(file === countFile ? { note: `rows are counts of the original rows by ${countColumn}` } : {}), rows }
})
fs.writeFileSync(out, JSON.stringify({ title, files }, null, 1))
console.log(`${out}: ${title}; ${files.map((f) => `${f.file} ${f.rows.length} 行 ${f.columns.length} 列说明`).join(";")};${fs.statSync(out).size} 字节`)
