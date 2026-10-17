# data-collection

为通用的页面 judge 造偏好数据:把真实网站的一节换成模型按同样内容重新设计的一节,两版在同一个运行中的页面里先后截图,成对作为 (原版, 生成版)。

## 流程

| 步骤 | 脚本 | 产出 |
|---|---|---|
| 录制 | `scripts/record.mjs <url> <dir>` | `page.har`(页面的全部请求和响应)、`live.png`(参考用)、`sections.json`(设计 token、每节的位置和内容、内联 SVG 转成的独立文件) |
| 回放 | `scripts/render.mjs <dir>` | `replay.json`(每节在回放里是否和录制时一样)、`render/orig.png`、`render/orig.json` |
| 重新设计 | `scripts/generate.mjs <dir> [count]` | `gen/<i>.html`、`gen/<i>.json`(提示词、模型、用量) |
| 换节截图 | `scripts/render.mjs <dir>`(再跑一次) | `render/<i>.png`、`render/<i>.json`(位置、高度和检查) |
| 放不进框的重写 | `scripts/generate.mjs <dir> --revise`,再 `render.mjs` | 内容伸出框的节把伸出多少告诉模型重写,最多 `ROUNDS` 轮 |
| 检查和裁切 | `python3 -I scripts/pairs.py <dir>` | `pairs/<i>-orig.png`、`pairs/<i>-gen.png`、`pairs/<i>-side.png`、`pairs/report.json` |

`node scripts/run.mjs <out-root> <url>...`(或 `--list <文件>`,一行一个 URL)对每个网站跑完上面几步,每个网站一个目录 `<out-root>/<host>/`,日志在 `<out-root>/<host>.log`,同时带着网站名打印到终端。

- `JOBS`(默认 20):同时处理的网站数,也就是同时在等模型的网站数。一个网站选中的几节同时请求模型,遇到 429、5xx 或断线会隔 10s、30s、60s 重试。
- `BROWSER_JOBS`(默认 4):录制、回放、裁切这些浏览器步骤同时最多跑几个。它们吃 CPU,机器是 4 核。
- `COUNT`(默认 2):每个网站换几节。
- `ROUNDS`(默认 2):放不进框时最多让模型改几轮。
- `STEP_SECONDS`(默认 300):浏览器步骤的时间上限,超过就停掉,这个网站算失败。有的页面太重(比如没有显卡时用 CPU 画的大 WebGL 场景),直接丢掉,不为它等。

## 页面怎么跑

页面一直带着自己的脚本跑,录制和回放用同一套加载过程(`scripts/browser.mjs`),把会让两次运行不一样的东西都固定住:

- 时钟从固定时刻开始,加载完停在固定时刻(Playwright 的 `page.clock`);停住以后页面的定时器和动画帧都不再走,页面在截图之间保持不动。
- `Math.random` 和 `crypto.getRandomValues` 用固定种子,带随机参数的请求也和录制时一样。
- `IntersectionObserver` 对每个元素都报"在屏幕上",`content-visibility` 一律 `visible`:整页截图要的是整页,不是读者滚到的那一屏。
- 视口、语言、时区、配色、减弱动效都固定。
- cookie 横幅、聊天窗、弹窗和不在顶部的固定元素藏起来(`display:none`),不从文档里删:页面的框架(比如 React)以后还会去找这些节点,找不到整个页面就崩了。
- 加载完以后让时钟一次走 2 秒,直到页面高度和可见元素数不再变,再停住:晚开始的入场动画(比如滚动后才开始淡入的整页内容)也要走完。
- 回放时所有请求都从 HAR 回答,HAR 里没有的直接中止。录制时重定向回自身的响应(服务器先设 cookie 再给页面)会删掉,否则回放会原地打转。
- 视频和音频是分段请求的,HAR 存下的是一段段,回放答不上:录制时整个下载到 `media/`,回放时从那里整个给页面。

回放后重新读一遍页面,每节的高度和内容(文字、图片、链接)要和录制时一样才算可用,`generate.mjs` 只从可用的节里挑。每次打开内容都不一样的节(随机轮换的卡片、打乱顺序的评价)在这里被筛掉。

原版和每个生成版在同一个回放页面里截:先截原版,再把一节换成生成版截图,截完换回去,换下一节。生成版的图是原版截图只把那一节的框换成生成版渲染出来的像素:框外就是原版自己的像素,哪怕页面的脚本对换节有反应(比如别处的 canvas 被清空),也不会进到图里。

- 生成模型只拿到内容(文字、图片、插图、图标,按阅读顺序)和页面的设计 token(字体、颜色、内容宽度、上下两节的背景),拿不到原版的 HTML 和布局。
- 生成的节放进一个 shadow root,宿主元素占原节的位置:两边的 CSS 互不影响,字体、颜色这些继承属性照常从页面传进来。
- 生成的节放在一个和原版一样大的框里:提示里给出原版的宽和确切的高,宿主元素就是这个高度(它是 grid,片段的外框拉伸填满)。框里的空间怎么分是模型自己的设计;内容伸出框的上下边(包括被裁掉的)就把伸出多少告诉模型重写。两版尺寸相同,高度不能当作区分两版的捷径,下面的页面也不动。
- 视频和 canvas 在读页面时截成图(JPEG 资源),当作插图交给模型。
- 被页面别处的元素盖住的节(比如别处绝对定位过来的图)不可用:换掉这节以后那个元素还在原位,会压在新的一节上。按面积算:别处画得出东西的元素(文字、图、背景、边框)盖住这节超过 3% 才算,不画东西的透明层和读屏用的隐藏文字不算。

## 检查

| 检查 | 在哪 | 含义 |
|---|---|---|
| 回放一致 | `replay.json` | 每节在回放里的高度和内容是否和录制时一样、有没有被别处的元素盖住;不合的节不拿去生成 |
| 页面反应 | `pairs/report.json` 的 `above_rows_differing` / `below_rows_differing` | 换节后框外有多少行变了;只作参考,图里框外用的是原版像素 |
| 内容 | `missingText` / `missingImages` / `brokenImages` | 每段文字、每张图都要出现,图要加载成功;被原版截断的文字只看开头 |
| 放进框 | `render/<i>.json` 的 `spill` / `fits` | 内容伸出框上下边多少像素(包括被裁掉的),0 才算放进去 |
| 破版 | `overflow` / `fontsMissing` | 超出框左右的元素数、没加载上的字体 |

`pairs/report.json` 里每对的 `failed` 列出没过的检查,空的才可用。

## 依赖

- `npm install`(playwright-core)
- Google Chrome:Playwright 自带的 Chromium 不含 H.264/AAC 解码器,放不了大多数网站的 MP4 视频。默认路径 `/opt/chrome-stable/opt/google/chrome/chrome`,别处的用 `CHROME` 指定。安装(不需要 apt 的依赖):
  ```sh
  curl -LO https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x google-chrome-stable_current_amd64.deb /opt/chrome-stable
  ```
- Python 3 和 Pillow(`pairs.py`)
- 模型的地址和 key 来自 `~/.config/ui-rl/judge.env`(`JUDGE_URL`、`JUDGE_MODEL`、`DEEPSEEK_API_KEY`),`GEN_MODEL` 可以换生成模型。

## 数据

产出全是数据,不进 git。测试时放在 `/home/user/ui-rl-scratch/data-collection/`。
