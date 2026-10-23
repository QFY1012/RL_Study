# report-bench

比各家 AI 系统「把一份数据做成数据报告网页」做得怎么样的 benchmark。

- 开放赛道:模型、agent、整套流程都行,只要按格式交页面;比的是整个系统。不设基线。
- 每题给 `data/` 下一张或几张原始数据表(csv),和一句说明数据是什么的题目;页面一律用英文。
- 141 题:The Pudding 的 93 篇(真实数据,`report-gepa/data/pudding` 47 篇、`pudding-web` 46 篇)和 48 份 mock 明细数据(24 类业务各 2 份,`report-gepa/data/mock`)。96 题是一张表,其余 2 到 8 张。

## 题目(`tasks.json`)

每题一项:`id`、`source`(`pudding`、`pudding-web`、`mock`)、`tables`(那份数据里给哪几张表,相对它在 `report-gepa/data/<source>/<id>/` 下的路径)、`title`。

- 只给原始数据表,为某张图算好的中间表(按年汇总、百分比、排名、图表坐标)不给;一篇文章的几张原始表(比如电影、演职人员、制片公司各一张)都给。同一份数据重复的(`docs/` 和 `src/` 下各一份)只给一份。json 不给。
- 没收的 Pudding 文章:只有中间表的(birth-control、neighborhoods、prosecutors、hater、hip-hop-words、the-office、comics、incarceration、words-against-strangers),只有对照表、没有数据的(airports),数据不全的(same-name 只有一个州),和 music-bubble 是同一份数据的(music-map),不是能写报告的数据的(menu-collection 的菜单图片尺寸、cloud-zoo 的动物园直播列表、science_etc_1 的论文文本片段),以及数据只有 json 的。
- 题目只说数据是什么,不说结论:原文标题常常就是结论(「Women's Pockets are Inferior」),不用。

## 生成题目目录(`src/report_bench/build.py`)

```sh
cd report-bench && PYTHONPATH=src python3 -m report_bench.build out | tee out-build.log
```

- `out/tasks/<id>/`:`data/<表>.csv`(tsv 转成 csv,utf-8,文件名里的 `%20` 之类还原)和 `task.json`(`id`、`title`、`files`、`instruction`)。这是发给参赛者的全部东西。一共 751 MB,最大的是 mow(250 MB)。
- `out/tasks.jsonl`:每题的来源、题目和每张表的行列数、大小。
- `out/answers/<id>/findings.json`:mock 题里预埋的规律,打分用,不发给参赛者。

`instruction` 是 `TASK.md` 的全文,每题一样。

## 提交

每个系统一个目录,每题一个 `index.html`:`submissions/<系统>/<id>/index.html`。页面要离线能打开,css、脚本、数据都写在文件里(见 `TASK.md`)。

## 打分

还没写。打算:用 report-gepa 的 judge(1.1 打不开整页 0 分;表达 2.x、美学 3.x 各条 0–1),mock 题另加一项,逐条看页面有没有讲出 `findings.json` 里的规律。

## 数据

`out/` 不进仓库,上传 Google Drive 后在这里写位置和取回方法。
