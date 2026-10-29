# report-gepa

用 GEPA 优化写报告页面的提示词。计划见 `PLAN.md`。和仓库里其他目录无关,从头写。

## 环境

```sh
python3 -m venv .venv
.venv/bin/pip install gepa==0.1.4 openai==3.35.1 playwright==1.64.0 pillow==13.0.0 ftfy==6.3.1 pandas==3.0.5
```

浏览器用容器里预装的 Chromium(`/opt/pw-browsers/chromium`),不跑 `playwright install`。

密钥和端点放在 `~/.config/report-gepa/llm.env`(权限 600,不进仓库):

```
LLM_API_KEY=...
LLM_BASE_URL=https://openoneapi.com/v1
LLM_MODEL=deepseek-v4.1-flash
```

同名的环境变量会覆盖文件里的值。

## 模拟报告数据(`src/report_gepa/datagen.py`、`domains.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.datagen data/reports --per-kind 3 --workers 8 | tee runs/datagen.log
```

- `domains.py` 列了 24 类数据:销售月报、电商漏斗、产品指标周报、城市气象月报、部门预算执行、A/B 实验、满意度调研、客服工单、物流时效、园区用电、门店运营、招聘、考试分析、服务可用性、广告投放、多款 App 流程对比、项目进度、竞品功能对比、库存周转;另 5 类只进测试集:多城市气候对比、医院门诊、地铁客流、农场种植、楼盘销售。每类只写「真实系统导出的数据里有什么」,不写页面该怎么排。
- 每份随机抽规模(小、中、大)和有没有结论文字,`glm-5.3-flash` 按真实系统导出的样子编 JSON,结构不套固定模板。程序检查大小是否符合规模、有没有对象数组、数值够不够、有没有占位符、是不是中文,不通过就把问题发回去重写,最多 2 次。
- 输出:`data/reports/<类>/<id>.json`;`manifest.jsonl` 记每份的抽样参数、重写次数和结构特征(层数、数值个数、数组个数、最长数组、日期个数、长文本个数);`split.json` 是划分,测试类全进测试集,其余每类 1 份进验证、其余进训练。
- 只查结构,不查业务上的细节:试生成时一份 7 月的气象数据只有 30 天,这种不影响排版的出入没有再加检查。
- 已生成的文件会跳过,中途断了重跑同一命令即可。
- 第一版不带图片,流程对比类的截图只有文字描述。

## 明细 mock 数据(`src/report_gepa/rawgen.py`)

给 benchmark 用:和 Pudding 一样,每题一个 CSV,一行一条业务记录(一次就诊、一个订单、一张工单……),要参赛的 agent 自己统计、找规律。

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.rawgen data/mock --per-kind 2 --workers 8 | tee runs/rawgen.log
```

- 类别同 `domains.py` 的 24 类,每类一行是什么写在 `rawgen.RECORDS`。规模按行数抽:小 300–3000、中 3000–3 万、大 3 万–30 万。
- `glm-5.3-flash` 写一个只用标准库的 `gen.py`:`gen` 写出 CSV,`check` 只从 CSV 读回来,对埋的 3–5 条规律重新算数并判断是否成立。规律要来自这个业务自己的机制,不许用周几效应这类通用套路(第一版原型两份都埋了「周一高峰」后加的要求)。
- 程序检查:能跑、行数符合规模、列名 snake_case、文本是中文、有缺失值、没有占位符、每条规律 `holds` 为真;不通过把问题发回去重写,最多 2 次。
- 输出 `data/mock/<id>/{data.csv, gen.py, findings.json}`;`findings.json` 是从写好的 CSV 算出来的,作为「页面有没有找到规律」的答案。`manifest.jsonl` 记规模、种子、每次尝试的问题和 CSV 的形状。
- 2026-10-21 跑了 48 份(24 类 × 2):26 份一次通过、15 份重写一次、7 份两次;6 份因中转站 524 超时或规律不成立失败,重跑两轮补齐。文件 89 KB–29.5 MB,中位数 0.9 MB,共 150 MB;规律共 208 条。
- 已生成的(有 `findings.json`)会跳过,失败的重跑同一命令即可。

## 生成页面(`agent/gen.mjs`、`src/report_gepa/generate.py`)

页面由 pi agent(`@mariozechner/pi-coding-agent` 0.73.1)写。先装一次:

