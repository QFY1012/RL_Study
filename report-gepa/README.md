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

## 生成页面(`src/report_gepa/generate.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.generate <report.json> <out_dir> [--guide guide.md] [--n 2]
```

系统提示词是指南(GEPA 优化的对象,不给 `--guide` 时用一句话的种子指南),用户消息是报告 JSON 原文,模型 `deepseek-v4.1-flash`。每一版写出 `<n>.html`、截图 `<n>.png` 和记录 `<n>.json`(指南哈希、结束原因、耗时、token、渲染结果)。回复不完整或没有 HTML 时记为没有交付,不渲染。

2026-10-19 用种子指南在一份产品周报上试过:70 秒,2.2 万输出 token,页面 4,243px 高,没有脚本错误,截图完整。

## 批量生成页面(`src/report_gepa/pagegen.py`)

```sh
PYTHONPATH=src .venv/bin/python -m report_gepa.pagegen data/reports runs/pages --workers 6 --renders 3 | tee runs/pagegen.log
```

和 datagen 同时跑:每 30 秒读一次 datagen 的 `manifest.jsonl`,新写完的报告立刻排队生成;datagen 写出 `split.json` 且排队的页面全部完成后退出。已有记录的页面跳过,断了重跑即可。`--renders` 限制同时打开的浏览器数。

每份报告 4 个页面,来源不同,让标注时好坏的差别不只来自抽样波动:

| 名字 | 指南 | 模型 | 个数 |
|---|---|---|---|
| `seed-ds-1`、`seed-ds-2` | 种子指南(一句话) | deepseek-v4.1-flash | 2,也是 GEPA 的参照页面 |
| `seed-glm-1` | 种子指南 | glm-5.3-flash | 1 |
| `detail-ds-1` | `guides/detailed.md` | deepseek-v4.1-flash | 1 |

`guides/detailed.md` 是让 deepseek-v4.1-flash 自己写的通用详细指南(读懂数据、组织内容、排版、选图表、写文字、写 HTML、自查),不针对任何一份数据,代表「认真写过提示词」的水平。

输出在 `runs/pages/<报告 id>/<名字>.{html,png,json}`。

## 数据

还没有上传。生成完放 Google Drive,到时在这里写清楚位置和取回方法。
