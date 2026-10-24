# report-bench

比各家 AI 系统「把一份数据做成数据报告网页」做得怎么样的 benchmark。

- 开放赛道:模型、agent、整套流程都行,只要按格式交页面;比的是整个系统。不设基线。
- 每题给 `data/` 下一张或几张原始数据表(csv),和一句说明数据是什么的题目;页面一律用英文。
- 170 题:The Pudding 的 122 篇(真实数据,`report-gepa/data/pudding` 47 篇、`pudding-web` 51 篇、`pudding-repo` 24 篇)和 48 份 mock 明细数据(24 类业务各 2 份,`report-gepa/data/mock`)。108 题是一张表,其余 2 到 8 张。

## 题目(`tasks.json`)

每题一项:`id`、`source`(`pudding`、`pudding-web`、`pudding-repo`、`mock`)、`tables`(那份数据里给哪几张表,相对它在 `report-gepa/data/<source>/<id>/` 下的路径)、`title`。

- 只给原始数据表,为某张图算好的中间表(按年汇总、百分比、排名、图表坐标)不给;一篇文章的几张原始表(比如电影、演职人员、制片公司各一张)都给。同一份数据重复的(`docs/` 和 `src/` 下各一份)只给一份。json 只给一条条记录结构的,转成 csv(文件名 `<原名>.json.csv`)。
- 没收的 Pudding 文章:只有中间表的(birth-control、neighborhoods、prosecutors、hater、hip-hop-words、the-office、comics、incarceration、words-against-strangers),只有对照表、没有数据的(airports),数据不全的(same-name 只有一个州),和 music-bubble 是同一份数据的(music-map),不是能写报告的数据的(menu-collection 的菜单图片尺寸、cloud-zoo 的动物园直播列表、science_etc_1 的论文文本片段),以及数据只有 json 的。
- `pudding-repo`(各篇自己的 GitHub 仓库)里没收的:动画的分镜和精灵图参数(ivf、sesame),一个时刻一个小文件的(clocks,1444 个),问题只有编号、没有题面的(spades),内容看不懂的(genre 的排名矩阵和缺排名的地区表),和 `pudding` 里 heat-records-map 是同一份数据的(weather-map),一场比赛一个文件的(caption-contest,397 个),按年计数的(crossword)。`pudding-web` 新进的 10 篇只收了 authors、death、lifeafter、nba-top-plays:其余是平滑后的趋势和计数(big-hair、eating-alone、best-sellers)、词表和网站对照表(millennials、elections),和 vocabulary 重复的(projects_vocabulary);后来 json 转出的 chyrons(三元图坐标)和 happy-map(地图标签)也不收。
- 题目只说数据是什么,不说结论:原文标题常常就是结论(「Women's Pockets are Inferior」),不用。

## 生成题目目录(`src/report_bench/build.py`)

```sh
cd report-bench && PYTHONPATH=src python3 -m report_bench.build out | tee out-build.log
```

- `out/tasks/<id>/`:`data/<表>.csv`(tsv 转成 csv,utf-8,文件名里的 `%20` 之类还原)和 `task.json`(`id`、`title`、`files`、`instruction`)。这是发给参赛者的全部东西。一共 768 MB,最大的是 mow(250 MB)。
- `out/tasks.jsonl`:每题的来源、题目、每张表的行列数和大小;Pudding 题另有 `original`,数据出自的那篇文章的网址。
- `out/answers/<id>/`:打分用,不发给参赛者。mock 题是 `findings.json`(预埋的规律);Pudding 题是 `original.json`(原文的网址、标题、发表年月),原文就是这份数据的人工可视化,可以拿来对照。

`instruction` 是 `TASK.md` 的全文,每题一样。

## 提交

每个系统一个目录,每题一个 `index.html`:`submissions/<系统>/<id>/index.html`。页面要离线能打开,css、脚本、数据都写在文件里(见 `TASK.md`)。

## 打分

打分脚本还没写。打算:用 report-gepa 的 judge(1.1 打不开整页 0 分;表达 2.x、美学 3.x 各条 0–1),mock 题另加一项,逐条看页面有没有讲出 `findings.json` 里的规律。

## 评测代码

从 report-gepa 移过来,评测标准只有这一份:report-gepa(GEPA)和 report-tfgrpo 都 import 这里的 `report_bench.capture`、`judge`、`rubric`、`llm`。用 report-gepa 的环境(`../report-gepa/.venv`,装法见 report-gepa 的 README);1.2 的事实核查用 report-gepa 的 pi agent(`report_gepa.generate.run_agent`)。典型案例的截图在 `report-gepa/runs/evidence/`。

### 模型调用(`src/report_bench/llm.py`)

```sh
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.llm "提示词"
```

用 OpenAI SDK 流式调用,中转端点上长回复不会因为整段等到最后才返回而被掐断。结束原因不是 `stop`(没结束就断了,或撞了长度上限)算不完整,会重试;最后一次仍不完整就照原样返回,由调用方决定怎么记。2026-10-19 在 `deepseek-v4.1-flash` 上调通。

### 渲染(`src/report_bench/render.py`)

```sh
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.render <page.html> <out.png>
```

输出 JSON:`verdict` 是 `ok`、`blank`(正常加载但没有文字)或 `render_failed`(没看到页面,打分时屏蔽);另外记录 `page_errors`(加载时未捕获的异常)、`syntax_errors`(内联脚本过不了 `node --check`)、`hang`(页面卡死)。

2026-10-19 用五个测试页验证过:正常页、白页、语法错误、加载时报错、`while(true){}` 卡死,五个都分对。

### 打分(`capture.py`、`judge.py`、`factcheck.py`、`rubric.py`)

rubric 只有一份:`rubric/judge-dimensions.md`。`rubric.py` 读里面以条目编号开头的表格行,判法写在表里:信(1.x)判「犯了 / 没犯」,犯了任何一条整页 0 分;达(2.x)和雅(3.x)每条打 0–1 分;雅的每条另附几个打过分的典型案例。判法照 MiMo 开源打分服务(`recipes/design`)的 query judge 和评测 rubric。

#### 采集证据

```sh
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.capture one <page.html 或 url> <out_dir> [--data <数据>...]
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.capture pudding runs/pudding-pages data/pudding runs/evidence --workers 4 | tee runs/capture.log
```

- 为什么不只用现成的整页截图:MiMo 的渲染服务(`render.py` 照它做)截一张整页长图,截前冻结动画。滚动叙事的页面上,一张图随滚动变化的几个状态在整页图里只剩一个(titletowns 原文第一张图有 4 个状态,整页图只截到最后一个)。整页图保留下来做缩略图,滚动帧另外截。
- 像真人一样滚动:鼠标滚轮每次 80px,让 scrollama 这类滚动触发一步一步地触发;每 450px 等动画停下来截一屏(1440×900),不冻结动画;和上一帧几乎一样的帧不留。页面太长时加大间隔,最多 60 帧。
- 每帧记下屏幕上每张图的位置和内容指纹。页面在滚、图在屏幕上的位置不动,就是固定住了(sticky);指纹变了,就是图重画了。汇总成 `scroll_story`:哪张图在哪几帧固定、出现了几种状态。2026-10-20 试过:foundation-names 原文主图第 8–21 帧固定、5 种状态;titletowns 原文三张图各固定 4–7 帧、4–7 种状态;titletowns 指南版没有固定的图。
- 另外截一张整页图缩成 480px 宽的缩略图;按页面顺序抽出全部文字(带位置、是否在图里、是否隐藏)和图表清单(svg、canvas、img 的大小,svg 里的图形和标签个数)。
- 输出 `<out_dir>/frames/NN.jpg`、`thumb.jpg`、`evidence.json`(还记着页面用的数据,给事实核对用)。
- `pudding` 命令采集每篇的原文(`<out>/<篇>/original`)和生成的版本(`<out>/<篇>/<版本>`),已采集的跳过。原文是交互式页面、不是滚动长文的(manifest 里 `original_static` 为 false:开始按钮、视频,或只有一屏的应用,如 falsetto、boybands、book-covers、birthday-paradox)不采原文;`judgestats` 也把这些篇整篇排除,它们的原文只能看到一屏,judge 和人工比较都用不了。

#### 判

```sh
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.judge page runs/evidence/titletowns/original --items 1.1,1.2,1.3,2.2,2.4,2.11,3.1,3.2 [--per-item]
```

- 信、达、雅各是一组,每组一次调用,照 MiMo 评测 rubric 一次返回七个维度的做法(提示词里写了「各条独立判断」)。信里 1.1 和 1.2 不调模型,所以信的这次调用只有 1.3;达的各条一次打完;雅的两条一次打完。每条照样单独写一份记录,组的共同回答在 `group-<维度>.json`。`--per-item` 改成每条单独一次调用,是测耦合时的对照:一起判时一条的印象会不会带到别的条上,比一比就知道。judge 看到:全部帧(超过 40 帧均匀抽 40)、缩略图、页面文字(每段标了在第几帧)、滚动记录。帧按 1080px 宽发送。默认 judge 是 `glm-5.3-flash`。
- 1.1 不调模型,按采集结果判。只对生成页判脚本报错:Pudding 原文自己也报错(titletowns 有 "reading 'latitude'"),页面照样能用。
- 1.2 由 `factcheck.py` 判:pi agent 在沙盒里读数据和 `page.txt`(页面全部文字),列出页面上的每个数字和带量的说法,用 python 复算,每条记 ok、wrong 或 unverifiable。有一条 wrong 就算犯了;原文引用了没公开的数据时会是 unverifiable,不算犯。
- 1.3 由 judge 看图判犯没犯,写出犯在哪张图。信的三条犯了任何一条,整页 0 分。
- 达的条目照 MiMo 评测 rubric(`recipes/design/webdev/eval_rubric.py`)的写法打 0–1 分:每条在 rubric 的「打分的分段说明」里有自己的五段描述,先按它定区间,再在区间内取值,写出位置和扣分理由。给不出合法分数或结论的回答记为没判出来,不当 0 分。雅也打 0–1 分,但先给 judge 看 rubric 里每条的典型案例:`runs/evidence/<篇>/<版本>/frames/` 里的一帧、分数和理由,标明「不是要评的页面」,再给要评的页面,judge 照着案例定档。案例取自人工标注过的页面,算雅和标注的一致率时排除这几篇。原来的组内挑选(MiMo 的 group pick)比不出来,多数轮次判「无明显差别」,已经删掉。
- 记录在 `runs/judge/page/<篇>/<版本>/<条目>.json`,带 judge 模型、提示词和 rubric 的哈希、采集版本;已有的跳过。
- 调用失败(重试后仍失败)不写记录,打出 FAILED,重跑同一命令会补上;额度不够时整批停下。

### 调用失败和重试(`src/report_bench/llm.py`)

deepseek 经中转站时,同一个大的图文请求有时几秒内返回 400「模型请求失败」或正文为空的 stop(同一请求成功和失败时 prompt token 数不同,像是分到了不同后端),有时 524 超时。和截图内容、图片张数、`max_tokens` 都无关(2026-10-20 逐项排除过)。正文为空也算没完成,和其他失败一起最多重试 5 次;加上以后 v5 一轮判分没有一次失败。


## 数据

`out/` 不进仓库,上传 Google Drive 后在这里写位置和取回方法。
