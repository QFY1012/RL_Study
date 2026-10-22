# report-gepa

用 GEPA 优化写报告页面的提示词。计划见 `PLAN.md`。和仓库里其他目录无关,从头写。

## 环境

```sh
python3 -m venv .venv
.venv/bin/pip install gepa==0.1.4 openai==3.35.1 playwright==1.64.0 pillow==13.0.0
```

浏览器用容器里预装的 Chromium(`/opt/pw-browsers/chromium`),不跑 `playwright install`。

密钥和端点放在 `~/.config/report-gepa/llm.env`(权限 600,不进仓库):

```
LLM_API_KEY=...
LLM_BASE_URL=https://openoneapi.com/v1
LLM_MODEL=deepseek-v4.1-flash
```

同名的环境变量会覆盖文件里的值。

## 模型调用(`src/report_gepa/llm.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.llm "提示词"
```

用 OpenAI SDK 流式调用,中转端点上长回复不会因为整段等到最后才返回而被掐断。结束原因不是 `stop`(没结束就断了,或撞了长度上限)算不完整,会重试;最后一次仍不完整就照原样返回,由调用方决定怎么记。2026-10-19 在 `deepseek-v4.1-flash` 上调通。

## 渲染(`src/report_gepa/render.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.render <page.html> <out.png>
```

输出 JSON:`verdict` 是 `ok`、`blank`(正常加载但没有文字)或 `render_failed`(没看到页面,打分时屏蔽);另外记录 `page_errors`(加载时未捕获的异常)、`syntax_errors`(内联脚本过不了 `node --check`)、`hang`(页面卡死)。

2026-10-19 用五个测试页验证过:正常页、白页、语法错误、加载时报错、`while(true){}` 卡死,五个都分对。

## 模拟报告数据(`src/report_gepa/datagen.py`、`domains.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.datagen data/reports --per-kind 3 --workers 8 | tee runs/datagen.log
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
PYTHONPATH=src .venv/bin/python -m report_gepa.rawgen data/mock --per-kind 2 --workers 8 | tee runs/rawgen.log
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
PYTHONPATH=src .venv/bin/python -m report_gepa.generate <out_dir> <数据文件或目录>... [--guide guides/seed.md] [--model deepseek-v4.1-flash] [--n 2]
```

- 系统提示词是指南(GEPA 优化的对象,默认 `guides/seed.md`,一句话)。用户消息是 `agent/gen.mjs` 里固定的任务说明:数据在 `data/`、页面写到 `index.html`、不引用外部资源、环境里没有浏览器。数据不放进提示词,agent 用工具自己读。
- 工具:读、写、改文件只限工作目录;shell 命令在 `agent/sandbox.sh` 里跑(新的挂载、网络、进程命名空间,只看得到工作目录和只读的 `/usr`、node;没有网络,环境变量里没有密钥)。
- 每一版在 `<out_dir>/<名字>/`:`index.html`、截图 `page.png`、记录 `record.json`(每次 agent 运行的步数、token、耗时,渲染结果)、agent 全程记录 `session.jsonl`。拷进去的数据跑完就删。
- 没写出 `index.html`、HTML 没闭合、标签写成了文字(`< div`)算没交付,整轮重来,最多 2 轮。
- 每步输出上限 65536 token(pi 默认 32000,glm 不指定时停在 8192)。

2026-10-19 用一份 Pudding 风格的指南(已删)在一份 A/B 实验数据上试过:7.4 分钟、39 步、输入 37.7 万 token、输出 6.2 万 token,页面 7,635px,五张不同的图,数字是 agent 用 python 从数据里算的。那一次 agent 花了很多步在沙盒里找浏览器想自查,之后在任务说明里写明了没有。

## 批量生成页面(`src/report_gepa/pagegen.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.pagegen data/reports runs/pages --workers 6 --renders 3 | tee runs/pagegen.log
PYTHONPATH=src .venv/bin/python -m report_gepa.pagegen data/pudding runs/pudding-pages --workers 5 --renders 3 | tee runs/pudding-pages.log
```

`--pages seed-ds-1,detail-ds-1` 只生成列出的页面。

每 30 秒读一次数据目录的 `manifest.jsonl`(每行的 `data` 是数据相对数据目录的路径),新的数据立刻排队;`split.json` 出现且排队的页面全部完成后退出。中转返回「预扣费额度失败」(余额不够)时整批立即停下,那一页不留记录,充值后重跑同一命令即可。已有 `record.json` 的页面跳过,断了重跑即可。`--renders` 限制同时打开的浏览器数。

每份数据 4 个页面,来源不同,让标注时好坏的差别不只来自抽样波动:

| 名字 | 指南 | 模型 | 个数 |
|---|---|---|---|
| `seed-ds-1`、`seed-ds-2` | `guides/seed.md`(一句话) | deepseek-v4.1-flash | 2,也是 GEPA 的参照页面 |
| `seed-glm-1` | `guides/seed.md` | glm-5.3-flash | 1 |
| `detail-ds-1` | `guides/detailed.md` | deepseek-v4.1-flash | 1 |

`guides/detailed.md` 是让 deepseek-v4.1-flash 自己写的通用详细指南,代表「认真写过提示词」的水平。人工标注里的「指南版」(`pudding-ds-1`)是 2026-10-20 用一份 Pudding 风格的指南生成的;那份指南禁止滚动叙事、每节一张图,和 rubric 2.4 相反,已经删掉,标注过的页面作为数据留在 Drive。`guides/editorial.md` 是杂志专题风格,只试过,没进批量。

## 修脚本报错的页面(`src/report_gepa/repair.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.repair runs/pudding-pages runs/pages --workers 4 | tee runs/repair.log
```

渲染时记录到脚本报错(运行时异常或语法错误)的页面,交给 deepseek-v4.1-flash 的 agent 在原页面上修:任务说明列出报错,要求只改出错的地方、不改设计和文字(`agent/gen.mjs` 的第 5 个参数传入这段任务说明)。原页面留作 `index.broken.html`、`page.broken.png`,`record.json` 里加 `repair`(修复用的模型、报错前后、agent 运行记录),`render` 换成修好后的结果;agent 记录在 `repair-session.jsonl`。最多试 2 次。

2026-10-20 第一批:Pudding 和模拟报告里共 8 页有报错,7 页是 glm 写的(3 个语法错误、4 个运行时异常),1 页是 deepseek 留下了没替换的 `__DATA__` 占位符。

## Pudding 数据(`src/report_gepa/pudding.py`)

```sh
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/the-pudding/data ~/the-pudding/data
ln -sfn ~/the-pudding/data ~/the-pudding/the-pudding__data
PYTHONPATH=src .venv/bin/python -m report_gepa.pudding ~/the-pudding data/pudding runs/pudding-originals | tee runs/pudding.log
```

收的是 The Pudding 公开了数据的全部数据报道(56 篇):`the-pudding/data` README 表格里的,加上表格没列、但目录 README 写明了对应文章的 gayborhoods、mow。每篇在 `STORIES` 里写明数据从哪来:数据仓库的目录、另一个仓库(浅克隆,只检出 csv/tsv/json)或单独发布的文件(pudding.cool 上的 json、Google 表格导出的 csv)。没收:newsletter 链接库(winning-the-internet)、没有文章的(clutch)、没有数据的(queues)、数据只在 Notion 上的 Whole Foods、只有做法说明的 Human Terrain,以及数据是成千上万个小文件、不是一份可以写报告的数据集的 wiki-billboard(一人一个文件)、two-minute-report(一场比赛一个)、country-radio(一家电台一个,外加分析的中间文件)。

每篇的数据复制到 `data/pudding/<名字>/`;数据仓库目录自带的 README 说明数据,一起复制,指向原文的行删掉,让任务是「用这份数据做报告」而不是「回忆这篇文章」。原文用同样的方式整页截图到 `runs/pudding-originals/<名字>.png`(只等 DOM 加载完,再给 5 秒,最高 30000px)。打开是开始按钮或者是视频的(kidz-bop、boybands、stand-up、three-seconds、nba-unexpected、mow),manifest 里 `original_static` 为 false,截图不能当标杆。

数据仓库是 MIT 许可;其他仓库各有各的许可。

## judge(`capture.py`、`judge.py`、`factcheck.py`、`rubric.py`)

rubric 只有一份:`rubric/judge-dimensions.md`。`rubric.py` 读里面以条目编号开头的表格行,判法写在表里:信(1.x)判「犯了 / 没犯」,犯了任何一条整页 0 分;达(2.x)和雅(3.x)每条打 0–1 分;雅的每条另附几个打过分的典型案例。判法照 MiMo 开源打分服务(`recipes/design`)的 query judge 和评测 rubric。

### 采集证据

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.capture one <page.html 或 url> <out_dir> [--data <数据>...]
PYTHONPATH=src .venv/bin/python -m report_gepa.capture pudding runs/pudding-pages data/pudding runs/evidence --workers 4 | tee runs/capture.log
```

