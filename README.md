# RL Study

输出层(报告页面生成)的 judge、迭代 loop 和强化学习实验的代码,从 `QFY1012.github.io` 的 `experiments/` 搬过来,保留了提交历史(只含代码文件)。

| 目录 | 内容 |
|---|---|
| `ui-judge/` | 页面 judge(reward):成对 / 单页打分脚本、评分标准、渲染 |
| `ui-loop/` | 第一版迭代 loop:组件库、生成 Agent、比较与合并脚本 |
| `ui-rl/` | 重建的强化学习环境(Training-Free GRPO),计划见 `ui-rl/PLAN.md`,进度见 `ui-rl/README.md` |

各目录的说明见各自的 README。

## 材料不在仓库里

数据、生成的页面、截图、traces、runs、标注和分析报告放在 Google Drive 的 `rl-materials.tar.gz`(约 490 MB,13968 个文件)。解压到仓库根目录,路径就和脚本里写的一致:

```bash
tar -xzf rl-materials.tar.gz -C <仓库根目录>
```

压缩包里的内容:

| 路径 | 文件数 |
|---|---|
| `ui-judge/archive` `data` `evalset` `specs` `validate` | 48 |
| `ui-loop/traces` | 9838 |
| `ui-loop/library`(组件提案记录) | 123 |
| `ui-loop/skills/flow` `skills/cvd`(指南、经验、数据、状态) | 209 |
| `ui-loop/demo` 生成的页面、`designs`、`loop-state.json` | 46 |
| `ui-rl/runs` | 3145 |
| `ui-rl/data/flow`(f1–f24 报告数据和截图) | 548 |
| `ui-rl/labels` 的 `pairs` `key` `human`、`ui-rl/reports` | 8 |
| `ui-rl/gen` 里的 2 张 png、一个 pyc 缓存 | 3 |

所有 `.png`、`.jsonl`、`.svg`、`.log` 都在压缩包里,不进仓库。