```sh
cd agent && npm ci
```

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.generate <out_dir> <数据文件或目录>... [--guide guides/seed.md] [--model deepseek-v4.1-flash] [--n 2]
```

- 系统提示词是指南(GEPA 优化的对象,默认 `guides/seed.md`,一句话)。用户消息是 `agent/gen.mjs` 里固定的任务说明:数据在 `data/`、页面写到 `index.html`、不引用外部资源、环境里没有浏览器。数据不放进提示词,agent 用工具自己读。
- 工具:读、写、改文件只限工作目录;shell 命令在 `agent/sandbox.sh` 里跑(新的挂载、网络、进程命名空间,只看得到工作目录和只读的 `/usr`、node;没有网络,环境变量里没有密钥)。
- 每一版在 `<out_dir>/<名字>/`:`index.html`、截图 `page.png`、记录 `record.json`(每次 agent 运行的步数、token、耗时,渲染结果)、agent 全程记录 `session.jsonl`。拷进去的数据跑完就删。
- 没写出 `index.html`、HTML 没闭合、标签写成了文字(`< div`)算没交付,整轮重来,最多 2 轮。
- 每步输出上限 65536 token(pi 默认 32000,glm 不指定时停在 8192)。

2026-10-19 用一份 Pudding 风格的指南(已删)在一份 A/B 实验数据上试过:7.4 分钟、39 步、输入 37.7 万 token、输出 6.2 万 token,页面 7,635px,五张不同的图,数字是 agent 用 python 从数据里算的。那一次 agent 花了很多步在沙盒里找浏览器想自查,之后在任务说明里写明了没有。

## 批量生成页面(`src/report_gepa/pagegen.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.pagegen data/reports runs/pages --workers 6 --renders 3 | tee runs/pagegen.log
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.pagegen data/pudding runs/pudding-pages --workers 5 --renders 3 | tee runs/pudding-pages.log
```

`--pages seed-ds-1,detail-ds-1` 只生成列出的页面。

每 30 秒读一次数据目录的 `manifest.jsonl`(每行的 `data` 是数据相对数据目录的路径),新的数据立刻排队;`split.json` 出现且排队的页面全部完成后退出。中转返回「预扣费额度失败」(余额不够)时整批立即停下,那一页不留记录,充值后重跑同一命令即可。已有 `record.json` 的页面跳过,断了重跑即可。`--renders` 限制同时打开的浏览器数。

每份数据 4 个页面,来源不同,让标注时好坏的差别不只来自抽样波动:

| 名字 | 指南 | 模型 | 个数 |
|---|---|---|---|
| `seed-ds-1`、`seed-ds-2` | `guides/seed.md`(一句话) | deepseek-v4.1-flash | 2,也是 GEPA 的参照页面 |
| `seed-glm-1` | `guides/seed.md` | glm-5.3-flash | 1 |
| `detail-ds-1` | `guides/detailed.md` | deepseek-v4.1-flash | 1 |

`guides/detailed.md` 是让 deepseek-v4.1-flash 自己写的通用详细指南,代表「认真写过提示词」的水平。人工标注里的「指南版」(`pudding-ds-1`)是 2026-10-20 用一份 Pudding 风格的指南生成的;那份指南禁止滚动叙事、每节一张图,和 rubric 2.6 视图连贯相反,已经删掉,标注过的页面作为数据留在 Drive。`guides/editorial.md` 是杂志专题风格,只试过,没进批量。

## 修脚本报错的页面(`src/report_gepa/repair.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.repair runs/pudding-pages runs/pages --workers 4 | tee runs/repair.log
```

渲染时记录到脚本报错(运行时异常或语法错误)的页面,交给 deepseek-v4.1-flash 的 agent 在原页面上修:任务说明列出报错,要求只改出错的地方、不改设计和文字(`agent/gen.mjs` 的第 5 个参数传入这段任务说明)。原页面留作 `index.broken.html`、`page.broken.png`,`record.json` 里加 `repair`(修复用的模型、报错前后、agent 运行记录),`render` 换成修好后的结果;agent 记录在 `repair-session.jsonl`。最多试 2 次。

2026-10-20 第一批:Pudding 和模拟报告里共 8 页有报错,7 页是 glm 写的(3 个语法错误、4 个运行时异常),1 页是 deepseek 留下了没替换的 `__DATA__` 占位符。

## Pudding 数据(`src/report_gepa/pudding.py`)

```sh
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/the-pudding/data ~/the-pudding/data
ln -sfn ~/the-pudding/data ~/the-pudding/the-pudding__data
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.pudding ~/the-pudding data/pudding runs/pudding-originals | tee runs/pudding.log
```

收的是 The Pudding 公开了数据的全部数据报道(56 篇):`the-pudding/data` README 表格里的,加上表格没列、但目录 README 写明了对应文章的 gayborhoods、mow。每篇在 `STORIES` 里写明数据从哪来:数据仓库的目录、另一个仓库(浅克隆,只检出 csv/tsv/json)或单独发布的文件(pudding.cool 上的 json、Google 表格导出的 csv)。没收:newsletter 链接库(winning-the-internet)、没有文章的(clutch)、没有数据的(queues)、数据只在 Notion 上的 Whole Foods、只有做法说明的 Human Terrain,以及数据是成千上万个小文件、不是一份可以写报告的数据集的 wiki-billboard(一人一个文件)、two-minute-report(一场比赛一个)、country-radio(一家电台一个,外加分析的中间文件)。

每篇的数据复制到 `data/pudding/<名字>/`;数据仓库目录自带的 README 说明数据,一起复制,指向原文的行删掉,让任务是「用这份数据做报告」而不是「回忆这篇文章」。原文用同样的方式整页截图到 `runs/pudding-originals/<名字>.png`(只等 DOM 加载完,再给 5 秒,最高 30000px)。打开是开始按钮或者是视频的(kidz-bop、boybands、stand-up、three-seconds、nba-unexpected、mow),manifest 里 `original_static` 为 false,截图不能当标杆。

数据仓库是 MIT 许可;其他仓库各有各的许可。

## 没公开数据的 Pudding 文章(`src/report_gepa/puddingweb.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingweb harvest ~/the-pudding/web | tee runs/puddingweb-harvest.log
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingweb pack ~/the-pudding/web data/pudding-web | tee runs/puddingweb-pack.log
```

`harvest` 打开网站文章列表(`pudding.cool/assets/data/stories.json`)里 `data/pudding` 没有的每一篇,从头滚到尾,把页面从 pudding.cool 加载的 csv/tsv/json 存到 `~/the-pudding/web/<篇>/`,每篇一行记在 `summary.jsonl`(2026-10-20 跑过一遍:216 篇里 156 篇要打开,82 篇加载了数据文件)。`pack` 留 csv 和 tsv;json 只留一条条记录(至少 50 条)的列表,转成 `<原名>.json.csv`,嵌套一层的字段展开成 `字段.键`:页面加载的其他 json 多是地图边界、精灵图和文章自己的文案,不是要报告的数据,还会把原文交给 agent。和 `data/pudding` 或前面某篇内容完全相同的文件去掉(同一篇的两个网址、`data/pudding` 里已有的文章),剩下的文件里没有一张至少 50 行、3 列的表的整篇不要(小文件多是文章的文案、配色表和词表)。结果 74 篇,在 `data/pudding-web/<篇>/` 和 `manifest.jsonl`(2026-10-25 重抓:160 篇里 85 篇加载了数据文件;2026-10-24 那次是 71 篇,之前按「不到 20 KB 不要」、不收 json 时是 58 篇)。benchmark 用到的 50 篇和 10-24 那次逐行相同,只有每天更新的 heat-records、heat-records-map 两篇数据变了。

这些文章只用来学(report-tfgrpo 的 `--extra web`):`report_gepa.optimize.split` 看不到它们,GEPA 的验证集和测试集不变。

## Pudding 文章自己的仓库(`src/report_gepa/puddingrepo.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingrepo clone /home/user/the-pudding/web /home/user/the-pudding/repos | tee runs/puddingrepo-clone.log
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingrepo pack /home/user/the-pudding/repos data/pudding-repo | tee runs/puddingrepo-pack.log
```

大多数文章在构建时把数据打包进 JS,页面不加载数据文件,`puddingweb` 拿不到;原始数据常在 the-pudding 下这篇文章自己的仓库里(`src/data/`、`static/assets/`……)。`clone` 对 `data/pudding-web` 没收的每一篇,找名字和网址末段相同(或把 `-` 换成 `_`)的公开仓库,再加上 `OTHER` 里写明的、文章页面链接到的数据仓库(pop-love-songs、lenna-data、sxywu/hamilton、googletrends/asne、googletrends/google_nba、nextml/caption-contest-data),浅克隆、只检出 csv/tsv/json、不取 LFS,每篇一行记在 `repos.jsonl`(2026-10-25:86 篇里 58 篇有仓库,526 MB;10-24 那次整个仓库都检出,9.2 GB)。`pack` 收 node_modules、.git 以外的 csv/tsv 和记录结构的 json(同 `puddingweb`;和 csv 重复时留 csv),不要模板自带的占位文件(test.csv、sample.csv、demo 目录);和 `data/pudding`、`data/pudding-web` 或前面文件内容相同的去掉(构建复制到 `docs/`、`public/` 的那份),留篇的规则同 `puddingweb`。结果 33 篇,在 `data/pudding-repo/<篇>/` 和 `manifest.jsonl`(多一个 `repos` 字段);benchmark 用到的 24 篇和 10-24 那次逐行相同。

## Pudding 文章打包进 JS 的数据(`src/report_gepa/puddingjs.py`、`jsdata/extract.mjs`)

```sh
cd jsdata && npm ci && cd ..
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs harvest /home/user/the-pudding/js | tee runs/puddingjs-harvest.log
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs extract /home/user/the-pudding/js | tee runs/puddingjs-extract.log
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs pack /home/user/the-pudding/js data/pudding-js | tee runs/puddingjs-pack.log
```

构建时 import 进来的数据,打包后就是 JS 块里的字面量。

- `harvest` 打开网站文章列表里 `report_gepa.pudding` 和 benchmark(`report-bench/tasks.json` 的 pudding-web、pudding-repo 题)都没收的每一篇(和 `puddingweb` 一样从头滚到尾),存下页面从 pudding.cool 加载的全部 JS 和页面里的内联脚本,每篇一行记在 `summary.jsonl`。
- `extract` 对存下的 JS 跑 `jsdata/extract.mjs`(acorn 语法树)找表:至少 50 个对象字面量的数组(键就是列名)、至少 50 行等长的数组套数组(构建时去掉了表头,列名记成 `c0`、`c1`……)、至少 3 列等长数组组成的对象、csv/tsv 文本的字符串、至少 5 条按编号排的文字(问卷的题面这类对照表),`JSON.parse` 里的字符串也一样找。只认字面量:行里有函数、变量或算出来的键就不算。表在 `<篇>/tables/`,每张一行记在 `<篇>/tables.jsonl`(在 JS 里的位置、类型、行列数、表头)。改了提取器只要重跑这一步,不用重新打开页面。
- `pack` 只取 `puddingjs.TABLES` 列出的表,按它在 JS 里的位置找,改成好读的文件名,没表头的换上 `TABLES` 里的列名(照文章代码里读这张表的写法,比如 kevin-bacon 的 `Ke.nodes.map(([e,t,n,…])=>({pid:e,name:t,hop:n,…}))`),写到 `data/pudding-js/<篇>/` 和 `manifest.jsonl`。

2026-10-25 跑的:去掉 `report_gepa.pudding` 的 56 篇和 benchmark 已有的 75 篇,剩下 83 篇,33 篇提出了至少 50 行、3 列的表。逐张看过以后收了 15 篇(都进了 benchmark 的 `pudding-js`);没收的是文章文案和滚动步骤、配色表、动画精灵图和图形的位置尺寸、地图边界、为一张图算好的计数(crossword 按年、country-radio 按区间)、每格是一串编码数字读不懂的(teenagers、love-story、invisible-epidemic、judge-my-music)、缺排名的地区表(genre),以及只有名单或坐标的(asterisks、city_3d、same-name)。

## 数据在、但不是一张表的 Pudding 文章(`src/report_gepa/puddingmerge.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingmerge /home/user/the-pudding/repos data/pudding-merge [--stories a,b] | tee runs/puddingmerge.log
```

前面几个来源没收、但数据其实在的 11 篇,`RECIPES` 里每篇一个配方,写到 `data/pudding-merge/<篇>/` 和 `manifest.jsonl`。仓库只检出配方读的路径(浅克隆,不取 LFS),缓存在第一个参数的目录下。

| 篇 | 原来为什么没收 | 配方 |
|---|---|---|
| two-minute-report | 一场比赛一个文件(1,476 个) | 仓库 `polygraph-cool/last-two-minute-report` 里已有合并好的 `output/all_games.csv`,26,822 次判罚 |
| country-radio | 一家电台一个文件,加上分析的中间文件 | `the-pudding/country-radio-data` 的 `input/`:29 家电台 2022 年的播放记录合成 `plays.csv`(209,572 行),城市取自文件名 |
| caption-contest | 一期一个文件(397 个) | `nextml/caption-contest-data` 的 `summaries/` 合成 `captions.csv`(385 期、2,349,117 条配文、269 MB),期数和抽样算法取自文件名 |
| wiki-billboard | 一人一个文件 | `the-pudding/wiki-billboard-data` 的每周浏览量合成 `weekly-pageviews.csv`(约 6,700 人,2015-07 到 2018-09),加 `category.csv` 的 247 人 |
| same-name | 页面只加载读者所在的州 | 页面按读音组取的 `assets/places/0000.csv` 到 `5553.csv` 合成 `places.csv`(22,042 个地点),读音组成为一列 |
| book-covers | 只有 json | 记录转成 `books.csv`;`grid_point` 是文章排版的坐标,去掉 |
| eu-regions | 数据在地图文件的属性里 | NUTS2 地区、国家、首都三张表的 2017 年人均 GDP(PPS,欧盟平均 = 100) |
| nba-spelling、gyllenhaal | json 是「名字 → 拼法列表」 | 展开成 `spellings.csv`(名字、拼法、次数) |
| restaurants、new-slang | 文件在 googletrends.github.io,`puddingweb` 只收 pudding.cool 的 | 照原样取,改成好读的文件名;new-slang 旁边的 `summary_3.csv` 是文章算的相关系数,不收 |

same-name 要请求 5,554 个小文件,连接被代理断开时每个文件最多重试 4 次;已取的文件留在缓存里,重跑不再取。

## 原文的发现(`src/report_gepa/originals.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.originals runs/originals [id ...] --workers 20 --model deepseek-flash --answers | tee -a runs/originals.log
```

给 benchmark 的 Pudding 题写标准答案:原文作者从这份数据得出的发现,写成和页面交的 `facts.json` 一样的结论加代码。pi agent(`agent/gen.mjs`,`WEB_TOOLS=1`)拿到题目的数据和原文网址,用 `web_fetch`、`web_view` 读原文,列出作者从数据得出的每个发现,能用数据重现的写进 `facts.json`(每条带原文的话 `source`),重现不了的写进 `skipped.json`。之后每条代码重新运行,结论和输出按 1.3 的同一个判法对一遍(`trust.claims_hold`),`source` 在 agent 读到的网页文字里查一遍;都过的进 `answer.json`,`--answers` 再拷成 `report-bench/out/answers/<id>/facts.json`。每篇在 `runs/originals/<id>/`:`facts.json`、`answer.json`、`skipped.json`、`record.json`、`session.jsonl`。已有 `answer.json` 的篇跳过。

2026-10-28 到 10-29 用官方端点的 `deepseek-flash` 跑完 147 篇(lifeafter 的题目数据和原文对不上,已从题库删掉),共 1115 条;13 篇写不出(数据重现不了原文的发现,比如 karen 的数据里没有 Karen,restaurants 没有坐标),这些题不判 2.1。147 篇逐条人工复核过,交互页面逐页点击核对,改动和理由记在各篇 `record.json` 的 `review` 里:

- 每条代码在题目的数据上重跑,对着输出看结论;再对着原文看结论里的数和口径。只认原文网站读回来的文字(包括代理和存档),对不上的用 `report_bench.capture` 渲染原文页面再找,必要时查网页源码或原文自己的仓库。
- 引语检查误判的捞回:引语在原文里,只是 `web_view` 读到的文字里图表标签插在句子中间,或引语把卡片上的几个标签连成了一段(countries、campaign-colors、lit-canon、miles、caption-contest 等)。
- 1.3 判犯的 7 条:5 条是结论确实超出输出(「被暗杀」、漏了并列项、13.28% 写成 13.2%),改结论;2 条是结论对、输出看不出来(数据本身全是亚裔角色;两组国家不重叠),改代码把它打印出来。改完的都重跑核对过。
- 1.3 看不出的问题:结论和输出一致,但和原文对不上(banknotes 的 Hannibal 1993 年就上了钞票;bears-boys 的猫在数据里偏男性),改结论;同一个词在不同 fact 里换口径凑原文的数(hype 的「熬过新秀合同」),去掉。
- 实时更新的页面(heat-records、heat-records-map 的计数器、mars-weather)讲的是抓取那天的数,不是稳定的发现,去掉;mars-weather 的引语是 agent 拿数据填进页面空白处的,原文从来没这么写过。
- 引语出自原文自己仓库里的文件、页面上要滚动到某一步或点开才显示的,保留,在 `review` 里写明出处(census-history 的话题文字、cetaceans 的图表标注、covid-science)。
- 交互页面(测验、点击翻页、音频导览)agent 读不到的引语,点击走一遍页面核对:在原文里的捞回(sitters-standers、music-dna、songwriters、wiki-death、photo-history 测验后按数据写出的句子),wiki-breakout 的引语是导览字幕(`tracks.json`),保留。
- superteams 的 agent 用 4800 种定义的网格搜索去凑原文的 11 支球队,跑了两个小时被停掉;它最后用的设定和页面默认选中的按钮、各位专家写明的设定一致,保留。

已知的漏洞:引语检查(`read_on_web`)把 agent 读过的所有网页都算进去,包括 GitHub、搜索结果和第三方页面(boybands 读到过一个第三方生成的博客),应该只认原文网站。

## judge

评测代码和 rubric 在 `report-bench`(`score.py` 的 `score_page` 是唯一的打分入口;`capture.py`、`trust.py`、`facts.py`、`judge.py`、`rubric.py`、`render.py`、`llm.py`、`rubric/`),说明见 `report-bench/README.md`;这里的命令要 `PYTHONPATH=src:../report-bench/src`。

### judge 分析(`judgestats.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.judgestats stats runs/judge/glm-a          # 各版本平均分、条目两两相关、VIF
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.judgestats agree runs/judge/glm-a runs/judge/glm-b   # 两次判分的一致率
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.judgestats human runs/judge/glm-a labels/round1     # 和人工标注的一致率
```

- 耦合:两条分数的 Spearman 相关超过 0.7 就标出来;再把每条对其余各条做回归,VIF 超过 5 说明这一条大部分能由别的条目说出来。相关矩阵的特征值看这些条目实际上有几个独立方向。
- 一致率:同一个 judge 判两次(重测),或换一个模型判(跨模型),逐条算 Spearman、平均绝对差、落在同一个分数区间的比例、按区间算的加权 kappa。
- 和人比:标注是「原文 vs 指南版」哪边好。逐条看这一条单独挑出的高分页面和人选的是否一致,再看每层,和按 rubric 合成的页面分(信犯了任何一条就是 0,否则是达的平均分);雅的两两比较也和同一批标注比。


## GEPA(`src/report_gepa/optimize.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.optimize runs/gepa/<名字> [--max-calls 120] [--val 8] [--train 19] [--minibatch 3] | tee runs/gepa/<名字>.log
```

用 `gepa==0.1.4` 优化写页面 agent 的系统提示词 `{"guide": ...}`,从 `guides/seed.md` 起步。

- **数据**:Pudding 里原文是滚动长文的 43 篇。人工标注过的 16 篇是测试集,GEPA 不碰;其余 27 篇按 `--seed` 分成验证 8 篇(帕累托集)和训练 19 篇(反思用的小批量)。划分写在 `<run>/split.json`。
- **一次 rollout** = 一篇数据 + 一版指南:pi agent 按 benchmark 的任务说明(`report-bench/TASK.md`:交付 `facts.json`(每个发现的结论和算出它的 pandas 代码)和 `index.html`,页面写英文)加上 `pageshot` 的用法写页面,再由 `report_bench.score.score_page` 打分,和 benchmark、TF-GRPO 是同一个定义,judge 是 deepseek:
  - 信:1.1 页面可渲染、1.2 fact 能执行、1.3 结论和数据一致,犯了任何一条整页 0 分。
  - 达:2.x 每条 0–1 分,一次调用。
  - 雅:3.1、3.2 每条 0–1 分,一次调用,照 rubric 里的典型案例定档。
  - 分数 = 达和雅各条的平均(等权)。
- **反馈**:`score_page` 结果里的 `feedback`:信的每处问题和原因,每条的分数、位置和理由。
- 每次 rollout 的页面、截图、信的核对、判分都在 `<run>/rollouts/<指南哈希>/<篇>/`;已有的复用,断了重跑同一命令。

### 单独给一份指南打验证分(`src/report_gepa/evalguide.py`)

```sh
PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.evalguide runs/<名字> [--guide guides/seed.md] [--with-rubric] | tee runs/<名字>.log
```

用和 GEPA 一样的 `Adapter` 在验证集 8 篇上各写一页、打分,分数和 `runs/gepa/full` 的验证分可比。`--with-rubric` 把评分标准接在指南后面:信 1.1–1.3 的一票否决,每条打分项的说明、五段分档和典型案例的文字(judge 还看案例截图,指南里只有文字)。它是基于 judge 优化提示词要胜过的基线:写页面的一开始就知道评审的标准。

2026-10-24 跑的 `runs/seed-rubric`(种子 + 评分标准,4645 字):

| 指南 | 验证 8 篇 | 去掉 skate-music 的 7 篇 | 2.4 | 2.6 | 文中嵌图(已删) | 3.1 | 3.2 |
|---|---|---|---|---|---|---|---|
| 种子 | 0.541 | 0.542 | 0.69 | 0.33 | 0.27 | 0.33 | 0.61 |
| 种子 + 评分标准 | 0.622 | 0.711 | 0.57 | 0.68 | 0.71 | 0.56 | 0.74 |
| GEPA `0112` | 0.669 | 0.657 | 0.65 | 0.62 | 0.54 | 0.49 | 0.65 |

(各条是没被 1.1 否决的页面的平均。)skate-music 脚本报错(`T is not a function`)被 1.1 判 0;其余 7 篇每篇都比 `0112` 高,规定了做法的几条(2.6 一张图连续变、文中嵌图的句中小图、3.1 数据标记做成话题里的东西)涨得比 GEPA 还多。`0112` 多出来的是 2.4 图表可读(它写了字号下限)和渲染兜底(第 0 节);只有一篇报错,还说不清是不是系统性的差别。

### 2026-10-22 的 `runs/gepa/full`

从第 1 代 `e7d538554fa4` 起步(它是从种子起跑那次的第一轮产物),120 次 rollout,11 轮。结果在 `<run>/result.json`,最好的指南在 `<run>/best-guide.md`。

| 指南 | 来源 | 验证集均分 |
|---|---|---|
| 种子 `119267d05acb` | `guides/seed.md` | 0.541 |
| `e7d538554fa4` | 起点 | 0.634 |
| `a812c3952494` | 第 1 轮 | 0.666 |
| **`0112543a18a2`** | 第 3 轮 | **0.669,最好** |
| `353b2c6bda17` | 第 6 轮 | 0.658 |
| `066d9001a6d6` | 第 8 轮 | 0.654 |
| `717a4f70759f` | 第 9 轮 | 0.583(skate-music 脚本报错被否决,其余 7 篇平均 0.667) |
| `d5e12ec46f83` | 第 10 轮 | 0.638 |

另有 5 轮的新指南没过小批量(997b、5c56、804a、0599、dd34)。读法:

- 提升在前两代:种子到 `a812`,8 篇验证集每篇都涨,平均 +0.125(2.4 视图连贯 .33→.67、2.12 文中嵌图 .27→.58)。
- 之后在噪声里打转:`a812` 到 `d5e1` 全在 0.64–0.67,0112 和 a812 逐篇差的均值 0.003、标准误约 0.017。各代互相拉锯,0112、717a 雅高而嵌图、连贯低,353b、066d 相反;逐篇取最好的帕累托上限是 0.713。
- 同一个 judge 给 Pudding 原文的分约 0.675,第 2 代以后已经和原文打平,judge 可能分不出更好。
- 有几轮的去留由一页脚本报错决定(rain 被否决两次、717a 的 skate-music),接受与否接近抛硬币。
- 合并在单组件下不会触发(`gepa/proposer/merge.py` 要求至少一个组件和祖先相同)。
- 还没在测试集 16 篇上验证。

跑的过程中修过三处,不改提示词:写页面 agent 的请求超时 30 秒改 5 分钟(带几十张截图时几乎每步都超时重发);agent 150 步提示收尾、170 步截停(一页 infinite 跑到 310 步);反思的回复按提示词哈希存在 `<run>/reflections/`,中途重启时拿回同一版指南。重启后选父代的随机状态不会复现,中途那一轮仍会重来。

## 写页面 agent 的浏览器(`agent/bin/pageshot`)

沙盒(`agent/sandbox.sh`)里打开了本地回环,只读挂上 Chromium、本项目的 Python 环境和 `src/`,`pageshot index.html` 用 `capture.py` 像读者一样滚动截图,输出 `_shots/frames/NN.jpg`、`_shots/thumb.jpg` 和 `evidence.json`;仍然上不了外网。`gen.mjs` 把模型声明为能收图片,read 工具才会把截图交给模型。2026-10-20 cookies 上试过:没有浏览器时一页 62 步、16 分钟、输入 250 万 token;有了以后 21–34 步、4.5–7.5 分钟、输入 9–26 万 token。agent 会跑 pageshot,但不一定把截图看全(一页的条形图没画出来,它只看了 2 张截图)。

## 数据

数据放 Google Drive(qfy2518418912@gmail.com)「我的云端硬盘」根目录,只有本人账号能打开。

| 文件 | 内容 | 解压到 |
|---|---|---|
| [`pudding-data.tar.xz`](https://drive.google.com/file/d/1rN-754lKNpakj4Y7bAYHzhZOzSrvQVph/view)(81 MB,解压后 617 MB) | `data/pudding/`:56 篇的数据文件和 `manifest.jsonl`(2026-10-20) | `report-gepa/data/` |
| [`pudding-web-data.tar.xz`](https://drive.google.com/file/d/10N17jX8kobBrAjMEkTt7Wrax8I1vy4Nf/view)(16 MB) | `data/pudding-web/`:74 篇没公开数据的文章,从页面加载的 csv/tsv 和 `manifest.jsonl`(2026-10-25) | `report-gepa/data/` |
| [`pudding-repo-data.tar.xz`](https://drive.google.com/file/d/10artVA9s4JVIytp9V39u45sY72RYVjA_/view)(63 MB) | `data/pudding-repo/`:33 篇从文章自己的 GitHub 仓库收的 csv/tsv 和 `manifest.jsonl`(2026-10-25) | `report-gepa/data/` |
| [`mock-data.tar.xz`](https://drive.google.com/file/d/1X-lXq3lohkKtG3JIxUNVOERVcUxlB54w/view)(15 MB,解压后 144 MB) | `data/mock/`:48 份明细 CSV 和规律 `findings.json`。2026-10-21 生成时的造数脚本 `gen.py` 和 `manifest.jsonl` 没传上 Drive、已经丢了,这份是 2026-10-25 从 benchmark 的 `out/` 还原的,build 用到的都在 | `report-gepa/data/` |
| [`pudding-js-data.tar.xz`](https://drive.google.com/file/d/1bJ_W40DzagQBibUKzMbopabWJaYopDmY/view)(1.1 MB,解压后 6 MB) | `data/pudding-js/`:15 篇从文章 JS 里提出的表和 `manifest.jsonl`(2026-10-25) | `report-gepa/data/` |
| [`pudding-merge-data.tar.xz`](https://drive.google.com/file/d/1jKV68pCxT1vOsZiJwkQ2dxwCHg_AJOUK/view)(77 MB,解压后 368 MB) | `data/pudding-merge/`:11 篇合并或展开好的表和 `manifest.jsonl`(2026-10-25) | `report-gepa/data/` |

```sh
tar -xJf pudding-data.tar.xz -C report-gepa/data/
tar -xJf pudding-web-data.tar.xz -C report-gepa/data/
tar -xJf pudding-repo-data.tar.xz -C report-gepa/data/
tar -xJf mock-data.tar.xz -C report-gepa/data/
tar -xJf pudding-js-data.tar.xz -C report-gepa/data/
tar -xJf pudding-merge-data.tar.xz -C report-gepa/data/
```

不从 Drive 取也能重做:`report_gepa.pudding` 从 the-pudding 的公开仓库重新克隆生成同样的 `data/pudding/`(见上面「Pudding 数据」)。

`runs/originals/`、`runs/evidence/` 和它们的日志在仓库里。更早的 `runs/`(生成的页面、截图、证据、judge 记录)和 `labels/`(人工标注)没有上传,也不在仓库里。