- 为什么不只用现成的整页截图:MiMo 的渲染服务(`render.py` 照它做)截一张整页长图,截前冻结动画。滚动叙事的页面上,一张图随滚动变化的几个状态在整页图里只剩一个(titletowns 原文第一张图有 4 个状态,整页图只截到最后一个)。整页图保留下来做缩略图,滚动帧另外截。
- 像真人一样滚动:鼠标滚轮每次 80px,让 scrollama 这类滚动触发一步一步地触发;每 450px 等动画停下来截一屏(1440×900),不冻结动画;和上一帧几乎一样的帧不留。页面太长时加大间隔,最多 60 帧。
- 每帧记下屏幕上每张图的位置和内容指纹。页面在滚、图在屏幕上的位置不动,就是固定住了(sticky);指纹变了,就是图重画了。汇总成 `scroll_story`:哪张图在哪几帧固定、出现了几种状态。2026-10-20 试过:foundation-names 原文主图第 8–21 帧固定、5 种状态;titletowns 原文三张图各固定 4–7 帧、4–7 种状态;titletowns 指南版没有固定的图。
- 另外截一张整页图缩成 480px 宽的缩略图;按页面顺序抽出全部文字(带位置、是否在图里、是否隐藏)和图表清单(svg、canvas、img 的大小,svg 里的图形和标签个数)。
- 输出 `<out_dir>/frames/NN.jpg`、`thumb.jpg`、`evidence.json`(还记着页面用的数据,给事实核对用)。
- `pudding` 命令采集每篇的原文(`<out>/<篇>/original`)和生成的版本(`<out>/<篇>/<版本>`),已采集的跳过。原文是交互式页面、不是滚动长文的(manifest 里 `original_static` 为 false:开始按钮、视频,或只有一屏的应用,如 falsetto、boybands、book-covers、birthday-paradox)不采原文;`judgestats` 也把这些篇整篇排除,它们的原文只能看到一屏,judge 和人工比较都用不了。

