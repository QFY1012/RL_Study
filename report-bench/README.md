# report-bench

比各家 AI 系统「把一份数据做成数据报告网页」做得怎么样的 benchmark。

- 开放赛道:模型、agent、整套流程都行,只要按格式交页面;比的是整个系统。不设基线。
- 每题给一张表 `data.csv` 和一句说明数据是什么的题目;页面一律用英文。
- 76 题:The Pudding 的 28 篇(真实数据,`report-gepa/data/pudding` 21 篇、`pudding-web` 7 篇)和 48 份 mock 明细数据(24 类业务各 2 份,`report-gepa/data/mock`)。

## 题目(`tasks.json`)

每题一项:`id`、`source`(`pudding`、`pudding-web`、`mock`)、`table`(Pudding 那份数据里用哪张表)、`title`。

- 只收数据本来就是一张表的 Pudding 文章;多张表的不拆不拼。titletowns、pockets 另带的 json 不给。menu-collection 的表只有菜单图片的宽高和页码,没收。
- 题目只说数据是什么,不说结论:原文标题常常就是结论(「Women's Pockets are Inferior」),不用。

## 生成题目目录(`src/report_bench/build.py`)

```sh
cd report-bench && PYTHONPATH=src python3 -m report_bench.build out | tee out-build.log
```

- `out/tasks/<id>/`:`data.csv`(tsv 转成 csv,utf-8)和 `task.json`(`id`、`title`、`instruction`)。这是发给参赛者的全部东西。
- `out/tasks.jsonl`:每题的来源、题目和表的行列数、大小。
- `out/answers/<id>/findings.json`:mock 题里预埋的规律,打分用,不发给参赛者。

`instruction` 是 `TASK.md` 的全文,每题一样。

## 提交

每个系统一个目录,每题一个 `index.html`:`submissions/<系统>/<id>/index.html`。页面要离线能打开,css、脚本、数据都写在文件里(见 `TASK.md`)。

## 打分

还没写。打算:用 report-gepa 的 judge(1.1 打不开整页 0 分;表达 2.x、美学 3.x 各条 0–1),mock 题另加一项,逐条看页面有没有讲出 `findings.json` 里的规律。

## 数据

`out/` 不进仓库,上传 Google Drive 后在这里写位置和取回方法。
