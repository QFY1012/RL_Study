# data-collection

为通用的页面 judge 造偏好数据:把真实网站的一节换成模型按同样内容重新设计的一节,两版放在同一页里、同样条件下截图,成对作为 (原版, 生成版)。

## 流程

| 步骤 | 脚本 | 产出 |
|---|---|---|
| 冻结页面 | `scripts/snapshot.mjs <url> <dir>` | `page.har.zip`(页面加载的所有响应)、`page.html`(JS 执行后的 DOM,去掉脚本,每节标 `data-sec`)、`live.png`、`sections.json`(设计 token、每节的位置和内容、内联 SVG 转成的独立文件) |
| 重新设计 | `scripts/generate.mjs <dir> [count]` | `gen/<i>.html`、`gen/<i>.json`(提示词、模型、用量) |
| 离线渲染 | `scripts/render.mjs <dir>` | `render/orig.png`、`render/<i>.png`、`render/<i>.json`(位置和检查) |
| 检查和裁切 | `python3 -I scripts/pairs.py <dir>` | `pairs/<i>-orig.png`、`pairs/<i>-gen.png`、`pairs/<i>-side.png`、`pairs/report.json` |

`scripts/run.sh <out-root> <url>...` 依次跑完上面四步,每个网站一个目录 `<out-root>/<host>/`。

要点:

- 生成模型只拿到内容(文字、图片、插图、图标,按阅读顺序)和页面的设计 token(字体、颜色、内容宽度、上下两节的背景),拿不到原版的 HTML 和布局。所以两版的差别只在设计决策上。
- 渲染时所有请求都从 HAR 回放,HAR 里没有的请求直接中止;文档本身用 `page.html`。原版和生成版走同一条路径。
- 生成的节放进一个 shadow root,宿主元素占原节的位置:两边的 CSS 互不影响,字体、颜色这些继承属性照常从页面传进来。
- 生成版和原版的高度差取整到整像素,否则下面整页会重新栅格化,隔离检查过不了。

## 检查

| 检查 | 在哪 | 含义 |
|---|---|---|
| 保真 | `pairs/report.json` 的 `fidelity` | 离线渲染的原版和在线截图有多少行像素不同 |
| 隔离 | `above_rows_differing` / `below_rows_differing` | 换掉的那节上方应完全不变,下方平移高度差后应完全不变 |
| 内容 | `missingText` / `missingImages` / `brokenImages` | 每段文字、每张图都要出现,图要加载成功;被原版截断的文字只看开头 |
| 破版 | `overflow` / `fontsMissing` | 超出宿主宽度的元素数、没加载上的字体 |

## 依赖

- `npm install`(playwright-core,用 `/opt/pw-browsers/chromium`)
- Python 3 和 Pillow(`pairs.py`)
- 模型的地址和 key 来自 `~/.config/ui-rl/judge.env`(`JUDGE_URL`、`JUDGE_MODEL`、`DEEPSEEK_API_KEY`),`GEN_MODEL` 可以换生成模型。

## 数据

产出全是数据,不进 git。测试时放在 `/home/user/ui-rl-scratch/data-collection/`。
