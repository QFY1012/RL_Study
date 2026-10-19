# report-gepa

用 GEPA 优化写报告页面的提示词。计划见 `PLAN.md`。和仓库里其他目录无关,从头写。

## 环境

```sh
python3 -m venv .venv
.venv/bin/pip install gepa==0.1.4 openai==3.35.1 playwright==1.64.0
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

2026-10-19 用 Pudding 风格指南在一份 A/B 实验数据上试过:7.4 分钟、39 步、输入 37.7 万 token、输出 6.2 万 token,页面 7,635px,五张不同的图,数字是 agent 用 python 从数据里算的。那一次 agent 花了很多步在沙盒里找浏览器想自查,之后在任务说明里写明了没有。

## 批量生成页面(`src/report_gepa/pagegen.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.pagegen data/reports runs/pages --workers 6 --renders 3 | tee runs/pagegen.log
PYTHONPATH=src .venv/bin/python -m report_gepa.pagegen data/pudding runs/pudding-pages --workers 5 --renders 3 | tee runs/pudding-pages.log
```

每 30 秒读一次数据目录的 `manifest.jsonl`(每行的 `data` 是数据相对数据目录的路径),新的数据立刻排队;`split.json` 出现且排队的页面全部完成后退出。已有 `record.json` 的页面跳过,断了重跑即可。`--renders` 限制同时打开的浏览器数。

每份数据 5 个页面,来源不同,让标注时好坏的差别不只来自抽样波动:

| 名字 | 指南 | 模型 | 个数 |
|---|---|---|---|
| `seed-ds-1`、`seed-ds-2` | `guides/seed.md`(一句话) | deepseek-v4.1-flash | 2,也是 GEPA 的参照页面 |
| `seed-glm-1` | `guides/seed.md` | glm-5.3-flash | 1 |
| `detail-ds-1` | `guides/detailed.md` | deepseek-v4.1-flash | 1 |
| `pudding-ds-1` | `guides/pudding.md` | deepseek-v4.1-flash | 1 |

`guides/detailed.md` 是让 deepseek-v4.1-flash 自己写的通用详细指南,代表「认真写过提示词」的水平;`guides/pudding.md` 照 The Pudding 的可视化叙事写(问题当标题、一节一个发现配一张专门画的图、图上直接标注),代表我们想要的方向。`guides/editorial.md` 是杂志专题风格,只试过,没进批量。

## Pudding 数据(`src/report_gepa/pudding.py`)

```sh
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/the-pudding/data ~/the-pudding/data
PYTHONPATH=src .venv/bin/python -m report_gepa.pudding ~/the-pudding/data data/pudding runs/pudding-originals | tee runs/pudding.log
```

从 The Pudding 公开的数据仓库(MIT 许可,40 个目录)里挑 20 个:页面主要由这份数据构成、静态截图看得懂(kidz-bop、boybands、stand-up 打开是一个开始按钮,截图只有封面,没选)、数据不超过 70MB。每个复制 csv/tsv/json 和 README 到 `data/pudding/<名字>/`,README 里指向原文的行删掉,让任务是「用这份数据做报告」而不是「回忆这篇文章」。原文用同样的方式整页截图到 `runs/pudding-originals/<名字>.png`(只等 DOM 加载完,最高 30000px),当标杆。

## 数据

还没有上传。生成完放 Google Drive,到时在这里写清楚位置和取回方法。