### 判

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.judge page runs/evidence/titletowns/original --items 1.1,1.2,1.3,2.2,2.4,2.11,3.1,3.2 [--per-item]
```

- 信、达、雅各是一组,每组一次调用,照 MiMo 评测 rubric 一次返回七个维度的做法(提示词里写了「各条独立判断」)。信里 1.1 和 1.2 不调模型,所以信的这次调用只有 1.3;达的各条一次打完;雅的两条一次打完。每条照样单独写一份记录,组的共同回答在 `group-<维度>.json`。`--per-item` 改成每条单独一次调用,是测耦合时的对照:一起判时一条的印象会不会带到别的条上,比一比就知道。judge 看到:全部帧(超过 40 帧均匀抽 40)、缩略图、页面文字(每段标了在第几帧)、滚动记录。帧按 1080px 宽发送。默认 judge 是 `glm-5.3-flash`。
- 1.1 不调模型,按采集结果判。只对生成页判脚本报错:Pudding 原文自己也报错(titletowns 有 "reading 'latitude'"),页面照样能用。
- 1.2 由 `factcheck.py` 判:pi agent 在沙盒里读数据和 `page.txt`(页面全部文字),列出页面上的每个数字和带量的说法,用 python 复算,每条记 ok、wrong 或 unverifiable。有一条 wrong 就算犯了;原文引用了没公开的数据时会是 unverifiable,不算犯。
- 1.3 由 judge 看图判犯没犯,写出犯在哪张图。信的三条犯了任何一条,整页 0 分。
- 达的条目照 MiMo 评测 rubric(`recipes/design/webdev/eval_rubric.py`)的写法打 0–1 分:每条在 rubric 的「打分的分段说明」里有自己的五段描述,先按它定区间,再在区间内取值,写出位置和扣分理由。给不出合法分数或结论的回答记为没判出来,不当 0 分。雅也打 0–1 分,但先给 judge 看 rubric 里每条的典型案例:`runs/evidence/<篇>/<版本>/frames/` 里的一帧、分数和理由,标明「不是要评的页面」,再给要评的页面,judge 照着案例定档。案例取自人工标注过的页面,算雅和标注的一致率时排除这几篇。原来的组内挑选(MiMo 的 group pick)比不出来,多数轮次判「无明显差别」,已经删掉。
- 记录在 `runs/judge/page/<篇>/<版本>/<条目>.json`,带 judge 模型、提示词和 rubric 的哈希、采集版本;已有的跳过。
- 调用失败(重试后仍失败)不写记录,打出 FAILED,重跑同一命令会补上;额度不够时整批停下。

### 分析(`judgestats.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.judgestats stats runs/judge/glm-a          # 各版本平均分、条目两两相关、VIF
PYTHONPATH=src .venv/bin/python -m report_gepa.judgestats agree runs/judge/glm-a runs/judge/glm-b   # 两次判分的一致率
PYTHONPATH=src .venv/bin/python -m report_gepa.judgestats human runs/judge/glm-a labels/round1     # 和人工标注的一致率
```

- 耦合:两条分数的 Spearman 相关超过 0.7 就标出来;再把每条对其余各条做回归,VIF 超过 5 说明这一条大部分能由别的条目说出来。相关矩阵的特征值看这些条目实际上有几个独立方向。
- 一致率:同一个 judge 判两次(重测),或换一个模型判(跨模型),逐条算 Spearman、平均绝对差、落在同一个分数区间的比例、按区间算的加权 kappa。
- 和人比:标注是「原文 vs 指南版」哪边好。逐条看这一条单独挑出的高分页面和人选的是否一致,再看每层,和按 rubric 合成的页面分(信犯了任何一条就是 0,否则是达的平均分);雅的两两比较也和同一批标注比。


## GEPA(`src/report_gepa/optimize.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.optimize runs/gepa/<名字> [--max-calls 120] [--val 8] [--train 19] [--minibatch 3] | tee runs/gepa/<名字>.log
```

用 `gepa==0.1.4` 优化写页面 agent 的系统提示词 `{"guide": ...}`,从 `guides/seed.md` 起步。

- **数据**:Pudding 里原文是滚动长文的 43 篇。人工标注过的 16 篇是测试集,GEPA 不碰;其余 27 篇按 `--seed` 分成验证 8 篇(帕累托集)和训练 19 篇(反思用的小批量)。划分写在 `<run>/split.json`。
- **一次 rollout** = 一篇数据 + 一版指南:pi agent 写页面(固定任务说明要求写英文、可以用 `pageshot` 看自己的页面),采集截图,deepseek 判:
  - 信:只判 1.1,犯了整页 0 分;1.2 和 1.3 不做(1.3 靠看截图目测柱长,会量错,一次量错就是整页 0 分)。
  - 达:2.x 每条 0–1 分,一次调用。
  - 雅:3.1、3.2 每条 0–1 分,一次调用,照 rubric 里的典型案例定档。
  - 分数 = 达和雅各条的平均(等权)。
- **反馈**:每条的分数、位置和理由。
- 每次 rollout 的页面、截图、判分都在 `<run>/rollouts/<指南哈希>/<篇>/`;已有的复用,断了重跑同一命令。

## 写页面 agent 的浏览器(`agent/bin/pageshot`)

沙盒(`agent/sandbox.sh`)里打开了本地回环,只读挂上 Chromium、本项目的 Python 环境和 `src/`,`pageshot index.html` 用 `capture.py` 像读者一样滚动截图,输出 `_shots/frames/NN.jpg`、`_shots/thumb.jpg` 和 `evidence.json`;仍然上不了外网。`gen.mjs` 把模型声明为能收图片,read 工具才会把截图交给模型。2026-10-20 cookies 上试过:没有浏览器时一页 62 步、16 分钟、输入 250 万 token;有了以后 21–34 步、4.5–7.5 分钟、输入 9–26 万 token。agent 会跑 pageshot,但不一定把截图看全(一页的条形图没画出来,它只看了 2 张截图)。

## 调用失败和重试(`src/report_gepa/llm.py`)

deepseek 经中转站时,同一个大的图文请求有时几秒内返回 400「模型请求失败」或正文为空的 stop(同一请求成功和失败时 prompt token 数不同,像是分到了不同后端),有时 524 超时。和截图内容、图片张数、`max_tokens` 都无关(2026-10-20 逐项排除过)。正文为空也算没完成,和其他失败一起最多重试 5 次;加上以后 v5 一轮判分没有一次失败。

## 数据

数据放 Google Drive(qfy2518418912@gmail.com)「我的云端硬盘」根目录,只有本人账号能打开。

| 文件 | 内容 | 解压到 |
|---|---|---|
| [`pudding-data.tar.xz`](https://drive.google.com/file/d/1rN-754lKNpakj4Y7bAYHzhZOzSrvQVph/view)(81 MB,解压后 617 MB) | `data/pudding/`:56 篇的数据文件和 `manifest.jsonl`(2026-10-20) | `report-gepa/data/` |

| `mock-data.tar.xz`(15 MB,解压后 150 MB;待上传) | `data/mock/`:48 份明细 CSV、造数脚本、规律和 `manifest.jsonl`(2026-10-21) | `report-gepa/data/` |

```sh
tar -xJf pudding-data.tar.xz -C report-gepa/data/
tar -xJf mock-data.tar.xz -C report-gepa/data/
```

不从 Drive 取也能重做:`report_gepa.pudding` 从 the-pudding 的公开仓库重新克隆生成同样的 `data/pudding/`(见上面「Pudding 数据」)。

还没上传:`runs/`(生成的页面、截图、证据、judge 记录)和 `labels/`(人工标注)。
