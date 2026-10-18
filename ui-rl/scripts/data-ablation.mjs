// 控制变量:同一个 design 提示词,销售月报(sales.json)做成后台面板,Pudding 的口袋数据(pockets.json,pudding-data.mjs 转的)
// 更像文章。两份数据差好几处,这里每次只改一处,写出各个变体,再用 plain-report.mjs 分别生成,看页面往哪边变。
//
//   node ui-rl/scripts/data-ablation.mjs <sales.json> <pockets.json> <输出目录>
//
// 写出 <输出目录>/<变体>.json:
//   P0 口袋原样;P-zh 标题、说明、列说明译成中文(数据行不动);P-notitle 去掉标题;P-nodesc 去掉说明和列说明;
//   P-summary 原始数据行换成月报写法(算好的指标、分组表、各品牌表和一段结论,英文,标题不变)。
//   S0 销售月报原样;S-en 整份译成英文;S-thesis 标题换成一句论点;S-desc 加上 Pudding 那样的数据说明和每个字段的说明。
import fs from "node:fs"
import path from "node:path"

const [salesFile, pocketsFile, out] = process.argv.slice(2)
if (!out) throw new Error("usage: data-ablation.mjs <sales.json> <pockets.json> <输出目录>")
fs.mkdirSync(out, { recursive: true })
const sales = JSON.parse(fs.readFileSync(salesFile, "utf8"))
const pockets = JSON.parse(fs.readFileSync(pocketsFile, "utf8"))
const write = (name, data) => fs.writeFileSync(path.join(out, `${name}.json`), JSON.stringify(data, null, 1))
const file = pockets.files[0]

write("P0", pockets)

const zhColumns = {
  brand: "品牌全名。",
  style: "每条牛仔裤的版型(分析时把直筒和微喇合为一类、紧身和修身合为一类,这里仍分开记)。",
  menWomen: "这条牛仔裤标的是男款还是女款。",
  name: "吊牌上写的具体款式名(例如 Fave Super Skinny Jean)。",
  brandSize: "量的尺码。每个品牌取最接近 32 英寸腰围的尺码(按品牌官网的说明)。",
  waistSize: "品牌官网上标的腰围(英寸)。",
  fabric: "吊牌上写的面料成分,逗号分隔(例如 78% cotton, 20% polyester, 2% spandex)。",
  price: "价格(美元),不带美元符号和多余的 0($39.50 记作 39.5)。",
  maxHeightFront: "前口袋的深度(厘米):从最高的铆钉顶端量到口袋最低点(靠拉链一侧)。",
  minHeightFront: "前口袋的深度(厘米):从最高的铆钉顶端量到口袋最低点(远离拉链一侧)。",
  rivetHeightFront: "最高的铆钉顶端到最低的铆钉之间的距离(厘米)。",
  maxWidthFront: "前口袋最宽处的宽度(厘米)。",
  minWidthFront: "从最高的铆钉到口袋远离拉链一侧的宽度(厘米)。",
  maxHeightBack: "后口袋最深处(通常在中间)到袋口的深度(厘米)。",
  minHeightBack: "后口袋最浅处到袋口的深度(厘米)。",
  maxWidthBack: "后口袋最上面(袋口)的宽度。",
  minWidthBack: "后口袋最窄处的宽度(在口袋收成尖角之前)。",
}
for (const c of file.columns) if (!zhColumns[c.name]) throw new Error(`没有 ${c.name} 的中文说明`)
write("P-zh", {
  title: "女装的口袋更差",
  files: [{
    file: file.file,
    about: "这是什么:美国最流行、最容易买到的几个品牌的 80 条蓝色牛仔裤的全部测量数据。来源:Jan Diehm 和 Amber Thomas 在纳什维尔、纽约和西雅图的实体店里手工量的。前口袋都量空裤子右手边的那个。每一行:一条牛仔裤。",
    columns: file.columns.map((c) => ({ name: c.name, description: zhColumns[c.name] })),
    rows: file.rows,
  }],
})

write("P-notitle", { files: pockets.files })
write("P-nodesc", { title: pockets.title, files: [{ file: file.file, rows: file.rows }] })

// 月报写法:和 sales.json 一样是算好的数和写好的结论,不给原始行
const mean = (xs) => Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10
const pick = (f) => file.rows.filter(f)
const avg = (rows, k) => mean(rows.map((r) => r[k]))
const women = pick((r) => r.menWomen === "women"), men = pick((r) => r.menWomen === "men")
const style = (r) => (/skinny|slim/i.test(r.style) ? "skinny" : "straight")
const depthW = avg(women, "maxHeightFront"), depthM = avg(men, "maxHeightFront")
const widthW = avg(women, "maxWidthFront"), widthM = avg(men, "maxWidthFront")
// 原始数据里同一品牌的写法不一("Guess " 带空格,"7 for All Mankind" 和 "7 for all Mankind"):按去空格、不分大小写合并
const key = (r) => r.brand.trim().toLowerCase()
const brands = [...new Map(file.rows.map((r) => [key(r), r.brand.trim()]))].map(([k, brand]) => {
  const w = women.filter((r) => key(r) === k), m = men.filter((r) => key(r) === k)
  return { brand, womenFrontDepth: avg(w, "maxHeightFront"), menFrontDepth: avg(m, "maxHeightFront"), gap: Math.round((avg(m, "maxHeightFront") - avg(w, "maxHeightFront")) * 10) / 10 }
}).sort((a, b) => b.gap - a.gap)
const deeper = brands.filter((b) => b.gap > 0).length
write("P-summary", {
  title: pockets.title,
  sample: `${file.rows.length} pairs of jeans from ${brands.length} brands, measured in stores in Nashville, New York and Seattle, June–August 2018`,
  summary: `Women's front pockets are ${depthW} cm deep on average, against ${depthM} cm for men's: ${Math.round((1 - depthW / depthM) * 100)}% shallower. They are also ${Math.round((1 - widthW / widthM) * 100)}% narrower (${widthW} cm against ${widthM} cm). In ${deeper} of ${brands.length} brands the men's front pocket is deeper. Back pockets are about the same size.`,
  kpis: [
    { label: "Women's front pocket depth", value: depthW, unit: "cm" },
    { label: "Men's front pocket depth", value: depthM, unit: "cm" },
    { label: "Women's front pocket width", value: widthW, unit: "cm" },
    { label: "Men's front pocket width", value: widthM, unit: "cm" },
    { label: "Brands where men's front pocket is deeper", value: deeper, unit: `of ${brands.length}` },
  ],
  groups: ["women", "men"].flatMap((g) => ["skinny", "straight"].map((s) => {
    const rows = pick((r) => r.menWomen === g && style(r) === s)
    return { group: `${g} - ${s}`, pairs: rows.length, frontDepth: avg(rows, "maxHeightFront"), frontWidth: avg(rows, "maxWidthFront"), backDepth: avg(rows, "maxHeightBack"), backWidth: avg(rows, "maxWidthBack"), price: avg(rows, "price") }
  })),
  brands,
})

