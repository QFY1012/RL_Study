# 交接(data-collection,2026-10-17)

接手前先读 `README.md`(流程和每条规则的来由)和 `PLAN.md`(已完成和待做)。这份只写:现在在哪、没做完什么、下一步怎么做。

## 现在的状态

分支 `claude/peaceful-brown-rtls5f`,最新两个提交:

- `08e6808` 页面渲染不出来的问题(时钟、WebGL、关脚本后的 canvas/视频、视口相关的显示、分节、框的量法、样式改写丢东西、重叠排除)。
- `38d9238` 生成版质量差里属于我们的错(都是通用规则,不针对某个网站):
  - 压在一节上、却不在任何一节里的层算那一节的(`data-part`)。
  - 给模型的图都和页面上一样:视频、canvas、画出来的图单独截;SVG 单独渲染不对就给截图;看不见的图不算。
  - 页面用 `role="img"` 或 `aria-hidden` 标注的示意图整个是一张图。
  - 脚本开着时做的事之后都推一段页面时间(stripe 示意图缩成 1/56 的根因)。
  - 给模型网格和字号层级,原版对齐网格而生成版没对齐就打回(`grid`)。

验证过的:

- vercel #1 的集装箱压住生成内容:现在那一层归 #1,#1 的绳子穿过导航栏,按重叠规则排除。
- raycast 键盘:SVG 单独渲染差 53%,改给截图。
- stripe 第 3 节:163 条标签变成 8 张图。
- stripe 示意图大小:恢复成 1。
- 跨域 canvas 的固定:画面完整。
- vercel #2、#4 和 framer #11 的新结果对齐正确。

## 正在跑的(交接时没跑完)

`v15`:18 个网站,原来 6 个加从 Mobbin 收录的产品里挑的 12 个(linear、notion、figma、supabase、resend、webflow、loom、dropbox、attio、posthog、mercury、ramp)。网址列表在 `/home/user/ui-rl-scratch/data-collection/sites-v15.txt`,日志 `v15.log`,结果 `v15/<host>/`。

交接时的结果:

| 网站 | 可用的对 |
|---|---|
| vercel、cal、raycast、resend、figma、linear、supabase | 2/2 |
| framer、notion、arc | 1/2 |
| 其余(stripe、webflow、loom、dropbox、attio、posthog、mercury、ramp) | 还在跑 |

注意:这些数据在云端容器的临时目录里,会话结束就没了。按 `CLAUDE.md` 应该传到 Google Drive,这个会话没有 Drive 的权限,没传。接手后要么重跑:

```sh
source ~/.config/ui-rl/judge.env
node scripts/run.mjs <out> --list sites.txt 2>&1 | tee <out>.log
```

要么在还开着的容器里把 `/home/user/ui-rl-scratch/data-collection/` 打包上传。

API key 只在 `~/.config/ui-rl/judge.env`(`JUDGE_URL=https://openoneapi.com/v1/chat/completions`、`DEEPSEEK_API_KEY`),不进仓库;新环境要重新建这个文件。

## 下一步(按优先级)

1. **逐对看 v15 的图**(`v15/<host>/pairs/<i>-side.png`)。我只看了 vercel #2、#4 和 framer #11。要看的是:
   - 生成版里有没有原版的东西压着或漏出来;
   - 有没有缝;
   - 图有没有错(给的图和页面上不一样)。
   
   每发现一类问题,先在页面上复现、找到原因,再改成对所有网站都成立的规则。

2. **resend、ramp 的页面停不下来**:日志里 `still changing when its sections are hidden and shown, after 4 rounds`(resend 照样出了 2/2,但原版图和换节后的页面可能对不上)。

   已查到的(resend,`load` 之后脚本已关,隔 3 秒截两张整页图):首屏右边 x≈800、y≈236–709 那块在变,那里有两个 CSS 动画还是 running:`div.open-scale-up-fade` 和 `div.animate-webgl-scale-in.fade-in`。也就是 `freeze` 停了动画以后,又有动画开始跑。下一步先确认它们是什么时候出现的:
   - 是 `freeze` 之后才建出来的(比如藏节再显示时 `display` 从 none 恢复,CSS 动画会从头开始);
   - 还是 `freeze` 没找到它们(在 shadow root 或 iframe 里)。

   确认后改成任何时候建出来的动画都停在同一个状态,而不是只停 `freeze` 那一刻已有的。

   其他不靠脚本也会动的东西也要一起看:
   - 动图(GIF、WebP、APNG);
   - SVG 的 SMIL 动画(`<animate>`);
   - `freeze` 没管到的 CSS 动画(比如在 shadow root 外的 iframe 里)。
   
   它们会让 `page.png` 和每次截图都不一样,也会撑大量出的框。查法:加载完隔几秒截两张整页图,逐带比,找出变的地方,看那里是什么元素(上面 resend 的结果就是这样查出来的)。根本的改法是让这些东西也停在一个状态:
   - 动图换成它的一帧,像 `pin` 那样用 CSS `content` 固定;
   - SVG 动画用 `svg.pauseAnimations()` + `setCurrentTime`。

3. **没有无障碍标注的示意图还是拆成标签**(cal 的日历、stripe 连接图的下半部分、raycast 一节的整个应用界面)。只靠 ARIA 覆盖不全。通用的办法是用看图的模型认:
   - 把候选节截出来,连同文字条目给模型,问哪些文字是图里的标签;
   - 再按 DOM 把这些标签归到不含正文的最近祖先,截成一张图。
   
   先用 v15 统计没标注的有多少,再决定做不做。

4. **模型本身**:flash 模型给了字号体系也不一定照着用(vercel #4 的标题用了约 20px,页面其他节都是 56px)。这是设计好坏本身,不算我们的错,但如果想要更好的生成版,换更强的模型(`GEN_MODELS`)。这由人决定。

5. `PLAN.md` 里其余的待做:富文本的两种样式、CSS mask 图标、iframe、伪元素装饰(arc 的波浪线)、标签可靠性。

## 调试的办法

改代码前先在页面上复现。我用的是一个常驻的 node 进程:

- 开一个浏览器,用 `browser.mjs` 的 `load` 加载好页面,一直留着;
- 用 HTTP 发 JS 片段,在 node 侧拿 `(page, ctx)` 跑;
- 每次运行前把 `scripts/` 整个拷到新目录再 import,这样改过的模块之间的相互 import 也是新的。

一个页面加载一次就能反复试,不用每次等 1–2 分钟。这个工具在临时目录里,会话结束就没了,需要时照这个思路重写一个(几十行)。

查页面行为时,对照"脚本开着、真实时间"的普通加载(`page.goto` 后等几秒)最快:两边不一样,就是我们的加载过程造成的(stripe 的 1/56 就是这样查出来的)。
