"""Prompts for the four LLM steps of Training-Free GRPO.

Translated from the official implementation (TencentCloudADP/youtu-agent,
utu/prompts/practice/experience.yaml) and kept to its structure: single rollout
summary, group advantage, group update, batch update. What differs: the
"trajectory" of a rollout is the page it produced (its screenshots, text and
the judge's reasons), because the agent's own transcript runs to millions of
tokens and the page is what is judged; and there is no ground truth, only the
judge's scores and reasons, as in the paper's variant without answers.
"""

AGENT_OBJECTIVE = """输入:一份数据(工作目录 data/ 里的 CSV、JSON 等文件,有的带数据说明)。
输出:一个把这份数据讲清楚的数据报告网页(单个 HTML 文件,英文)。"""

LEARNING_OBJECTIVE = """帮写页面的 agent 写出更好的数据报告网页。每个页面有一个 reward(0 到 1,judge 打的总分)和 judge 对这个页面的具体评语,好坏以它们为准。
提炼具体、能照着做的做法(用什么图、怎么排、怎么标、怎么写),能用到没见过的数据上;不要只对某一份数据成立的细节,也不要把评语里的评价词(一致、连贯、简洁、贴合话题)原样当成经验。"""

HEAD = """你的最终目标是从写页面的 agent 过去的尝试里提炼有用的经验,提高它以后的表现。经验要围绕学习目标,以后会用来指导 agent 的行为。agent 和学习目标如下:
<Agent 目标>
{agent_objective}
</Agent 目标>
<学习目标>
{learning_objective}
</学习目标>

"""

SINGLE_SUMMARY_SP = HEAD + """现在你要分析 agent 的一次尝试:它针对一份数据写出的一个网页。给你的是这个页面的滚动截图、缩略整页图、页面文字、滚动记录,以及 judge 按评判标准给的分数和理由。

<任务>
1. 围绕学习目标:学习目标不等于 agent 的任务本身,要分清。
2. 逐项写出这个页面的设计决定:标题和开头怎么写、分几节、每节讲什么、每张图的图型和编码、图上有没有标注、文字和图怎么配合、有没有滚动时变化的图、配色和整体风格。写具体,不要笼统。
3. 对照 judge 的理由,写出哪些决定得分、哪些决定扣分,以及错过了什么机会。不要默认 agent 的做法是对的。
4. 总结它的整体做法。
</任务>

<输出>
学习目标和 agent 任务的区别:[一两句]

页面的设计决定:
1. ...
2. ...

得分和扣分:
- [决定] → [judge 怎么评,哪一条,多少分]

错过的机会:
- ...

整体做法:[一段话]
</输出>"""

SINGLE_SUMMARY_UP = """<数据>
{question}
</数据>

<judge 的分数和理由>
{critique}
</judge 的分数和理由>

下面是这个页面(截图和文字)。按要求输出:"""

GROUP_ADVANTAGE_SP = HEAD + """现在你要比较 agent 对同一份数据的几次尝试(几个页面),提炼能指导以后的高层经验。

<输入>
- 数据:agent 拿到的那份数据。每次尝试的 reward 在 0 到 1 之间,1 最好。
- 几次尝试:每次是一个页面的总结。
</输入>

<任务>
1. 按学习目标评估每次尝试:哪些更好,哪些更差,差别在哪。
2. 差的:找出根本原因(设计决定、对数据的理解……),写出具体的失败模式。
3. 好的:找出关键的成功因素和有效做法。
4. 提炼通用的经验:能用到以后别的数据上。每条写成「当〈条件〉时,〈做法〉」,不超过 60 个汉字;做法是好的页面实际做了、差的页面没做的具体动作,不是评价词。
</任务>

<输出格式>
用下面的标签组织输出:
<学习目标重点>
  [一两句]
</学习目标重点>

<表现评估>
  - 好的尝试:[哪几次,为什么]
  - 差的尝试:[哪几次,为什么]
</表现评估>

<对比分析>
  [直接对比好的和差的尝试,指出最关键的差别]
</对比分析>

<模式>
  [成功的关键和常见的坑]
</模式>

<Experiences>
  [最多 **{num_experiences}** 条经验,围绕学习目标]
  1. [经验 1]
  2. [经验 2]
</Experiences>
</输出格式>"""

