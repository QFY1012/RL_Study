# report-tfgrpo

用 Training-Free GRPO(arXiv 2510.08191)给写报告页面的 agent 学一份经验清单。照官方实现做:`TencentCloudADP/youtu-agent` 的 `utu/practice/` 和 `utu/prompts/practice/experience.yaml`。

生成页面、截图采集、judge 和 rubric 都直接调用 `report-gepa`(`report_gepa.generate`、`capture`、`judge`、`rubric/judge-dimensions.md`),这里只有学习的循环和它的四个提示词。

## 和 GEPA 的区别

GEPA 改写整份指南,每一版都要和父版本比分数,决定留不留,所以每个页面要一个能跨版本比较的分数。Training-Free GRPO 不改指南,只往后面接一份经验清单;没有去留检验,只需要知道同一份数据的几个页面里谁好谁差。雅本来就只能组内比较,正好合用。

## 一步

1. **分组生成**:一批 `--batch` 篇数据,每篇用「基础提示词 + 当前经验清单」写 `--group` 个页面(默认 3 个),agent 是 report-gepa 的 pi agent,沙盒里有 `pageshot` 可以看自己的页面。
2. **reward**:每个页面截图采集后,deepseek 按 rubric 判,和 GEPA 的分数完全一样,两边的结果可以直接比:
   - 信:只判 1.1(采集结果),犯了 reward 为 0。1.2 和 1.3 不做(同 GEPA)。
   - 达:2.x 每条 0–1 分,一次调用。
   - 雅:3.1、3.2 每条 0–1 分,一次调用,照 rubric 里的典型案例定档。
   - reward = 达和雅各条的平均(等权)。
3. **单页总结**:LLM 看每个页面的截图、文字和两个分数:表达(达各条平均)、美学(雅各条平均),不给条目名和 judge 的理由,写出它的设计决定、得分和扣分在哪。
4. **组内优势**:LLM 比较同一篇的几个页面的总结和 reward,提炼最多 `--per-story` 条经验(默认 1 条,同官方数学配置);一条经验要有前提才成立时写成「当〈条件〉时,〈做法〉」。
5. **组更新**:每篇的新经验和现有清单比,决定 ADD / UPDATE / DELETE / NONE。
6. **批更新**:把这一批所有操作合成净效果,改出新的经验清单,下一步就用它。

经验清单接在基础提示词后面:「写页面之前,先仔细读懂下面这些经验,并照着做:[0]. …」。

照官方实现核对过(`TencentCloudADP/youtu-agent` 的 `utu/practice/experience_updater.py`、`utu/prompts/practice/experience.yaml`、`configs/practice/math_reasoning.yaml`)。学习目标照官方配置写成一句话,不附评分标准;单条总结不给评语,官方提示词留了 critique 的位置,但数学和网页搜索两个实验的打分程序都把它设成空(`reasoning: None`)。经验写法照官方:「经验名称:一句简短描述」,有前提时写成「当〈条件〉时,〈策略〉」;官方没有字数上限。

和官方不同的地方:

| 官方 | 这里 | 原因 |
|---|---|---|
| 和标准答案比,对 1 错 0;只学有对有错的组 | rubric 的分数,每组都学 | 页面没有标准答案;分数连续,相当于官方不给答案时的分支(每组都学) |
| 单条总结读 agent 的完整轨迹,知道对错 | 读页面本身(截图、文字)和表达、美学两个分数 | agent 一次要几十步、上百万 token;judge 判的也是页面。只给两个分数:给了条目名(「2.12 文中嵌图 0.20」)经验就照着条目名写,三页都没做到的东西也能学出来,不是组内比出来的;渲染失败的报错照给 |
| 批更新没有操作数上限 | `--max-ops`,默认每步最多新增、改写、删除合起来 3 条 | 我们加的约束:每一步只改几条,清单变化慢、可追溯 |
| 经验写成「名称:一句简短描述」;整批合并时多条 UPDATE 不要拼接细节 | 另外明说一条经验只讲一个原则,不罗列做法、图型、例子和检查项;多条 ADD 合并时也只取共同原则 | 只照官方的写法,deepseek 每组只能出 1 条经验时就把看到的做法全塞进去,整批合并又把 3 条 ADD 拼成一条两百多字的清单 |
| 解析经验要求 `<Experiences>` 首尾标签都在,缺了就是空 | 缺结尾标签也读;读不到就重问,不把空结果存下来 | deepseek 常漏写结尾标签,`tf2` 第一版 4 组里 3 组的经验因此丢了 |
| 温度 0.7 | 不设 | 生成用 deepseek 的思考模式,温度不起作用;同一份提示词写的页面本来就不同 |
| 数学一批 50 题、每题 5 个 | 一批 4 篇、每篇 3 个 | 一个页面要写 5–15 分钟 |

