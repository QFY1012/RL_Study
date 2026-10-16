# 书网格版组件库(gen/book)

按 Müller-Brockmann《平面设计中的网格系统》的做法重做的一套组件和检查,和 `gen/app`、`gen/design.md`、`gen/components.md` 并排放,原来的文件一个都没改。

## 网格怎么推出来

- 先定正文:14px 字、24px 行距。纵向的一切都是整行:这 24px 就是基线网格的「行」。
- 场 = 6 行 = 144px,场与场之间空 1 行(24px),所以场线相隔 168px,从页头上边算起。
- 节从场线开始,高度是整数个场(节与节相隔 192px)。
- 横向沿用原来的 12 栏:每栏 74px、栏间 24px,共 1152px。节标题占左 3 栏,内容占右 9 栏。
- 图(截图、图表)从场线开始,高度是整数个场:1 场 144、2 场 312、3 场 480。

## 文件

| 文件 | 内容 |
| --- | --- |
| `app/` | `gen/app` 的副本,改了 `src/components/report/` 里的组件:行高全是 24 的倍数,图占整场,`grid.ts` 导出 `LINE`、`FIELD`、`PITCH`、`fields(n)` |
| `design.md` | 书网格版的设计规范(新增 A8「图占场」;纵向只许 `leading-12`、`gap-12` 这类整行的类) |
| `components.md` | 书网格版的组件说明 |
| `check.mjs` | `bookOffenders(draw)`:行高、每行字落在 24px 行线上、图占整场 |
| `shoot.mjs` | 用 `book/app` 渲染一个工作区并检查 |

## 用法

```bash
cd ui-rl/gen
node book/shoot.mjs <workspace>                  # 渲染 + 原来的检查 + 书网格检查
BOOK_OVERLAY=1 node book/shoot.mjs <workspace>   # 另写 book-grid.png:把检查画在页面上
```

`<workspace>` 和 `scripts/shoot.mjs` 用的一样(`Page.tsx`、`data.json`、`assets/`)。`shoot.mjs` 在运行期间把 `<workspace>/app` 链到 `book/app`,跑完就删;工作区里已经有真的 `app/` 目录时拒绝运行。书网格的问题以 `「书网格」` 写进 `checks.json`。

`book-grid.png` 里:淡红是 12 栏,淡蓝是场,细蓝线是 24px 的行,绿框是量过的图,红框加编号是出问题的字或图。

## 现状

- f15 网格页(f15-grid)用书网格库渲染,原检查和书网格检查全部通过。
- 用旧规范生成的 16 张试点页,组件本身都过;不过的只是页面代码里按旧规范写的东西:`leading-9` 的结论、`items-baseline` 的数字行、给 FigureText 加的 `mt-2`。
- `generate.mjs` 还是用 `gen/app` 和 `gen/components.md`,没接到书网格库上。
- 不同字号的数字在一行里顶对齐,字的基线会差几 px(行框都在行线上,字形不在同一条基线上)。
