# ui-rl

输出层强化学习环境的重建,计划见 `PLAN.md`。运行需要的组件库、截图检查和生成 Agent 都复制在 `gen/`(先在 `gen/` 里 `npm ci`),不依赖 ui-loop;ui-loop 原样保留作对照。全部是 mock 数据;密钥只走环境变量(`source judge.env`;judge.env 已被 .gitignore 排除,云端会话里放在 `~/.config/ui-rl/judge.env`)。

## 第 0 阶段:测基线

| 步骤 | 命令 | 状态 |
|---|---|---|
| 0.1 logprobs 探针 | `node scripts/probe-logprobs.mjs [--url ...] [--model ...]` | 已跑,见下 |
| 0.2 抽页面对 | `python3 scripts/build-pairs.py` | 已跑:84 对(候选 72、A/A 12),98 张页面图 |
| 0.3 盲标 | 标注页 `labels/label.html`(已发布为 artifact,标注存在它的 db 里) | 进行中 |
| 0.4 现在的 judge 重复判 | `JUDGE_MODEL=deepseek-v4.1-flash JUDGE_EFFORT=high node scripts/judge-repeat.mjs --rounds 5` | 等额度 |
| 0.5 对照打分 | `node scripts/eval-reward.mjs --run baseline-judge` | 脚本已写好,用假数据测过 |

- `labels/key.json` 是答案(每对的来源、哪边是候选),标完之前不要看。`labels/pages/` 由 `build-pairs.py` 从 `ui-loop/traces` 生成,不进仓库。
- 标注从标注页的 db 导出到 `labels/human.json`(Claude 用 ArtifactData 读 `labels` 集合),每条 `{pair, round: r1|r2, score: -2..2, reason}`,score 正数 = pairs.json 的右边更好。
- judge-repeat 先跑完第 1 轮的所有对再跑第 2 轮;额度中途用完,重跑同一命令续跑。

### 0.1 探针结论(2026-10-13)

- openone 的 `deepseek-v4.1-flash`:思考 / 不思考、流式 / 非流式四种都**不返回 logprobs**;`thinking: {type: "disabled"}` 也被忽略,照样思考。
- 不给 response_format 时,要求「只输出一个数字」,非流式两次都写了一段解释再给结论:正式判法要用 JSON 字段或固定的最后一行来取分数。
- DeepSeek 官方端点:现在的 key 是 openone 的,官方端点 401,没测成。
- 2026-10-13 按官方文档的参数再探一次(`logprobs: true, top_logprobs: 20`):openone 上能用的只有 `deepseek-v4.1-flash`、`deepseek-v4-flash-0731`、`deepseek-v4-pro-0813`(官方名 `deepseek-flash`、`deepseek-v4-pro` 报 model_not_found)。三个模型、思考 / 不思考、流式 / 非流式**都不返回 logprobs**,是中转站去掉了。`reasoning_effort: "none"` 能关掉两个 flash 的思考,pro 关不掉;`thinking: {type: "disabled"}` 都不起作用。
- 所以第 1 阶段的有刻度比较先用**采样近似**:同一请求采 k 次,用 1–9 的出现频率当分布;拿到支持 logprobs 的端点再换回概率期望。

## 第 1 阶段:比较 judge(2026-10-13)

全部在第 0 阶段的 84 对盲标上比(dev:候选 c1 c2 c3 c5 c8 c11 + flow-g0 的 A/A 对;test:其余)。judge 定义在 `lib/judges.mjs`,结果在 `runs/p1-*`,对比表在 `reports/phase1-judges*.md`。

| judge | 改了什么 | 结论 |
|---|---|---|
| rubric31(`baseline-judge`) | loop 原来的审美 judge | test 候选 1/6,和随机差不多 |
| func | loop 早期的需求 judge | test 候选 2/6 |
| ia、ia31 | 从人工理由整理的 6 条(+ rubric31 视觉 7 条) | test 候选 4/6,明显好于 rubric31 |
| ia2、ia2s | 加两条取舍规则(补丁);ia2s 换成按节对齐的输入 | 规则对 c3、c5 有效但是补丁,删掉后(ia3s)退回 ia31 的水平 |
| ia2p、ia2g | 同一节左右拼图;1–9 分采 3 次 | 拼图更易受顺序影响,放弃;采样对「差不多」有用但贵 3 倍,放弃 |
| ia4s、ia4v | 只留人工理由里有依据的 5 条(删掉「简练」);ia4v 再加 rubric31 视觉细节作平局参考 | 各跑两轮:候选 10/11 和人工一致(只错 c4),两轮判出的方向 100% 一致 |
| **ia5** | **定下来的版本**:信息组织 4 条 + 视觉一节(「指标一行排满」并进「同类组件一致」) | 只是 ia4v 调了结构,没有单独重跑 |

