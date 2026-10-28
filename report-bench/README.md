# report-bench

比各家 AI 系统「把一份数据做成数据报告网页」做得怎么样的 benchmark。

- 开放赛道:模型、agent、整套流程都行,只要按格式交页面;比的是整个系统。不设基线。
- 每题给 `data/` 下一张或几张原始数据表(csv),和一句说明数据是什么的题目;页面一律用英文。
- 196 题:The Pudding 的 148 篇(真实数据,`report-gepa/data/pudding` 47 篇、`pudding-web` 51 篇、`pudding-repo` 24 篇、`pudding-js` 15 篇、`pudding-merge` 11 篇)和 48 份 mock 明细数据(24 类业务各 2 份,`report-gepa/data/mock`)。127 题是一张表,其余 2 到 8 张。

## 题目(`tasks.json`)

每题一项:`id`、`source`(`pudding`、`pudding-web`、`pudding-repo`、`pudding-js`、`pudding-merge`、`mock`)、`tables`(那份数据里给哪几张表,相对它在 `report-gepa/data/<source>/<id>/` 下的路径)、`title`,可选的 `dedupe`(哪几张表去掉完全相同的行:只给自己重复了很多遍的对照表用,比如 similarity 的歌名表同一首歌列了 27 遍;别的表里相同的行多半是真的,比如两次一样的猜测)。

