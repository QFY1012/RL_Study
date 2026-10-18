// 控制变量:同一个 design 提示词,销售月报(sales.json)做成后台面板,Pudding 的口袋数据(pockets.json,pudding-data.mjs 转的)
// 更像文章。两份数据差好几处,这里每次只改一处,写出各个变体,再用 plain-report.mjs 分别生成,看页面往哪边变。
//
//   node ui-rl/scripts/data-ablation.mjs <sales.json> <pockets.json> <输出目录>
//
// 写出 <输出目录>/<变体>.json:
//   P0 口袋原样;P-zh 标题、说明、列说明译成中文(数据行不动);P-notitle 去掉标题;P-nodesc 去掉说明和列说明;
//   P-summary 原始数据行换成月报写法(算好的指标、分组表、各品牌表和一段结论,英文,标题不变)。
//   S0 销售月报原样;S-en 整份译成英文;S-thesis 标题换成一句论点;S-desc 加上 Pudding 那样的数据说明和每个字段的说明。
//   第二轮:P-genre 汇总版套上月报体裁;P-blocks 汇总版再加几块并列的表;S-single 销售只留华南退货一条主线。
//   第三轮:P-small 并列多块版去掉 20 个品牌的大表;S-bigtable 销售加一张 36 家门店的表。
//   第四轮:S-birds 销售月报的结构和数字不动,讲的东西换成城市鸟类观测。
//   第五轮:S-nodelta 去掉环比同比;S-noops 去掉趋势、问题、下一步;S-bare 两样都去掉;P-ops 口袋汇总版加上这几块。
//   第六轮:S-mix 是 S-bare 译成英文、标题换成论点、去掉公司和时间段(几处一起改)。
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
const pSummary = {
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
}
write("P-summary", pSummary)
// 第二轮:第一轮里口袋怎么改都还是一栏长文,销售怎么改都还是面板。剩下的差别是体裁和并列的块数
// P-genre 汇总版套上月报的体裁(标题、公司、时间段);P-blocks 汇总版再加几块并列的、和主线无关的表(按价位、面料、后口袋)
write("P-genre", { ...pSummary, title: "Denim Category Report, August 2018", company: "Northline Retail Research (fictional)", period: "2018-06-29 to 2018-08-06" })
const stretch = (r) => /spandex|elastane|lycra/i.test(r.fabric ?? "")
const bands = ["<$50", "$50 - $99", "$100 - $149", "$150+"], band = (p) => (p < 50 ? 0 : p < 100 ? 1 : p < 150 ? 2 : 3)
const pBlocks = {
  ...pSummary,
  priceBands: bands.map((b, i) => {
    const rows = pick((r) => band(r.price) === i)
    return { band: b, pairs: rows.length, womenFrontDepth: avg(rows.filter((r) => r.menWomen === "women"), "maxHeightFront"), menFrontDepth: avg(rows.filter((r) => r.menWomen === "men"), "maxHeightFront") }
  }),
  fabrics: ["women", "men"].map((g) => {
    const rows = pick((r) => r.menWomen === g)
    return { group: g, stretchShare: Math.round((rows.filter(stretch).length / rows.length) * 100) / 100, avgCotton: mean(rows.map((r) => Number((r.fabric ?? "").match(/(\d+)%\s*cotton/i)?.[1] ?? 0))) }
  }),
  backPockets: ["women", "men"].map((g) => {
    const rows = pick((r) => r.menWomen === g)
    return { group: g, depth: avg(rows, "maxHeightBack"), width: avg(rows, "maxWidthBack"), shallowestDepth: avg(rows, "minHeightBack") }
  }),
}
write("P-blocks", pBlocks)
// 第三轮:两轮下来页面类型都没翻,剩下的差别是有没有一张占主导的大表(口袋的 20 个品牌;销售全是 4–5 行的小表)
// P-small 并列多块版去掉 20 个品牌那张大表;S-bigtable 销售原样再加一张 36 家门店的表(虚构,数随种子固定)
const { brands: _, ...pSmall } = pBlocks
write("P-small", pSmall)
let seed = 7
const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
const cities = { 华东: ["上海", "杭州", "南京", "苏州", "宁波", "合肥", "无锡", "温州", "济南"], 华北: ["北京", "天津", "石家庄", "太原", "青岛", "郑州", "大连"], 华南: ["广州", "深圳", "东莞", "佛山", "南宁", "厦门", "福州"], 西南: ["成都", "重庆", "昆明", "贵阳", "绵阳"], 其他: ["武汉", "长沙", "西安", "沈阳", "哈尔滨", "兰州", "乌鲁木齐", "南昌"] }
const stores = sales.regions.flatMap((r) => {
  const list = cities[r.name], weights = list.map(() => 0.5 + rand()), total = weights.reduce((a, b) => a + b, 0)
  return list.map((city, i) => ({
    store: `${city}店`, region: r.name,
    sales: Math.round((r.sales * weights[i]) / total * 10) / 10,
    mom: Math.round((r.mom + (rand() - 0.5) * 0.12) * 1000) / 1000,
    returnRate: Math.round((r.returnRate + (rand() - 0.5) * 0.02) * 1000) / 1000,
  }))
})
write("S-bigtable", { ...sales, stores })
// 第五轮:拆销售的骨架。S-nodelta 去掉所有环比、同比(指标、地区、渠道里的 mom、yoy);S-noops 去掉 12 个月趋势、问题、
// 下一步;S-bare 两样都去掉。P-ops 反过来给口袋汇总版加上这几块:按周的测量进度、问题、下一步(虚构,和数据不矛盾)
const noDelta = ({ mom, yoy, ...rest }) => rest
write("S-nodelta", { ...sales, kpis: sales.kpis.map(noDelta), regions: sales.regions.map(noDelta), channels: sales.channels.map(noDelta) })
const { trend: _t, issues: _i, nextSteps: _n, ...salesNoOps } = sales
write("S-noops", salesNoOps)
write("S-bare", { ...salesNoOps, kpis: sales.kpis.map(noDelta), regions: sales.regions.map(noDelta), channels: sales.channels.map(noDelta) })
write("P-ops", {
  ...pSummary,
  trend: [["2018-06-25", 6], ["2018-07-02", 14], ["2018-07-09", 18], ["2018-07-16", 16], ["2018-07-23", 12], ["2018-07-30", 14]].map(([week, pairs]) => ({ week, pairsMeasured: pairs })),
  issues: [
    { title: "Some women's pockets are sewn shut", detail: "Several women's styles had front pockets sewn shut; another version of the same style with a real pocket was measured instead", owner: "Field team" },
    { title: "Waist size is below the US median for women", detail: "All pairs have a 32-inch waistband, smaller than the median women's waist in the US, so women's pockets in larger sizes may differ", owner: "Analysis" },
  ],
  nextSteps: [
    "Measure the same styles in two more sizes to check whether the gap holds",
    "Add the largest phone that fits each front pocket",
    "Repeat the study in 2019 with the same 20 brands",
  ],
})