几点经验:

- 只跑一轮时,同一个 judge 自己就会有一两个候选的结论变掉;各版本间「差一个候选」在这个波动以内。比较版本至少各跑两轮。
- 「简练」是整理标准时加进去的,人工理由里一次也没出现,却是 judge 用得最多的一条,是 c3 判错的原因。改标准时只留理由里有依据的条目(按候选数算,同一候选的重复理由只算一次),不针对个别判错的对加规则。
- 按节对齐的输入比整页切块省约 40% 的输入;openone 不返回 logprobs(见上),有刻度的比较只能靠采样。
- c4 四个版本都判反:人工更看重「结论和指标合并」,judge 更看重「背景信息不和建议混在一起」。c4 在 test 里,记作已知分歧,没有据此改标准。
- 并发 32 时开头会有少量「60 秒没有开始回复」的重试,之后正常;84 对一轮约 5 分钟。

### 人工重标(暂缓,留作以后)

- 标注页上的「重标 · 21 对」:每 4 对取 1 对,左右对调、顺序倒过来显示,存的时候换算回 pairs.json 的左右。
- 用途:算人工前后两次的一致率,作 judge 一致率的上限参考。如果人工自己也只有八成左右一致,test 上 75–78% 就不算差。
- 和第一次标注隔得不久(PLAN 原定一周后),可能记得上次的选择,一致率会偏高。

### 可优化项目

- **第 2 层量化指标**(PLAN 3.2):留白、对齐、间距刻度、字号级数、一行没排满等,从渲染后的 DOM 直接量,不花 API 费用;每项在 84 对上看和人工方向是否一致,一致的才用。现在没做,第 1 阶段只用第 3 层 judge(ia5)。
- **验收没全达标**:test 上和人工一致 75–78%,低于 PLAN 的 85%(主要是 c4);决定先接受,进第 2 阶段。

## 第 2 阶段:报告数据(2026-10-13)

- `node data/gen-data.mjs`:复制原有 f1–f6(f6 的摘要「6 到 9 步」改成「5 到 9 步」,云途第 6 步补上 P6 的备注),按规格新写 f7–f24。模型写原始内容,`lib/features.mjs` 的 check 校验(编号、问题和建议的指向、阶段对比的列、摘要里的步数、虚构产品名、规格),不通过把问题发回去改,最多 2 次;程序补齐指标、产品汇总、截图路径,再画截图。
- 规格让会影响排版的数据特征拉开:产品 2–5 个,每个产品 3–15 步,有备注的步骤 14%–94%(原有 6 份都在 33%–56%),问题 1–8 个,阶段对比和共性做法有的有、有的没有,摘要 72–217 字。小 4 份、中 10 份、大 4 份。
- 划分(`data/split.json`):训练 f1–f12,验证 f13–f18,测试 f19–f24;试点训练 f1–f4 + f7–f10,试点验证 f13–f16。
- 概览和抽查的 5 份:`reports/phase2-data.md`。
- 程序查不出的小出入还有(例如证据里的填写项数和那一屏的 inputs 差 1),不影响排版,没有再加校验。

## 生成 Agent(`gen/`,2026-10-13)

从 ui-loop 复制过来(组件库、`shoot.mjs`、`generate.mjs`、`agent.mjs`、`sandbox.sh`、规范、组件说明、g0),依赖版本和 ui-loop 完全一样。复制后拿 `ui-loop/traces/flow-g0/f1` 核对过:新旧两边 `shoot.mjs` 的检查结果、整页截图、缩略图、10 张切块逐字节相同;按节截图和 `cache/sections` 里的也相同;judge 的 13 个提示词复制前后 sha1 相同。

