# RL_Study

## 代码进 git,数据进 Google Drive

- 只把代码提交到这个仓库:脚本、组件、配置、提示词、规范,以及说明代码的 README / PLAN。
- 数据一律放 Google Drive(账号 qfy2518418912@gmail.com),不进 git:报告数据、生成的页面、截图、traces、runs、标注、评测结果、分析报告、模型权重。
- 新产生的数据先放 Drive,再在对应目录的 README 里写清楚它在 Drive 的哪里、怎么取回、解压到哪个路径。
- 提交前看一眼 `git status`:有 png、jsonl、大的 json 或别的产物就别提交,按需要加进 `.gitignore`。
- 现有材料在 Drive 的 `QFY1012.github.io-claude-beautiful-faraday-cypsxn.zip`,取回方法见根目录 README。

## 不跑静默的终端命令

- 命令的输出要让人看得到:不要把输出全部重定向到文件或 `/dev/null` 了事,也不要用 `-q` 之类只为不出声的参数。
- 长任务要写日志时用 `tee`,同时留在终端输出里;跑的过程中定期把进度(日志末尾)拿出来给人看,不要只在结束时报一句。
- 后台任务启动后马上看一次它的输出,确认它在正常干活,而不是空转。
