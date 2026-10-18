// 给报告页面量几个和「后台面板 / 文章」有关的数,不靠肉眼:在 1440px 宽下打开每个 html,打印一行 JSON。
//
//   node ui-rl/scripts/page-style.mjs <html>...
//
// height    页面高度(px)
// prose     成段正文的字数占页面全部可见文字的比例:成段 = <p> 里至少 40 个字的那些(段落越多越像文章)
// cards     卡片个数:有边框(四边)、阴影或和外面不一样的背景色,宽 80–720px、高 40–480px、里面有字的框;
//           框里套框只算最外层
// bigNumbers 大号数字个数:字号 ≥ 28px、只有不超过 12 个字符且含数字的元素(指标方块的那个数)
// tables    <table> 个数;charts:宽过 120px 的 <svg> 和 <canvas> 个数;chars:可见文字总字数
import path from "node:path"
import { createRequire } from "node:module"

const files = process.argv.slice(2)
if (!files.length) throw new Error("usage: page-style.mjs <html>...")
const { chromium } = createRequire(import.meta.url)("../gen/node_modules/playwright-core")
const browser = await chromium.launch({ executablePath: process.env.CHROME ?? "/opt/pw-browsers/chromium" })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
for (const f of files) {
  await page.goto(`file://${path.resolve(f)}`, { waitUntil: "load" })
  await page.waitForTimeout(500)
  const m = await page.evaluate(() => {
    const visible = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0 }
    const text = (s) => s.replace(/\s+/g, "")
    const chars = text(document.body.innerText).length
    const prose = [...document.querySelectorAll("p")].filter(visible).map((p) => text(p.innerText).length).filter((n) => n >= 40).reduce((a, b) => a + b, 0)
    const bg = (el) => getComputedStyle(el).backgroundColor
    const transparent = (c) => c === "transparent" || /rgba\(.*,\s*0\)$/.test(c)
    // 元素外面看得见的背景色:往上找第一个不透明的
    const outerBg = (el) => { for (let e = el.parentElement; e; e = e.parentElement) if (!transparent(bg(e))) return bg(e); return "rgb(255, 255, 255)" }
    const boxed = (el) => {
      const s = getComputedStyle(el), r = el.getBoundingClientRect()
      if (r.width < 80 || r.width > 720 || r.height < 40 || r.height > 480 || !text(el.innerText ?? "").length) return false
      const border = ["Top", "Right", "Bottom", "Left"].every((d) => parseFloat(s[`border${d}Width`]) > 0 && s[`border${d}Style`] !== "none")
      return border || s.boxShadow !== "none" || (!transparent(s.backgroundColor) && s.backgroundColor !== outerBg(el))
    }
    const boxes = [...document.body.querySelectorAll("*")].filter((el) => visible(el) && boxed(el))
    const cards = boxes.filter((el) => !boxes.some((o) => o !== el && o.contains(el))).length
    const bigNumbers = [...document.body.querySelectorAll("*")].filter((el) => {
      if (!visible(el) || [...el.children].some((c) => text(c.innerText ?? "").length)) return false
      const t = text(el.innerText ?? "")
      return t.length > 0 && t.length <= 12 && /\d/.test(t) && parseFloat(getComputedStyle(el).fontSize) >= 28
    }).length
    const charts = [...document.querySelectorAll("svg, canvas")].filter((el) => visible(el) && el.getBoundingClientRect().width > 120).length
    return { height: document.documentElement.scrollHeight, prose: Math.round((prose / Math.max(chars, 1)) * 100) / 100, cards, bigNumbers, tables: document.querySelectorAll("table").length, charts, chars }
  })
  console.log(JSON.stringify({ file: f, ...m }))
}
await browser.close()