GROUP_ADVANTAGE_UP = """<数据>
{question}
</数据>

<几次尝试>
{trajectories}
</几次尝试>

按上面的格式输出。"""

OPS = """<输出要求>
只输出一个合法的 JSON 数组,放在 ```json 代码块里。每个元素是一个对象:
```json
{{"operation": "ADD | UPDATE | DELETE | NONE", "id": "已有经验的编号,或 null", "content": "经验名称:一句话"}}
```
ADD 和 NONE 的 id 写 null;UPDATE 和 DELETE 必须写已有经验的编号。数组里对象的个数{count_rule}。
</输出要求>

<输出示例>(和本任务无关,只示范格式)
```json
[
  {{"operation": "ADD", "id": null, "content": "新闻时效:用户问最近的新闻时,优先用近期来源,对时效性强的问题加时间过滤。"}},
  {{"operation": "UPDATE", "id": "3", "content": "产品比较:先搜出主流型号,再比较关键参数。"}},
  {{"operation": "NONE", "id": null, "content": "核对网址:点开搜索结果前先核对网址。"}}
]
```
</输出示例>"""

GROUP_UPDATE_SP = HEAD + """现在你要优化经验清单:给你现有的经验和从最近几次尝试里提炼的新经验,对每条新经验决定一种操作。

<任务>
1. 围绕学习目标:每个改动都要有助于提高 agent。
2. 四种操作:对每条新经验,和所有现有经验比较:
- ADD:新经验的内容在现有经验里完全没有。系统会自动分配编号。
- UPDATE:新经验细化、扩充或改进了某条现有经验。核心意思相同但多了细节时,把新信息合进去、保持编号不变,写成更完整但仍然概括的一条;略有冲突或多了分寸时,也优先 UPDATE,抓住关键点。意思相同、没有实质补充的,选 NONE。
- DELETE:新经验和某条现有经验直接矛盾(给出相反的指导,或那条已经过时),或那条无关、有害。写明要删的编号。
- NONE:新经验已经被现有经验完全覆盖,或多余、无关、没有价值。
3. 经验写成「经验名称:当〈条件〉时,〈做法〉」,名称是一两个词,整条不超过 60 个汉字。一条只讲一个做法:新经验讲的是另一个做法时用 ADD,不要 UPDATE 进旧经验把它越写越长。
</任务>

""" + OPS.replace("{count_rule}", "必须和新经验的条数相同")

GROUP_UPDATE_UP = """<现有经验>
{existing}
</现有经验>

<新经验>
{new}
</新经验>

按上面的要求输出。"""

BATCH_UPDATE_SP = HEAD + """现在你要合并并执行一批经验更新操作,它们来自这一批数据上的多次尝试。

<输入>
- 现有经验,每条后面跟着这一批里针对它的操作。
- 这一批里不针对现有经验的其他操作。
</输入>

<任务>
1. 围绕学习目标。
2. 四种操作:ADD、UPDATE、DELETE、NONE。
3. 合并:分析这一批操作,给出它们的净效果。
- 对每条现有经验,看所有针对它的 UPDATE 和 DELETE。同一条有多个 UPDATE,合成一条,抓住共同的核心,不要把细节拼在一起。
- 有 DELETE 就以 DELETE 为准:它说明这条经验无效或过时。
- 几条 ADD 内容相近的,合成一条,保留要点、去掉冗余;各有独到之处的,分开保留。每条新增的都要对学习目标有用。
- 每条经验不超过 60 个汉字,一条只讲一个做法;合并后超过就拆成几条。
- 有冲突时,按上下文、可靠程度和具体程度取舍;能统一成一条兼顾的做法就统一,不能就选更通用、更合理的。
</任务>

""" + OPS.replace("{count_rule}", "按合并后的净操作来定,但 ADD、UPDATE、DELETE 合起来最多 {max_ops} 个;超过时只留对学习目标最重要的,有多组数据印证的优先")

BATCH_UPDATE_UP = """<现有经验和针对它们的操作>
{experiences_and_operations}
</现有经验和针对它们的操作>

按上面的要求输出。"""

EXPERIENCE_HEADER = "\n\n写页面之前,先仔细读懂下面这些经验,并照着做:\n"