- 只给原始数据表,为某张图算好的中间表(按年汇总、百分比、排名、图表坐标)不给;一篇文章的几张原始表(比如电影、演职人员、制片公司各一张)都给。同一份数据重复的(`docs/` 和 `src/` 下各一份)只给一份。json 只给一条条记录结构的,转成 csv(文件名 `<原名>.json.csv`)。
- 五个 Pudding 来源依次补前面没收的文章:`pudding` 是 the-pudding/data 公开的数据,`pudding-web` 是文章页面加载的数据文件,`pudding-repo` 是文章自己仓库里的数据,`pudding-js` 是构建时打包进 JS 的表(`report_gepa.puddingjs`,收哪几张表写在 `puddingjs.TABLES`,没表头的照文章代码补上列名),`pudding-merge` 是数据在、但不是一张表的(`report_gepa.puddingmerge`,每篇一个配方):散在几百上千个小文件里的合成一张表,文件代表的东西(比赛、电台、期数、人、读音组)成为一列;嵌套的 json 展开成行;放在 pudding.cool 以外的文件照原样取。
- 题目只说数据是什么,不说结论:原文标题常常就是结论(「Women's Pockets are Inferior」),不用。

### 没收的 Pudding 文章(2026-10-25 对网站列表 217 篇逐篇查过,剩 70 篇)

- 不是网页(3):两个 YouTube 视频(The Loneliness Epidemic、queues 那篇)和一个播客(Failures to Act)。
- 只有为图算好的中间表、对照表,或不是能写报告的数据(21):汇总和中间结果(birth-control、neighborhoods、hater、hip-hop-words、the-office、comics、prosecutors、incarceration),平滑后的趋势和计数(big-hair、eating-alone、best-sellers),按年计数(crossword),对照表(airports、millennials 的词表、elections 的网站表),三元图坐标(chyrons),线上实验的汇总状态(infinite 的关卡、birthday-paradox 的分箱),游戏键盘和成绩(words-against-strangers),动物园直播列表(cloud-zoo),论文文本片段(science_etc_1)。
- 数据打包在 JS 里,但读不了或不是数据(11):每格是一串编码数字(teenagers、love-story、invisible-epidemic、judge-my-music 的邻接矩阵),排名矩阵和缺排名的地区表(genre),词向量近邻(text-prediction),只有球员名单(asterisks),动画精灵图(ivf、sesame、dark-patterns),菜单图片的区间(menu-story)。
- 作品本身没有数据集(27):视频和音频(walk、flipbook、lighting-cost、groove、cdmx、language、sampling、waveforms、motifs),插画、随笔和小说(kimchi、love-and-ai、plain、jordans 的鞋子轮廓、wnba-kicks、gifs、rickrolling 只有一个播放量),游戏、工具和模拟(where、emotion-wheel、onions、yard-sale、streaming、deepwork、clocks 的 1440 段视频),只有一二十行(democracy、kpop-survey、crokinole、happy-map 的地图标签)。
- 数据在地图瓦片或做好的图里(6):travel-local、3d-cities-story、city_3d(Mapbox 矢量瓦片,页面只拿得到城市名和坐标);wedding-playlists、oscars_so_mapped、outkast 没加载数据文件、JS 里也没有表,图应该是做好的 SVG 或图片(没逐张核实)。
- 和已收的是同一份数据(2):music-map(music-bubble)、weather-map(heat-records-map)。

## 生成题目目录(`src/report_bench/build.py`)

```sh
cd report-bench && PYTHONPATH=src ../report-gepa/.venv/bin/python -m report_bench.build out [--tasks a,b] | tee out-build.log
```

用 report-gepa 的环境(要 `ftfy`)。`--tasks` 只重建列出的题,其余题的目录和 `tasks.jsonl` 里的行不动,所以只要这几题的来源在 `report-gepa/data/` 下就行(加新题时用)。

- `out/tasks/<id>/`:`data/<表>.csv`(tsv 转成 csv,utf-8,文件名里的 `%20` 之类还原;源数据里 utf-8 被当成 latin-1 或 cp1252 读过一遍的乱码用 `ftfy` 改回来,比如 `fiancÃ©` → `fiancé`,本来就对的文字不动,字节已经丢了的 `�` 改不回来;每一行都是空(空白、NA、NaN、null、None)的列去掉,没有列名、只是行号的列也去掉,是表格软件和 pandas 导出时留下的)和 `task.json`(`id`、`title`、`files`、`instruction`)。这是发给参赛者的全部东西。一共 1.1 GB,最大的是 caption-contest(269 MB)。
- `out/tasks.jsonl`:每题的来源、题目、每张表的行列数和大小;Pudding 题另有 `original`,数据出自的那篇文章的网址。
- `out/answers/<id>/`:打分用,不发给参赛者。mock 题是 `findings.json`(预埋的规律);Pudding 题是 `original.json`(原文的网址、标题、发表年月),原文就是这份数据的人工可视化,可以拿来对照;写完的 Pudding 题另有 `facts.json`:原文作者从这份数据得出的发现,和页面交的 `facts.json` 同一个格式,由 `report_gepa.originals` 写出,逐条对照原文和数据复核过(见 report-gepa 的 README)。

`instruction` 是 `TASK.md` 的全文,每题一样。

## 提交

每个系统一个目录,每题一个文件夹,里面是 `index.html` 和 `facts.json`:`submissions/<系统>/<id>/`。页面要离线能打开,css、脚本、数据都写在文件里;`facts.json` 写页面报告的每个发现(结论和算出它的 pandas 代码,见 `TASK.md`)。

## 打分(`src/report_bench/score.py`)

```sh
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.score submissions/<系统> [--tasks a,b] [--workers 4] [--browsers 2] | tee runs/<系统>.log
```

`score_page` 是给一个页面打分的唯一定义,benchmark、GEPA(`report_gepa.optimize`)和 TF-GRPO(`report_tfgrpo.practice`)都调用它,judge 模型都是 `deepseek-v4.1-flash`,分数可以互相比:

1. `capture.py` 带着数据截屏采集;
2. 信(`trust.py`):1.1–1.3 按顺序判,犯了任何一条整页 0 分,不再往下判;
3. 否则表达 2.x、美学 3.x 各一次 judge 调用,每条 0–1 分;
4. 总分是这些条的平均。

- 每题的页面是 `submissions/<系统>/<id>/`,没有 `index.html` 就记 0 分;数据是这题 `data/` 下的文件。
- 1.3 没给出可用回答、或 judge 回复里有条目没解析出分数,就重问,最多 3 次,次数记在 `trust.json` 和 `judgements.json` 里,重跑时不再问没希望的页面;还没答出来的,结果记 `complete: false`,分数只算答出来的条目。
- 结果在 `runs/<系统>/<id>/`(`evidence/`、`trust.json`、`trust-prompt.txt`、`judgements.json`、`result.json`,重跑时复用)和 `runs/<系统>/scores.jsonl`;`result.json` 的 `feedback` 是信的每处问题、每条的分数和理由,GEPA 反思读的就是它。最后按来源打印平均分。
- mock 题的 findings 召回还没做。

## 评测代码

评测标准只有这一份:report-gepa(GEPA)和 report-tfgrpo 都调用这里的 `report_bench.score.score_page`。用 report-gepa 的环境(`../report-gepa/.venv`,装法见 report-gepa 的 README,要 `pandas`)。典型案例的截图在 `report-gepa/runs/evidence/`。

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

### 打分(`capture.py`、`trust.py`、`facts.py`、`judge.py`、`rubric.py`)

rubric 只有一份:`rubric/judge-dimensions.md`。`rubric.py` 读里面以条目编号开头的表格行:信(1.x)由 `trust.py` 判「犯了 / 没犯」,犯了任何一条整页 0 分;达(2.x)和雅(3.x)由 `judge.py` 每条打 0–1 分;雅的每条另附几个打过分的典型案例。判法照 MiMo 开源打分服务(`recipes/design`)的 query judge 和评测 rubric。

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

#### 信(`trust.py`、`facts.py`)

```sh
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.trust <evidence_dir> <facts.json>
```

页面按 `TASK.md` 交付 `facts.json`:每个发现一条,写 `id`、结论 `claim`、读哪些表 `tables`(变量名对应从页面所在文件夹看的文件路径，如 `data/orders.csv`,用 `pd.read_csv` 原样读)和一段 pandas 表达式 `code`。代码在 report-gepa 的沙盒(`agent/sandbox.sh`,没有网络,只看得到临时工作目录)里用系统的 python3 原样 `eval`,输出按 pandas 默认的打印格式。按顺序判,前一条犯了后面不判:

- 1.1 页面可渲染:看采集结果,打不开、没渲染出文字、卡死的犯;生成的页面脚本报错也犯。Pudding 原文自己也报错(titletowns 有 "reading 'latitude'"),页面照样能用,所以原文只看前一半。
- 1.2 fact 能执行:`facts.json` 读得出来,每条代码在数据上都运行得了。
- 1.3 结论和数据一致:一次模型调用(开推理),拿每条结论、它的代码和代码的输出对照,判一致或不一致;结论说了输出里没有的东西、结论里的数是直接写在代码里而不是从表里算出来的，也算不一致。没给出可用回答记为没判出来,不当没犯。

信只看 `facts.json`,不看网页正文和图。

#### 达和雅(`judge.py`)

```sh
PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.judge page runs/evidence/titletowns/original --items 2.4,2.6,2.8,3.1,3.2 [--per-item]
```

- 达、雅各是一组,每组一次调用,照 MiMo 评测 rubric 一次返回七个维度的做法(提示词里写了「各条独立判断」)。每条照样单独写一份记录,组的共同回答在 `group-<维度>.json`。`--per-item` 改成每条单独一次调用,是测耦合时的对照:一起判时一条的印象会不会带到别的条上,比一比就知道。judge 看到:全部帧(超过 40 帧均匀抽 40)、缩略图、页面文字(每段标了在第几帧)、滚动记录。帧按 1080px 宽发送。默认 judge 是 `glm-5.3-flash`。
- 达的条目照 MiMo 评测 rubric(`recipes/design/webdev/eval_rubric.py`)的写法打 0–1 分:每条在 rubric 的「打分的分段说明」里有自己的五段描述,先按它定区间,再在区间内取值,写出位置和扣分理由。给不出合法分数的回答记为没判出来,不当 0 分。雅也打 0–1 分,但先给 judge 看 rubric 里每条的典型案例:`runs/evidence/<篇>/<版本>/frames/` 里的一帧、分数和理由,标明「不是要评的页面」,再给要评的页面,judge 照着案例定档。案例取自人工标注过的页面,算雅和标注的一致率时排除这几篇。原来的组内挑选(MiMo 的 group pick)比不出来,多数轮次判「无明显差别」,已经删掉。
- 记录在 `runs/judge/page/<篇>/<版本>/<条目>.json`,带 judge 模型、提示词和 rubric 的哈希、采集版本;已有的跳过。
- 调用失败(重试后仍失败)不写记录,打出 FAILED,重跑同一命令会补上;额度不够时整批停下。

### 调用失败和重试(`src/report_bench/llm.py`)

deepseek 经中转站时,同一个大的图文请求有时几秒内返回 400「模型请求失败」或正文为空的 stop(同一请求成功和失败时 prompt token 数不同,像是分到了不同后端),有时 524 超时。和截图内容、图片张数、`max_tokens` 都无关(2026-10-20 逐项排除过)。正文为空也算没完成,和其他失败一起最多重试 5 次;加上以后 v5 一轮判分没有一次失败。


## 数据

`out/` 里除了数据表都在仓库里:`tasks.jsonl`、每题的 `task.json`、`answers/`。数据表(`out/tasks/<id>/data/` 下的 csv,共 1.2 GB)在 Google Drive(qfy2518418912@gmail.com)「我的云端硬盘」根目录的 [`report-bench-10-28.7z`](https://drive.google.com/file/d/1uxr8L_GzOyYAw4HeXxPB_qfnxPVBG-LA/view),只有本人账号能打开。题目是 2026-10-25 从原料重建、修过乱码和空列的 196 题。包里最外层是一个 `report-bench/` 目录,`report-bench/report-bench/out/tasks/<id>/data/` 是数据表;包里的其他文件仓库里都有,而且是更新的版本(包里的 `task.json` 还是旧的 `instruction`),不取。

要 7z(`apt-get install -y p7zip-full`)。只解出 csv(312 个)到一个空的临时目录,再拷进仓库:

```sh
7z x report-bench-10-28.7z -o<临时目录> '*.csv' -r
cp -r <临时目录>/report-bench/report-bench/out/tasks <仓库根目录>/report-bench/out/
```

在云端容器里取:`gcloud auth login --no-launch-browser --enable-gdrive-access` 登录(要用户在浏览器里授权,把验证码贴回来),环境变量 `CLOUDSDK_AUTH_ACCESS_TOKEN` 盖着登录的账号,取令牌时去掉它:

```sh
curl -fL --progress-bar -o report-bench-10-28.7z \
  -H "Authorization: Bearer $(env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud auth print-access-token)" \
  "https://www.googleapis.com/drive/v3/files/1uxr8L_GzOyYAw4HeXxPB_qfnxPVBG-LA?alt=media"
```