write("S0", sales)
write("S-en", {
  title: "Monthly Sales Report, September 2026",
  company: "Qinghe Home (fictional)",
  period: "2026-09-01 to 2026-09-30",
  summary: "September sales were ¥12.84M, up 8.6% month on month and 21.3% year on year, driven mainly by online channels in East China and the new Cloud Sofa. South China declined for the second month in a row, and its return rate rose to 6.1%, mostly because of damage in shipping. Gross margin was 38.2%, 1.4 points below August, because of the Mid-Autumn promotion.",
  kpis: [
    { label: "Sales", value: 1284, unit: "¥10k", mom: 0.086, yoy: 0.213 },
    { label: "Orders", value: 18420, unit: "orders", mom: 0.052, yoy: 0.174 },
    { label: "Average order value", value: 697, unit: "¥", mom: 0.032, yoy: 0.033 },
    { label: "Gross margin", value: 0.382, unit: "", mom: -0.014, yoy: 0.006 },
    { label: "Return rate", value: 0.047, unit: "", mom: 0.004, yoy: -0.002 },
  ],
  trend: sales.trend,
  regions: sales.regions.map((r) => ({ ...r, name: { 华东: "East China", 华北: "North China", 华南: "South China", 西南: "Southwest China", 其他: "Other" }[r.name] })),
  channels: sales.channels.map((c) => ({ ...c, name: { 天猫旗舰店: "Tmall flagship store", 京东自营: "JD.com (direct)", 抖音直播: "Douyin livestream", 线下门店: "Offline stores" }[c.name] })),
  topProducts: [
    { name: "Cloud Sofa (3-seat)", category: "Sofas", sales: 198, units: 1420, note: "Launched at the end of August; first in its first month" },
    { name: "Solid Wood Dining Table 1.4m", category: "Dining tables", sales: 132, units: 1890, note: "" },
    { name: "Memory Foam Mattress 1.8m", category: "Mattresses", sales: 121, units: 980, note: "Driven by the Mid-Autumn discount" },
    { name: "Folding Storage Cabinet", category: "Storage", sales: 87, units: 4350, note: "" },
    { name: "Fabric Armchair", category: "Chairs", sales: 64, units: 2210, note: "Most returned item in South China" },
  ],
  issues: [
    { title: "Returns in South China from shipping damage", detail: "62% of returns in South China were damaged in shipping, mostly fabric armchairs and dining tables; this started with the carrier change in August", owner: "Supply chain" },
    { title: "Promotion lowered the margin", detail: "The Mid-Autumn ¥300-off-¥2000 deal brought 23% of orders, but those orders had a gross margin of only 29%", owner: "Marketing" },
  ],
  nextSteps: [
    "From October, large items in South China go back to the previous carrier; review the return rate at the end of the month",
    "For the Double 11 presale, lead with the Cloud Sofa and mattress bundle, and keep discounts within 10%",
    "Douyin livestream is growing fastest; add two brand livestreams in October",
  ],
})
write("S-thesis", { ...sales, title: "9 月的增长靠华东线上,华南的物流破损在拖后腿" })
write("S-desc", {
  ...sales,
  about: "这是什么:虚构的家居品牌青禾家居 2026 年 9 月的销售数据。来源:各渠道后台导出的订单,金额是含税成交额,已扣除退款;退货率按 9 月下单、截至 10 月 10 日退回的订单计。每个地区、渠道、商品各一行。",
  fields: {
    kpis: "全月汇总指标。value 是 9 月的值,mom 是和 8 月比的变化,yoy 是和去年 9 月比的变化;毛利率、退货率的 mom、yoy 是百分点差。",
    trend: "最近 12 个月每月的销售额(万元)。",
    regions: "按收货地址分的地区。sales 是销售额(万元),mom 是环比,share 是占全月销售额的比例,returnRate 是退货率。",
    channels: "按下单渠道分。sales 是销售额(万元),mom 是环比。",
    topProducts: "9 月销售额前五的商品。sales 是销售额(万元),units 是件数,note 是运营的备注。",
    issues: "本月发现的问题,owner 是负责的部门。",
    nextSteps: "10 月要做的事。",
  },
})
console.log(`写好 ${fs.readdirSync(out).length} 个变体:${fs.readdirSync(out).join(" ")}`)