`tf1`(2026-10-22,已停)把 rubric 原文写进了学习目标、总结时给了 judge 的理由,学到的经验多是在复述 rubric,而且越写越长(4 条一步从 1199 字涨到 2577 字)。

## 运行

用 report-gepa 的环境(`../report-gepa/.venv`,装法见 report-gepa 的 README),密钥也一样在 `~/.config/report-gepa/llm.env`。

```sh
PYTHONPATH=src:../report-gepa/src ../report-gepa/.venv/bin/python -m report_tfgrpo.practice runs/<名字> [--group 3] [--batch 4] [--per-story 1] [--max-ops 3] [--epochs 1] [--steps N] [--stories a,b] [--mock] | tee runs/<名字>.log
```

- 数据用 report-gepa 的划分(`report_gepa.optimize.split`):训练 19 篇用来学;验证 8 篇和测试 16 篇(人工标注过的)不碰。`--stories` 指定别的篇。
- `--mock` 把 report-gepa 的 48 份 mock 明细数据(`data/mock/`,取回方法见 report-gepa 的 README)也加进训练集。agent 只拿到 `data.csv`,`gen.py` 和 `findings.json` 不给;总结和比较时只知道它是哪类业务数据。
- 每一步的东西在 `runs/<名字>/step-NN/`:`system.md`(这一步用的提示词)、`<篇>/page-K/`(页面、agent 记录)、`<篇>/ev-K/`(截图采集)、`judgements.json`、`summary-ev-K.md`、`advantage.md`、`operations.json`,`rollouts.json` 是这一步每个页面的 reward 和总结。
- 每一步结束后的经验清单在 `runs/<名字>/experiences/step-NN.json` 和 `.md`。
- 断了重跑同一命令:已有的页面、采集、判分、总结都复用,从最后一个没写完经验清单的步接着跑。

学完后在 GEPA 的验证集 8 篇上打分,和 report-gepa `runs/gepa/full` 的验证分(种子 0.541,最好的 0112 0.669)可比:

```sh
PYTHONPATH=src:../report-gepa/src ../report-gepa/.venv/bin/python -m report_tfgrpo.valeval runs/<名字> [--step N] | tee runs/<名字>-val.log
```

提示词是种子指南加这一步之后的经验清单(默认最后一步),每篇写一页,用 report-gepa 的 `Adapter` 写页面和判分;结果在 `runs/<名字>/val/`。

## 2026-10-22 的 `runs/tf2`

种子 `guides/seed.md`,一批 4 篇、每篇 3 页,1 个 epoch 共 4 步,最后 7 条经验(`runs/tf2/experiences/step-03.md`)。验证集 8 篇各一页:

| 提示词 | 验证均分 | 2.4 | 2.12 | 3.1 | 3.2 |
|---|---|---|---|---|---|
| 种子(GEPA `1192`) | 0.541 | 0.33 | 0.27 | 0.33 | 0.61 |
| 种子 + tf2 的 7 条经验 | 0.540 | 0.41 | 0.29 | 0.18 | 0.48 |
| GEPA 最好的 `0112` | 0.669 | 0.62 | 0.54 | 0.49 | 0.65 |

和种子持平。GEPA 从种子涨上来的主要是 2.4、2.12 这类每个页面都做不到的条目:组内三页都没做,就没有差别可比,TF-GRPO 学不到;GEPA 的反思读得到 judge 每条的理由,直接写进指南。组内分差大多 0.02–0.07,和 judge 的噪声(±0.05)同级,学到的经验多半是总结模型自己看截图得出的判断,不是组内比出来的。

## 数据

`runs/` 不进仓库。跑出来的结果上传 Google Drive 后,在这里写位置和取回方法。
