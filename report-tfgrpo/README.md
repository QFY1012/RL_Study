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
3. **单页总结**:LLM 看每个页面的截图、文字和 judge 的理由,写出它的设计决定、得分和扣分在哪。
4. **组内优势**:LLM 比较同一篇的几个页面的总结和 reward,提炼最多 `--per-story` 条经验(默认 2 条),写成「当〈条件〉时,〈做法〉」。
5. **组更新**:每篇的新经验和现有清单比,决定 ADD / UPDATE / DELETE / NONE。
6. **批更新**:把这一批所有操作合成净效果,改出新的经验清单,下一步就用它。

经验清单接在基础提示词后面:「写页面之前,先仔细读懂下面这些经验,并照着做:[0]. …」。

和官方不同的地方:

| 官方 | 这里 | 原因 |
|---|---|---|
| 和标准答案比,对 1 错 0 | rubric 的分数 | 页面没有标准答案;论文也有不给答案、只靠组内对比的版本 |
| 学习目标只说要答对 | 学习目标只说要页面更好、好坏看 reward 和 judge 对这一页的评语,不给 rubric 原文 | `tf1` 把 rubric 原文写进了学习目标,学到的经验多是在复述 rubric(「先列颜色语义表」「配色从话题取形」),和论文里「直接让模型写经验」没有区别 |
| 每条经验不超过 32 个英文词 | 每条写成「当〈条件〉时,〈做法〉」,不超过 60 个汉字,一条只讲一个做法 | `tf1` 没设上限,4 条经验一步就从 1199 字涨到 2577 字,都是往旧经验里堆细节 |
| 每步的操作数有上限(官方提示词里是一个占位参数) | `--max-ops`,默认每步最多新增、改写、删除合起来 3 条 | 每一步只改几条,清单变化慢、可追溯;`tf2` 第 0 步一下子加了 5 条 |
| 单条总结读 agent 的完整轨迹 | 读页面本身(截图、文字)和各项分数 | agent 一次要几十步、上百万 token;judge 判的也是页面 |
| 单条总结只知道对错和标准答案 | 只给各项分数,不给 judge 的理由(渲染失败的报错照给) | 理由用的是 rubric 的话,`tf1` 和 `tf2` 第一版的经验都在复述它;分数告诉模型差在哪一项,为什么差要它自己从截图里找 |
| 温度 0.7 | 不设 | 生成用 deepseek 的思考模式,温度不起作用;同一份提示词写的页面本来就不同 |
| 数学一批 50 题、每题 5 个 | 一批 4 篇、每篇 3 个 | 一个页面要写 5–15 分钟 |

## 运行

用 report-gepa 的环境(`../report-gepa/.venv`,装法见 report-gepa 的 README),密钥也一样在 `~/.config/report-gepa/llm.env`。

```sh
PYTHONPATH=src:../report-gepa/src ../report-gepa/.venv/bin/python -m report_tfgrpo.practice runs/<名字> [--group 3] [--batch 4] [--per-story 2] [--max-ops 3] [--epochs 1] [--steps N] [--stories a,b] | tee runs/<名字>.log
```

- 数据用 report-gepa 的划分(`report_gepa.optimize.split`):训练 19 篇用来学;验证 8 篇和测试 16 篇(人工标注过的)不碰。`--stories` 指定别的篇。
- 每一步的东西在 `runs/<名字>/step-NN/`:`system.md`(这一步用的提示词)、`<篇>/page-K/`(页面、agent 记录)、`<篇>/ev-K/`(截图采集)、`judgements.json`、`summary-ev-K.md`、`advantage.md`、`operations.json`,`rollouts.json` 是这一步每个页面的 reward 和总结。
- 每一步结束后的经验清单在 `runs/<名字>/experiences/step-NN.json` 和 `.md`。
- 断了重跑同一命令:已有的页面、采集、判分、总结都复用,从最后一个没写完经验清单的步接着跑。

## 数据

`runs/` 不进仓库。跑出来的结果上传 Google Drive 后,在这里写位置和取回方法。
