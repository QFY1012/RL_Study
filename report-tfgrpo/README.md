# report-tfgrpo

用 Training-Free GRPO(arXiv 2510.08191)给写报告页面的 agent 学一份经验清单。照官方实现做:`TencentCloudADP/youtu-agent` 的 `utu/practice/` 和 `utu/prompts/practice/experience.yaml`。

生成页面、截图采集、judge 和 rubric 都直接调用 `report-gepa`(`report_gepa.generate`、`capture`、`judge`、`rubric/judge-dimensions.md`),这里只有学习的循环和它的四个提示词。

## 和 GEPA 的区别

GEPA 改写整份指南,每一版都要和父版本比分数,决定留不留,所以每个页面要一个能跨版本比较的分数。Training-Free GRPO 不改指南,只往后面接一份经验清单;没有去留检验,只需要知道同一份数据的几个页面里谁好谁差。雅本来就只能组内比较,正好合用。

## 一步

1. **分组生成**:一批 `--batch` 篇数据,每篇用「基础提示词 + 当前经验清单」写 `--group` 个页面(默认 3 个),agent 是 report-gepa 的 pi agent,沙盒里有 `pageshot` 可以看自己的页面。
2. **reward**:每个页面截图采集后,deepseek 按 rubric 判:
   - 信:1.1(采集结果)、1.3(看图);犯了 reward 为 0。1.2 不做。
   - 达:2.x 每条 0–1 分,一次调用。
   - 雅:同一篇的几个页面放一组做组内挑选,三个页面按拉丁方判三轮;净票数 [-1, 1] 换算到 [0, 1]。
   - reward = 这些条目的平均(等权)。
3. **单页总结**:LLM 看每个页面的截图、文字和 judge 的理由,写出它的设计决定、得分和扣分在哪。
4. **组内优势**:LLM 比较同一篇的几个页面的总结和 reward,提炼最多 `--per-story` 条经验(默认 2 条),写成「当〈条件〉时,〈做法〉」。
5. **组更新**:每篇的新经验和现有清单比,决定 ADD / UPDATE / DELETE / NONE。
6. **批更新**:把这一批所有操作合成净效果,改出新的经验清单,下一步就用它。

经验清单接在基础提示词后面:「写页面之前,先仔细读懂下面这些经验,并照着做:[0]. …」。

和官方不同的地方:

| 官方 | 这里 | 原因 |
|---|---|---|
| 和标准答案比,对 1 错 0 | rubric 的分数,雅组内比较 | 页面没有标准答案;论文也有不给答案、只靠组内对比的版本 |
| 单条总结读 agent 的完整轨迹 | 读页面本身(截图、文字、judge 的理由) | agent 一次要几十步、上百万 token;judge 判的也是页面 |
| 温度 0.7 | 不设 | 生成用 deepseek 的思考模式,温度不起作用;同一份提示词写的页面本来就不同 |
| 数学一批 50 题、每题 5 个 | 一批 4 篇、每篇 3 个 | 一个页面要写 5–15 分钟 |

## 运行

用 report-gepa 的环境(`../report-gepa/.venv`,装法见 report-gepa 的 README),密钥也一样在 `~/.config/report-gepa/llm.env`。

```sh
PYTHONPATH=src:../report-gepa/src ../report-gepa/.venv/bin/python -m report_tfgrpo.practice runs/<名字> [--group 3] [--batch 4] [--per-story 2] [--epochs 1] [--steps N] [--stories a,b] | tee runs/<名字>.log
```

- 数据用 report-gepa 的划分(`report_gepa.optimize.split`):训练 19 篇用来学;验证 8 篇和测试 16 篇(人工标注过的)不碰。`--stories` 指定别的篇。
- 每一步的东西在 `runs/<名字>/step-NN/`:`system.md`(这一步用的提示词)、`<篇>/page-K/`(页面、agent 记录)、`<篇>/ev-K/`(截图采集)、`judgements.json`、`summary-ev-K.md`、`advantage.md`、`operations.json`,`rollouts.json` 是这一步每个页面的 reward 和总结。
- 每一步结束后的经验清单在 `runs/<名字>/experiences/step-NN.json` 和 `.md`。
- 断了重跑同一命令:已有的页面、采集、判分、总结都复用,从最后一个没写完经验清单的步接着跑。

## 数据

`runs/` 不进仓库。跑出来的结果上传 Google Drive 后,在这里写位置和取回方法。