// 第四轮:三轮改结构都没翻,剩下的是内容讲什么(经营指标 / 一项测量研究)。S-birds 销售月报的结构、数字、语言、
// 「月报」都不动,只把讲的东西换成城市鸟类观测:销售额→观测到的只数,地区→观测区,渠道→观测方式,商品→鸟种
write("S-birds", {
  title: "2026 年 9 月城市鸟类观测月报",
  company: "青禾观鸟会(虚构)",
  period: sales.period,
  summary: "9 月共观测到 1,284 只次鸟类,比 8 月多 8.6%,比去年 9 月多 21.3%,主要来自华东区的湿地样点和新记录到的「白腰杓鹬」。华南区连续两个月减少,受伤个体比例升到 6.1%,主要是撞上玻璃幕墙。本地留鸟占 38.2%,比 8 月低 1.4 个点,原因是秋季迁徙的候鸟增多。",
  kpis: [
    { label: "观测只次", value: 1284, unit: "只次", mom: 0.086, yoy: 0.213 },
    { label: "观测记录", value: 18420, unit: "条", mom: 0.052, yoy: 0.174 },
    { label: "每条记录平均只数", value: 697, unit: "‰", mom: 0.032, yoy: 0.033 },
    { label: "本地留鸟占比", value: 0.382, unit: "", mom: -0.014, yoy: 0.006 },
    { label: "受伤个体比例", value: 0.047, unit: "", mom: 0.004, yoy: -0.002 },
  ],
  trend: sales.trend.map((t) => ({ month: t.month, birds: t.sales })),
  regions: sales.regions.map((r) => ({ name: r.name, birds: r.sales, mom: r.mom, share: r.share, injuredRate: r.returnRate })),
  methods: [
    { name: "志愿者样线调查", birds: 512, mom: 0.118 },
    { name: "自动相机", birds: 341, mom: 0.064 },
    { name: "声纹记录仪", birds: 226, mom: 0.215 },
    { name: "公园定点观察", birds: 205, mom: -0.031 },
  ],
  topSpecies: [
    { name: "白腰杓鹬", group: "鸻鹬类", birds: 198, records: 1420, note: "8 月底首次记录,首月即第一" },
    { name: "白鹭", group: "鹭类", birds: 132, records: 1890, note: "" },
    { name: "红嘴鸥", group: "鸥类", birds: 121, records: 980, note: "中秋前后集中到达" },
    { name: "麻雀", group: "雀类", birds: 87, records: 4350, note: "" },
    { name: "珠颈斑鸠", group: "鸠鸽类", birds: 64, records: 2210, note: "华南受伤最多的鸟种" },
  ],
  issues: [
    { title: "华南区玻璃幕墙撞击导致受伤", detail: "华南区受伤个体中 62% 是撞上玻璃幕墙,集中在珠颈斑鸠和白鹭,与 8 月新建的两栋写字楼有关", owner: "保护组" },
    { title: "迁徙高峰拉低留鸟占比", detail: "中秋前后到达的候鸟占全月观测的 23%,其中留鸟只占 29%", owner: "数据组" },
  ],
  nextSteps: [
    "10 月起在华南区两栋写字楼的玻璃幕墙贴防撞贴纸,月底复盘受伤比例",
    "11 月候鸟高峰前优先安排白腰杓鹬和红嘴鸥的样点,控制每个样点的志愿者人数在 10 人以内",
    "声纹记录仪增长最快,10 月再加装两台",
  ],
})