试跑第 1 步时 6 版里有一版 20 分钟没写完、两版中途报错。查日志找到的原因,改了 `gen/scripts/agent.mjs` 两处:

- **等模型开始回复的时限 10 秒 → 60 秒**(主要原因)。v2、v6 一共 12 次「Request timed out」,全部发生在会话里已经有 9 张以上截图之后:图多了,中转站常常 10 秒以上才开始回复,10 秒就被当成超时重发,每次白等 30 多秒;v2 连续 4 次后会话中断。judge 的 `call()` 早就是 60 秒。
- **沙箱里只能用 node 运行检查脚本**。v3 把截图看错了,以为页面上多了一行字,之后几分钟自己写脚本渲染、截图去查,绕过了「最多检查 5 次」。现在 bash 里用 node / npx / npm / python 运行别的东西会被拦下,提示用 `node $SHOOT .` 检查、用 read 看截图;grep、cat、ls 照常能用(包括读组件源码)。

`scripts/rollout.mjs` 的 20 分钟上限保留,只当兜底。


### 网格组件库(2026-10-16 起是 `gen/app` 的唯一组件库)

所有组件和生成的报告都必须用网格:每一块的左右边落在 12 列的栏线上,每一节从场线开始。原来放在 `gen/next/` 的网格版组件、`design.md`、`components.md` 已经换进 `gen/app` 和 `gen/`,旧的 `render.tsx` 删掉;`shoot.mjs` 每次都跑网格检查,不在栏线上的块记为「网格」问题,和其他程序检查一样是硬约束。试点(`runs/pilot`)是用旧组件库跑的,和之后的结果不能直接比。下面两小节是这套组件库的来历。

#### 组件库整理

原来 `app/src/components/report/` 是 ui-loop 一路改过来的两层:`index.tsx` 里的 `Stat`、`DataTable`、`List`、`KV`、图表、`Text` 只是一行转发,真正的实现都在 706 行的 `render.tsx` 的一个大 switch 里,还夹着用不到的老代码(另一套 page/section 框架、card、alert、badges)。生成 Agent 想查一个组件怎么画,得先发现这层转发,再去大文件里找分支。

`gen/next/report/` 按 shadcn 的写法重写:一个组件一个文件(`stat.tsx`、`data-table.tsx`、`list.tsx`、`kv.tsx`、`chart.tsx`、`progress-list.tsx`、`text.tsx`、`figure.tsx`、`layout.tsx`),`index.tsx` 只做导出。组件名、属性、类名一字不改;去掉了用不到的分支和只用来追踪 spec 的 `data-type` 属性。`List` 里写明了 `meta` 在各模式下显示在哪。

核对(当时在 `gen/next/` 做,脚本已随替换删掉,见 git 历史):选的 21 页覆盖现有 263 个不同页面里用到的全部 108 种组件和属性写法,外加试点第 1 步的 6 版;新旧两套各渲染一次,检查结果、整页截图、缩略图、每张切块全部逐字节相同。


#### 网格内放开

原则:网格里怎么填都可以,但每一块的左右边都要落在 12 列的栏线上。

