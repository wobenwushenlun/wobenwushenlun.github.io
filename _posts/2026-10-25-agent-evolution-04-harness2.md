---
title: "Harness² 论文与源码精读：用执行对比递归改进 Agent Harness"
date: 2026-10-25 00:00:04 +0800
categories:
- Agent 系统工程
tags:
- Harness2
- Recursive Self-Improvement
- Harness Engineering
- Test-Time Adaptation
excerpt: 拆解 Propose–Probe–Compose、任务层与 harnessing 层两级递归，追踪候选选择和经验库代码，设计等预算且隔离评测的复现实验。
order: 4
pin: false
---

> 核对日期：2026-10-25。论文：Harness²: Recursive Agent Harnessing for an Open World，arXiv:2610.14224v1，2026-10-09。代码：Google Research `harness2`，固定 commit `1cfe254e8d25b15f37048c3730134686abe60335`。本文未独立复现作者成绩；论文结果、源码事实和教学推导分别说明。论文以 CC BY 4.0 发布，代码以 Apache-2.0 发布，原作者与出处见文末。

## 1. 这篇论文真正研究什么

同一个模型，换一套工具说明、上下文组织、检查步骤和辅助脚本，任务表现可能不同。Harness² 把这部分模型外部系统视为可编辑对象，研究如何在遇到新任务时自动修改它，并把修改经验用于后面的任务。[论文](https://arxiv.org/html/2610.14224)

它面对两个难点：新任务缺少可供在线优化使用的标准答案；一次任务产生的改法未必适合下一次。解决思路是把当前任务内的执行对比，与跨任务保存的改进经验连接起来。

它固定执行模型权重，不等于“整个系统完全不变”：输入文件、skills、脚本与经验库都可能改变。其递归主要体现在外部改进过程积累和利用经验，不是不断重新训练底座模型。

## 2. 先区分 execution harness 与 improvement harness

| 对象 | 职责 | 示例 |
| --- | --- | --- |
| Execution harness | 让 Agent 完成当前任务 | 规则、工具指导、skills、辅助脚本 |
| Improvement harness | 指导如何修改前者 | 阶段指令、候选编辑流程、改进经验库 |

教学记号：`M` 表示固定执行模型，`H` 表示执行 harness，`R` 表示改进 harness，`q` 表示任务，`e=(trajectory, deliverable)` 表示执行证据。

```text
固定执行模型 M + 执行 harness H → 执行任务 q → 证据 e
改进系统 R + q + H + e          → 新的 H'
本次改进证据                    → 更新 R 的经验库
```

重要边界：论文中每个新任务从共同的初始执行 harness 开始，历史改动通过经验库按需复用，而不是把上一任务全部配置无条件继承给下一任务。改进阶段指令与决策规则保持固定，主要持续演化的是库内容。[方法 §2.1–2.3](https://arxiv.org/html/2610.14224#S2)

## 3. 八类可编辑对象

官方列出 system prompt、guardrails、memory、tool guidance、subagents、skills、scripts、plugins 八类组件。[仓库](https://github.com/google-research/harness2)

| 组件 | 自拟改动 | 应检查的副作用 |
| --- | --- | --- |
| System prompt | 明确交付物和完成标准 | 指令过长、冲突 |
| Guardrails | 增加关键动作前的检查 | 误阻正常任务 |
| Memory | 保存领域约束 | 过期、污染 |
| Tool guidance | 解释工具参数和错误恢复 | 指导与真实工具不符 |
| Subagents | 划出独立验证职责 | 沟通与协调成本 |
| Skills | 包装可复用过程 | 过拟合单个任务 |
| Scripts | 自动计算或校验 | 代码错误、依赖变化 |
| Plugins | 改变运行时行为 | 权限与兼容性 |

这个范围有助于超越“自动改 prompt”。但可编辑面越大，需要隔离和回归测试的行为也越多。

## 4. 核心步骤：Propose → Probe → Compose

### 4.1 Reference：先得到基准行为

先用当前 harness 跑任务，获得轨迹和产物。它揭示系统做了什么，不能单独证明结果对错。

教学任务：生成一份包含多个工作表的数据分析文件。参考执行只处理了首张表，最终文件虽然存在，却遗漏了关键输入。

### 4.2 Propose：从两个角度提出候选

- **Invariant 候选：** 改通用执行缺陷，例如计划、工具调用、上下文、委派。
- **Domain-specific 候选：** 改当前领域的知识、流程与约束。

对应自拟例子：前者增加“先枚举全部输入”的通用检查；后者增加“区分公式单元格与缓存数值”的表格处理规则。

两个候选是对当前 harness 的可执行修改，不只是对最终答案的重写。历史库能提供组件和经验，但旧任务中的具体事实需要在当前材料中重新确认。

### 4.3 Probe：运行候选，比较行为变化

在匹配的模型与环境配置下运行候选，观察：是否真的读取了全部工作表、是否出现新错误、是否增加无效调用、交付物是否覆盖更多约束。

这是可见行为的对照，仍不是标准答案验证。两次不同结果可能来自采样随机性，也可能来自模型共有的判断偏差。

### 4.4 Compose：有选择地保留、修订或组合

合成器读取候选差异与执行证据，决定哪些改动有支持、哪些冲突、哪些应放弃。不能把所有候选机械拼接，否则冗长规则与工具冲突可能一起进入下一版本。

合成后的 harness 还要再执行，记录其产物和证据。这里改进的对象依然是可运行系统，不只是文本建议。[方法 §2.2](https://arxiv.org/html/2610.14224#S2.SS2)

## 5. 用伪代码理解一次改进

下面是教学抽象，函数名与数据结构不代表官方 API：

```python
def improve_task(task, base_harness, improvement_library):
    reference = execute(task, base_harness)
    candidates = [
        propose(task, base_harness, reference,
                scope="general", library=improvement_library),
        propose(task, base_harness, reference,
                scope="domain", library=improvement_library),
    ]
    probes = [execute(task, candidate) for candidate in candidates]
    successor, edit_evidence = compose(
        task, base_harness, reference, candidates, probes
    )
    result = execute(task, successor)
    return successor, result, edit_evidence
```

真正实现还需要候选目录隔离、模型会话启动、组件映射、错误处理、轨迹装配、产物渲染和证据过滤。这些往往比这段伪代码本身更影响可复现性。

## 6. 两种任务层递归：宽度与深度

### 6.1 Parallel：扩大候选与组合的宽度

并行模式在当前初始 harness 周围提出多组通用和领域候选，获得执行池，再让多个合成会话分别组合。`k` 控制宽度，不表示把最优版本连续训练了 k 代。

```text
初始 H
  ├─ 多个通用候选 ─┐
  └─ 多个领域候选 ─┴─ 执行证据池
                         ├─ Compose 1 → H'1 → 执行
                         ├─ Compose 2 → H'2 → 执行
                         └─ Compose k → H'k → 执行
```

### 6.2 Sequential：逐步带着前一轮修改继续

```text
H0 → 对比改进 → H1 → 对比改进 → H2 → ... → Hk
           本任务的执行与改进历史不断累积
```

串行模式可能更善于修正前一轮的问题，也可能更容易路径依赖。并行模式探索更宽，但不同候选常有重复计算。

论文中 `k=1` 都退化为基本改进步骤；`k>1` 时还有从匿名交付物中选择现有输出的阶段。[递归与选择](https://arxiv.org/html/2610.14224#S2.SS2)

## 7. 一个源码细节：选择结果不等于验证最优

固定版本的 `selection.py` 会为候选产物分配匿名 ID，并组织选择过程。选择器返回已有产物，而不在这一步重新写答案；选择阶段与后续 benchmark grader 也不是同一个角色。

特别值得注意：当前代码的 final selection pool 由递归产生的最终候选构成，参考 base 执行被排除。`k=1` 绕过多候选选择，直接使用基本步骤的结果。[selection.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/selection.py)

因此不能给这个方法添加一个未经证明的保证：“只要新版本不如 base，系统总会自动回退 base”。Compose 可以保留配置，但那是与最终候选池和评分保证不同的机制。

教学上，这个细节要求把三个概念分开：

1. 编辑器相信某个改动值得保留。
2. 选择器偏好某份产物。
3. 独立评测发现任务真的更好。

三者相关，却不相等。

## 8. Harnessing 层递归：库究竟保存什么

当前 `library.py` 保存采用的完整 harness 文件树和 `EXPERIENCE.md`，并生成索引。经验包含触发线索、教训与支持证据；领域库按目录组织，不是默认假定有一个向量记忆系统自动挑选经验。[library.py](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/library.py)

教学上可以写成：

```text
domain-library/
├─ INDEX.md
└─ harnesses/
   └─ earlier-task/
      ├─ harness/        完整采用配置
      └─ EXPERIENCE.md  何时适用、做了什么、证据是什么
```

库在新任务编辑会话中提供参考，后续仍应选择性适配；库增长不代表每条经验都正确，也不保证每个新任务都受益。

### 8.1 好经验与坏经验

| 经验描述 | 问题 / 价值 |
| --- | --- |
| 以后认真检查 | 无法执行和检验 |
| 这类任务使用公司 A 的数据 | 可能硬编码旧任务事实 |
| 多工作表输入时先枚举表名，并核对每张表是否需要使用 | 有触发条件与动作 |
| 上一条规则曾减少遗漏，但在空表上失败，需跳过无有效数据的表 | 含限制与反例 |

最有价值的经验往往还包含“什么时候不要用”。这属于本文建议的经验质量标准，不是说官方系统已经完整解决经验有效性问题。

## 9. “不需要 ground truth”到底意味着什么

它表示在线编辑、对比、合成与选择不以任务标准答案作为指导信号。系统依然使用执行结果、源材料、工具反馈、模型判断与产物证据。

**无标准答案不等于无反馈；有执行反馈不等于有可靠真值。**

仓库另有 `harness2-judge` 和 `harness2-report` 评估 benchmark 成绩。评测流程能量化算法输出，不应把其答案或 verdict 回流到在线编辑过程。[仓库运行说明](https://github.com/google-research/harness2#run-a-benchmark)

源码中也有防止 grader verdict 进入经验的检查，但程序过滤不是无泄漏证明。真实复现还应控制网络、文件访问和缓存，确保评分标准不会从环境侧泄漏。

## 10. 论文实验：哪些结果值得记住

论文覆盖 WorkBuddy-Bench、JobBench 和法律工作 LAB，使用两个执行模型、两个初始 harness 的组合。主表报告三次运行的均值和标准差；LAB Partial 是逐标准通过率，不是完整任务全通过率。[实验 §3](https://arxiv.org/html/2610.14224#S3)

取一个主表例子：GLM-5 在 OpenCode 下的 WorkBuddy 平均分，base 为 64.2，单步 Harness² 为 75.7，相差 **11.5 个分数点**。这是特定配置的报告结果，不是所有模型和任务的通用增益。

作者还比较固定 base、ReasoningBank、Meta-Harness、Harness Scaling 等不同路线。阅读时关注各方法改进预算、任务信息和跨任务状态是否可比，不要只按表中一个最高数字排序。

### 10.1 为什么 #Steps 不能代表全部改进成本

最终执行步骤减少，可能说明新 harness 更高效；但提出候选、运行 probe、合成和选择的调用也花钱。应该分别报告：

- 最终采用版本的执行成本；
- 本次为得到该版本花费的所有探索成本；
- 经验在后续任务上复用后的摊销成本。

### 10.2 编辑器与执行器要分别记录

论文默认编辑器与执行模型并非同一个角色。不能将“较弱执行器经过编辑后表现更好”直接解释为较弱模型独自完成了所有改进。编辑模型的能力与费用应列入配置与成本报告。

## 11. 复现前先设计两个问题

**问题 A：** 在允许更多计算时，整套改进流程能否提高任务成功率？

**问题 B：** 在相同总预算下，修改 harness 是否比单纯多次执行和挑选答案更有效？

二者都值得研究，但不能拿 A 的实验回答 B。推荐至少设置：

| 组别 | 目的 |
| --- | --- |
| Base 单次运行 | 得到原始起点 |
| 固定 harness 多次采样 + 相同选择器 | 排除多试几次的收益 |
| 只提修改，不执行 Probe | 检验执行对比贡献 |
| 执行候选，但不 Compose | 检验选择性组合贡献 |
| 完整改进，关闭跨任务库 | 检验任务内修改 |
| 完整改进，启用库 | 检验经验积累 |

固定执行器、编辑器、工具、环境快照和总体费用上限。除调用次数外，记录 token、墙钟时间与最大并发；不同任务使用不同长度轨迹时，等调用不一定等计算。

## 12. 跨任务实验要特别小心任务顺序

若先做简单任务再做复杂任务，看见后期成绩变好，可能是经验积累，也可能是顺序或分布变化。应随机化顺序并重复，记录每个时点的库快照。

需要至少检查：

- 空库与已有库的对照；
- 同领域新任务与跨领域任务；
- 更换执行模型后是否仍有效；
- 同一经验库是否含测试任务答案；
- 经验增多后是否出现上下文膨胀和负迁移。

“最终采用的 harness”也不应永久覆盖主线配置。研究环境中的候选应隔离，经过独立回归后再决定部署。

## 13. 计算规模的直观估算

按论文描述，理想化单步包含 reference、两类 probe、composed successor 的执行，可理解成约四次任务执行，再加编辑与反思调用。并行 `k` 扩宽后，执行数随 k 增长。

这只是理解量级的推导，不是对全部 CLI 分支的精确计费公式。实际还会有错误重试、复用、产物渲染、选择和 benchmark 评分。

做预算时可以使用：

```text
总成本 = 参考执行 + 候选执行 + 合成执行
       + 编辑器 + 选择器 + 反思 + 独立评测
```

最应该避免的是只统计最终 successor，然后宣称自动优化“几乎零成本”。

## 14. 源码精读顺序

固定快照：[Harness² source](https://github.com/google-research/harness2/tree/1cfe254e8d25b15f37048c3730134686abe60335)。

| 文件 | 阅读任务 |
| --- | --- |
| `harness2/core/tree.py` | 可编辑文件树与执行器组件怎样映射？ |
| `harness2/core/spec.py` | benchmark adapter 和执行记录包含什么？ |
| `harness2/core/proposer.py` | 编辑会话读取什么、能修改什么？ |
| `harness2/core/recursion.py` | 串行与并行如何组织状态？ |
| `harness2/core/schedule.py` | 依赖、并发、恢复如何调度？ |
| `harness2/core/selection.py` | 候选池、匿名化与失败回退如何实现？ |
| `harness2/core/library.py` | 经验何时写入，怎样按领域复用？ |
| `harness2/core/context.py` | 哪些证据可以进入改进上下文？ |

不要从大型 executor 开始迷失在适配细节。先用确定性 demo 对照目录和日志，确认每一阶段的输入输出。

## 15. 最小上手路径

官方安装目标为 Linux 与 Python 3.12。下面是官方提供的无模型凭据 demo 路线；本文未运行该 demo，不宣称已验证本地兼容性。[安装说明](https://github.com/google-research/harness2#install)

```bash
git clone https://github.com/google-research/harness2.git
cd harness2
git checkout 1cfe254e8d25b15f37048c3730134686abe60335
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e '.[render]'
harness2-demo --output runs/demo --k 2
```

在 Windows 上可优先考虑 WSL 或 Linux 环境，不能把这些 shell 命令直接当作 PowerShell 命令。真实 benchmark 还需要模型、执行器及任务依赖；先从一个任务和小预算开始。

## 16. 一天 5 小时练习与晋级标准

| 时间 | 练习 | 可观察结果 |
| --- | --- | --- |
| 60 分钟 | 精读方法与流程图 | 讲清 H 与 R 的区别 |
| 60 分钟 | 跑确定性 demo，检查产物 | 对应每个阶段的目录和日志 |
| 75 分钟 | 阅读选择器与库代码 | 解释 base 是否在候选池 |
| 75 分钟 | 为一个小任务设计消融 | 等预算表与隔离评测方案 |
| 30 分钟 | 闭卷复述与修正 | 不把无标签改进等同于正确性证明 |

晋级任务：用自己的话解释两个新任务为什么都可以从 H0 开始，却仍然体现跨任务经验积累；再设计一个能发现“经验越积越多但测试变差”的实验。

## 17. 自测与参考要点

1. Task-level 与 harnessing-level 分别改变什么？
2. Probe 能提供什么，不能证明什么？
3. 为什么并行 k 不代表递归深度 k？
4. 为什么 adopted harness 不能称为 verified optimal harness？
5. 如何排除改善只是来自额外采样？

<details>
<summary>参考要点</summary>
<p>前者修改当前任务执行配置，后者通过经验库影响以后改进；Probe 提供行为差异，缺少标准答案时不能证明正确；并行扩展候选与组合宽度；选择是模型基于可见证据的判断，没有最优保证；用固定 harness 多次执行及同等选择机制、总预算和独立评测作对照。</p>
</details>

复习卡：固定模型，修改外部系统；对比执行后再组合；经验带完整组件和证据；新任务不盲目继承旧配置；选择、验证、部署分别负责；最终执行便宜不等于优化全过程便宜。

## 18. 资料与系列导航

1. [Harness² 原论文](https://arxiv.org/html/2610.14224)
2. [论文元数据](https://arxiv.org/abs/2610.14224)
3. [Google Research 仓库](https://github.com/google-research/harness2)
4. [固定代码快照](https://github.com/google-research/harness2/tree/1cfe254e8d25b15f37048c3730134686abe60335)
5. [选择器](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/selection.py)
6. [经验库](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/library.py)

系列：[Langfuse](/notes/agent-evolution-01-langfuse/) · [OpenViking](/notes/agent-evolution-02-openviking/) · [Mem0](/notes/agent-evolution-03-mem0/) · [Harness²](/notes/agent-evolution-04-harness2/) · [Dream-RSI](/notes/agent-evolution-05-dream-rsi/)