write("S0", sales)
const en = {
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
}
write("S-en", en)
// S-single:只留一条主线(华南退货)的数据,别的块都去掉;标题、公司、时间段不变
write("S-single", {
  title: sales.title, company: sales.company, period: sales.period,
  summary: "华南区连续两个月下滑,9 月销售额 214 万元,环比 -5.8%,退货率升到 6.1%,是各地区最高,主要是物流破损。",
  regions: sales.regions, topProducts: sales.topProducts, issues: [sales.issues[0]], nextSteps: [sales.nextSteps[0]],
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
// 第六轮:S-bare 和 P-small 的骨架已经很像(一段结论 + 5 个指标 + 几张小表),一个还是面板、一个还是一栏。剩下的表面差别
// (语言、论点式标题、公司和时间段)单独改都没翻,这里一起改:S-mix 是 S-bare 译成英文、标题换成论点、去掉公司和时间段
write("S-mix", {
  title: "East China's online channels carried September; shipping damage in South China held it back",
  summary: en.summary,
  kpis: en.kpis.map(noDelta), regions: en.regions.map(noDelta), channels: en.channels.map(noDelta), topProducts: en.topProducts,
})

console.log(`写好 ${fs.readdirSync(out).length} 个变体:${fs.readdirSync(out).join(" ")}`)