- 组件:所有内容组件和 `Figure` 多了 `start`(从第几列开始)和 `rowSpan`(竖着跨几行),`Block` 多了 `start`、`rowSpan`;所有组件还都有 `rowStart`(从第几行开始,`fields` 网格里一行是一场)(竖着跨几行统一叫 `rowSpan`,最多 12;`Block` 的旧写法 `rows` 还能用,说明里只写 `rowSpan`);`Section` 多了 `layout="stack"`(标题在上、内容占满 12 列);`Grid` 不写 `cols` 时按自己有几列宽来分(`side` 节里 9、`stack` 节里 12、写了 `span` 就是 `span`),所以里面的东西天然落在栏线上。不写新 props 的旧页面渲染结果不变(21 页逐字节核对过,`SHOOT_GRID=0`)。
- 检查:`gen/scripts/grid-check.mjs`,`shoot.mjs` 每次截图后调用,量每一块的左右边,不在栏线上就报「网格」问题。拿第 1 遍观察的 16 版页面试:带清单的 3 版为了「四项一行」在 9 列宽里写了 `Grid cols={12}`,4 个指标全不在栏线上;g0 有 2 版两列的 `List` 不在栏线上。ia5 都没看出来。要看检查量了什么:`SHOOT_OVERLAY=1 node gen/scripts/shoot.mjs <工作区>` 多写一张 `grid.png`,淡红是 12 列、淡蓝是场,量过的块在栏线上画绿色虚线框、不在画红框并标上问题编号,每节上边的短线在场线上是蓝色、不在是红色。
- 场(纵向):`Section` 渲染后把高度补到整数个场(一场 144px,场间距 24px,场线相隔 168px),节与节之间本来就空一个场(192px),所以每一节都从场线开始;节里面不限。网格检查也量每一节的上边在不在场线上。代价是每节底部多出不到一场的空白(f15 那页总高从 5304px 变成 5832px)。这一条会改变所有页面的渲染,不再和旧组件库逐字节一致。
- 规范和组件说明:`gen/design.md`(在 `design-b2b9.md` 基础上加 A6 网格,B 改成默认排法,C2 加 `stack`,C4 改成自由组合;B9 的 2 条改用单列,因为 9 列分不成两半)、`gen/components.md`。手工全部对齐的示例在 `gen/examples/f15-grid/`;它的 `baseline.diff`(让表格、列表等的行也落在 24px 基线上)没有并进组件库。
- 2026-10-17 删掉了 `Section` 的 `layout="stack"`:节标题一律在左侧 3 列、内容在右侧 9 列,整页的节标题排成一条竖线。从零生成的页面用 `stack` 把截图和宽表格铺满 12 列,标题跑到上面,竖线就断了。
- 2026-10-17 节高取整改成「超过不到半场按没超过算」:内容伸进最后一个场不到 72px 时,节按前面的场数算,多出的部分伸进下面的空白(节间仍剩一半以上);超过半场才补满。f15 示例页从 5832px 变成 5496px,从零生成的那页从 7680px 变成 6840px,检查都通过。
- 2026-10-17 去掉了所有旧版兼容:`Block` 的旧参数 `rows`(用 `rowSpan`)、`shoot.mjs` 按组件库里有没有 `grid.ts` 决定量不量网格的判断和 `SHOOT_GRID=0` 开关(现在每次都量)。`report/grid.ts` 改名 `placement.ts`(各组件共用的 `span`、`start` 等放置参数,不是组件),不再认旧名。上面记录里提到的 `rows` 旧写法、`SHOOT_GRID=0` 都已不能用。

## 框选标注(2026-10-16)

参照 Wu et al., *Improving User Interface Generation Models from Designer Feedback*(CHI '26):设计师直接两两排序的数据和别人的判断几乎对不上(49%),在页面上圈出问题、写一句怎么改,再把「改后 vs 改前」做成偏好对,一致率高得多(草图 64%、直接修改 76%)。这里试同样的做法。

| 步骤 | 命令 | 状态 |
|---|---|---|
| 挑页面、重新渲染 | `node scripts/critique-pages.mjs`(先在 `gen/` 里 `npm ci`) | 已跑:pilot 13 步 × 最高、中间、最低各 1 版 = 39 页;重新渲染的缩略图和训练时逐字节相同 |
| 圈问题 | 标注页 `labels/critique.html`(已发布为 artifact,标注存在它的 db 里) | 进行中 |
| 按意见改页面 | `source judge.env && node scripts/revise.mjs --critiques labels/critiques.json` | 用一条测试意见跑通过一页(47 秒,改了 1 行),测试产物已删 |
| 看改后 | 同一个标注页的「看改后」 | 等改完 |

- 标注页上点一下组件就选中它(悬停时虚线框标出鼠标下最里层的组件,「大一层」换成外面那层),也可以拖框圈住任意区域;每处写一句怎么改。每页记用时(只在页面可见时计)。
- 组件的位置由 `critique-pages.mjs` 从渲染后的 DOM 量出(带 `data-slot` 的元素),存在 `labels/critique-pages/<页面>.json`;点选记 `pick: "dom"`,拖框记 `pick: "box"`,拖框按 IoU 对应到组件。
- `labels/critique-key.json` 是每页来自哪一步、哪一版、分数;标注页不发布它。
- 标注从 db 导出到 `labels/critiques.json`(Claude 用 ArtifactData 读 `critiques` 集合),每条 `{page, items:[{x,y,w,h,comment,hit,pick}], note, fine, seconds}`;看改后的结论在 `reviews` 集合。
- `revise.mjs` 在缩略图上画出框和编号(`marked.png`),用 `generate.mjs` 的 `--base` 加 change kind `critique` 让生成 Agent 在原页面上改(用这页当时那一步的输出指南);改后的页面在 `runs/critique/revised/<页面>/<报告>/`。
- 要回答的问题:每页标注花多久;改后的页面你认不认可(「看改后」里逐条记改到了 / 没改到 / 改坏了)。认可的改后页面和改前页面组成偏好对,给 reward / DPO 用。

## 只给数据让模型写报告(2026-10-18)

起因:让 DeepSeek 只凭网站名和一句描述写首页,结果很像样;同一个模型拿报告数据写报告页,却很难看。两边都是 HTML、都是排版,差距为什么这么大?这一轮就查这个。网站一边的实验见 `data-collection/README.md`「不给风格的生成」。

脚本 `scripts/plain-report.mjs`:不给组件库、设计规范、网格和示例,系统提示只说把数据做成网页,用户消息就是 JSON 原文。截图先用 `data/draw.mjs` 的 `phone()` 画进输出目录,页面在 1440px 宽下截整页图。截图前做了三件事:懒加载的图片改成立即加载并等它加载完;一屏屏滚到底,让滚动才淡入的内容显示出来;记下脚本报错和页面里出现的 `undefined`。

```sh
source ~/.config/ui-rl/judge.env && NODE_USE_ENV_PROXY=1 node ui-rl/scripts/plain-report.mjs <数据 json> <输出目录> --n 2 --tag plain
# 官方端点:JUDGE_URL=https://api.deepseek.com/chat/completions GEN_MODEL=deepseek-flash,key 换成官方的
... --n 1 --tag flash                     # 提示词 data(默认):三句中文
... --n 1 --tag design --prompt design    # 提示词 design:照 plain-site.mjs 写首页的那段话改成报告
```

Opus 对照不走脚本:子 agent 拿同一段 data 提示词和同一份 JSON,一次写完一个文件,不检查、不修改。

### 数据

| 报告 | 来源 | 结构 |
|---|---|---|
| f15、f7、f13 | 现有的流程挖掘报告(`data/flow/` 的 json 不进 git,在 Drive 文件夹 id `1s_PHlUtuNSJYAADMsdb-x5Q5EI1Z5u3B`) | 多个产品 × 多个步骤,每步一张高手机截图,问题和建议引用具体的产品和步骤 |
| sales(销售月报)、survey(满意度调研)、abtest(A/B 实验)、features(竞品功能矩阵) | 现编的,各 3–4KB | 常见的报告模板:KPI 卡、趋势、分组表、矩阵、结论和建议 |

f15 的 JSON 约 1,950 字(其中汉字 1,653),提示词 3,428 token,不算长。

### 结果

每份数据出 5 版:中转端点 deepseek-v4.1-flash 两版(plain-1、plain-2),官方 deepseek-flash 一版(flash-1),Opus 一版(opus-1),官方 deepseek-flash 用 design 提示词一版(design-1)。页面高度(px):

| 报告 | plain-1 | plain-2 | flash-1 | opus-1 | design-1 |
|---|---|---|---|---|---|
| f15 | 4963 | 3485 | 978 | 4319 | 8873 |
| f7 | 3861 | 2461 | 2871 | 2665 | 2884 |
| f13 | 3421 | 3596 | 3407 | 2591 | 3544 |
| sales | 2118 | 2405 | 2441 | 2170 | 2084 |
| survey | 2728 | 3066 | 2629 | 2584 | 2529 |
| abtest | 2059 | 2330 | 2178 | 2229 | 2124 |
| features | 3000 | 2332 | 2883 | 2941 | 2570 |

- **模板类(sales、survey、abtest、features):每个模型、每版都像样。** 有 KPI 卡、折线图、条形图、矩阵、结论和建议,层次清楚,和常见的 dashboard 或实验报告没有区别。
- **流程报告(f7、f13、f15):每个 DeepSeek 版本都难看,而且难看的方式一样。**
  - 每步一行,左边一张截图,右边几行字,大片空白。
  - 其他产品藏在 tab 后面,截图里看不到产品之间的对比。
  - 宽内容横向溢出。
  - 版面按 JSON 的字段顺序从上往下排,问题和建议与它们说的步骤离得很远。
  - design 提示词把脚本去掉了(7 页都没有 `<script>`,没有报错,内容全部可见),风格变成杂志式排版;但流程的组织方式没变,f15 拉到 8,873px 高。
- **Opus 会自己发明结构:** 把各产品的同一步排成一张对齐表,问题链接到它说的步骤。但一次写成,也有 bug:survey 页上出现 19 个 `undefined`(字段名写错)。
- 一次写成的 bug,DeepSeek 也有:官方 flash 的 f15 报 `Cannot set properties of null`,页面只剩 978px;f7 的问题和建议两节是空的,原因没查清,可能和截图方式有关。中转端点的 abtest 有一次回复在约 2.77 万 completion token 处断了,没有结束的代码块,重跑就好了。
- 提示词里要「精美」(`--prompt polished`)或「featured report」(`--prompt featured`),其余和 design 一样:官方 flash 各 1 版时,精美版的 f15 明显更紧凑(5,973px 对 8,873px),思考 token 7 份报告都多 1.5–2.7 倍。但换成中转端点,3 份流程报告 × 3 种提示词 × 各 3 版(27 页,都没有脚本、没有报错)再看,同一提示词几版之间的差别比提示词之间的差别还大(f15 design 三版 4,015–6,105px,polished 5,200–6,617px),回复长了 0–30%,页面并没有更好。所以官方那一版的改进是抽样运气,不是形容词的作用。27 页的排法几乎一样:产品卡 → 每个产品一行横排步骤截图 → 有时一张对比表 → 问题卡 → 建议卡,即 JSON 的顺序;没有一版像 Opus 那样把各产品同一步对齐、把问题放到它说的步骤旁边。视觉上都整齐,差在信息组织。对比图 `compare/<报告>-prompts.jpg`(行是提示词,列是版本),官方 key 跑的那部分在各目录的 `official-b/`。
- 对比图:`compare/<报告>.jpg` 是中转两版,`<报告>-3.jpg` 是中转、官方 flash、Opus 三版并排,`<报告>-design.jpg` 是 data 和 design 两种提示词的对比。

### 结论

- 模型的「审美」主要是**模板记忆**,不能泛化到没见过的信息结构。分界线不是「网页 vs 报告」,也不是「内容自己编 vs 内容固定」。后一条被网站一边的 `--text` 实验否定了:首页的文字一字不改地交给模型,页面照样好看。真正的分界线是**结构熟不熟**。
  - 见过的结构:落地页,还有销售、调研、A/B、功能矩阵这类模板报告。模型照着记忆里的样子排,排得好。
  - 没见过的结构:流程报告,多产品 × 多步骤 × 高截图 × 交叉引用。模型没有可抄的样子,就退回按字段顺序堆。
- 所以值得训练的是**结构化数据的信息设计**(怎么让多产品可比、让问题挨着证据、让截图排得紧凑),不是视觉风格。视觉风格模型已经会了。
- 这一点也说明网站数据对(真网站 vs AI 重写一节)教不了要学的东西:网站是模型最熟的结构。
- 局限:每种只有 1–2 版,好不好看是 Claude 看图判断的,还要你盲评确认。下一步见 `PLAN.md` 第 9 节。

### 数据位置

- 现编的 4 份 JSON 在 Drive 文件夹 `ui-rl-report-plain-2026-10-18`(id `1cOo8wWYSb5DgUiy4Rh7MuwNAcfF3rGCw`),各放进 `<输出目录>/<名字>/<名字>.json` 就能重跑;它们没有截图,不用画图。f7、f13、f15 用 `data/flow/` 的数据(Drive 位置见上表),截图用 `draw.mjs` 重画。
- 生成的页面、截图、请求和回复(共 21MB)只在跑实验的容器里(`/home/user/ui-rl-scratch/report-plain/`),没有上传到 Drive:Drive 的工具只能内联上传,传不了这么多文件。容器回收后就没了;要留的话,在本地按上面的命令重跑。
