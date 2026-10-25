---
title: "Langfuse 深度学习笔记：把 Agent 的执行轨迹变成评测与改进证据"
date: 2026-10-25 00:00:01 +0800
categories:
- Agent 系统工程
tags:
- Langfuse
- Observability
- Agent Evals
- Harness Engineering
excerpt: 从 trace、observation、score 到数据集实验，设计可归因的 Agent 观测与回归评测闭环，理解 Langfuse 的职责、架构、接入方法和边界。
order: 1
pin: false
---

> 核对日期：2026-10-25。本文是基于官方文档与开源仓库的项目学习笔记，不是独立性能实测。Langfuse 主要是工程平台，本文不为它虚构一篇对应算法论文。源码索引固定在 `f6c3660ced73d380f1936d2adb0cca97f16e4d2a`；文档可能继续更新。

## 1. 先问一个真实问题：Agent 为什么失败

假设一个研究 Agent 需要回答“某公司的现金流变化主要来自哪里”，它依次检索、解析 PDF、抽取数字、计算并生成报告。最终答案错误，可能至少有六个原因：

| 位置 | 可能的失败 | 需要保留的证据 |
| --- | --- | --- |
| 意图理解 | 找错公司或报告期 | 用户问题、结构化约束 |
| 检索 | 没找到关键报告 | query、候选来源、排序 |
| 解析 | 表格列错位 | 文档版本、页码、解析结果 |
| 上下文 | 关键证据被截断 | 装配后的上下文、截断记录 |
| 工具执行 | 单位或公式错误 | 工具参数、返回值、异常 |
| 最终生成 | 引用了没有支持的结论 | 答案、引用、评分理由 |

只有最终答案和 HTTP 状态码，很难定位这些问题。Langfuse 的直接价值，是把模型调用及相关业务步骤记录成可以关联、检查、评分的执行轨迹，并把典型案例变成实验数据集。[官方项目](https://github.com/langfuse/langfuse)

下面的表格、任务例子、指标组合和实验设计是本文的工程推导，不表示 Langfuse 自动提供了领域判断能力。

## 2. 它在系统中的位置

```text
用户请求
  → Agent harness
      → 模型调用
      → 检索 / 工具 / 验证 / 恢复
      → 最终输出
      └─ 遥测事件 → Langfuse → 轨迹检查 / 评分 / 数据集实验

实验结论 → 人或优化程序提出改动 → 下一版 harness
```

Langfuse 能服务改进闭环，却不会因为接入了 SDK 就自动让 Agent 自进化。产生改动、批准改动、部署新版本和回滚，需要由外部流程承接。

还有一个经常混淆的边界：**可观测性记录不是执行状态机。** 某次工具调用已经写入 trace，不代表执行器可以根据 trace 安全地恢复支付、写库或发消息。恢复需要幂等键、检查点与事务语义。

## 3. 核心对象：用一条任务串起来

官方把 tracing 和 evaluation 的对象连接起来；评分可以关联轨迹、观测、会话和数据集运行。学习时先理解以下对象的职责，具体字段以当前 SDK 为准。[评测核心概念](https://langfuse.com/docs/evaluation/core-concepts)

| 对象 | 理解方式 | 研究 Agent 示例 |
| --- | --- | --- |
| Trace | 一次逻辑执行的整体记录 | 完成一个财报问题 |
| Observation | 执行中的一个步骤 | 检索、解析、模型生成 |
| Generation | 模型生成相关观测 | 规划 query 或撰写答案 |
| Session | 多次交互的关联范围 | 用户连续追问同一主题 |
| Score | 对行为或产物的评价 | 引用正确率、任务通过与否 |
| Dataset item | 可重复运行的测试样本 | 问题、输入材料、参考约束 |
| Experiment / run | 某个配置在数据集上的执行 | 压缩方案 A 与 B 的比较 |
| Prompt version | 可定位的提示模板版本 | 证据检查器的第 3 版 |

命名时要区别“会话”“任务”“模型请求”。一个会话可能有多个任务，一个任务可能有几十次模型请求。若把它们全用一个 ID 表示，后续统计很容易混乱。

### 3.1 建议的关联字段

下面是本文建议保存的实验元数据，不是 Langfuse 强制 schema：

```json
{
  "task_id": "cashflow-017",
  "dataset_version": "research-v1",
  "model_id": "provider/model-snapshot",
  "harness_commit": "abc1234",
  "prompt_version": "evidence-check-v3",
  "toolset_version": "search-v2",
  "memory_snapshot": "memory-empty",
  "seed": 7,
  "budget_policy": "12-calls-24k-tokens"
}
```

这些字段回答的是“这一条轨迹到底由什么配置产生”。如果没有它们，看到成功率上升后也可能无法重现实验。

## 4. 怎样设计有用的轨迹树

```text
solve-question
├─ normalize-request
├─ retrieve-evidence
│  ├─ generate-query
│  ├─ search-api
│  └─ rerank-results
├─ parse-document
├─ check-evidence
├─ calculate-metrics
├─ draft-answer
└─ validate-citations
```

这棵树是教学示例。原则是让节点对应可诊断的职责，而不是给每一行代码建立 span。

每个工具节点至少记录输入摘要、输出摘要、开始结束时间、状态、尝试次数和错误类型。原始大文件可以保存为受控对象引用，不必重复塞入每条记录。

对上下文装配，还应额外保存：选中了哪些证据、去掉了哪些证据、压缩前后规模、是否保留来源标识。这样才能区分“检索未命中”和“命中后没进入模型”。

### 4.1 重试不能盖掉第一次失败

错误的记录方式是只保存最终成功结果。更有用的方式是保留 attempt 1 超时、attempt 2 返回、退避时间与累计成本。否则工具成功率、尾延迟和调用成本都会被美化。

### 4.2 并发不能直接相加求延迟

两个各耗时 5 秒的并行检索，可能只让用户等待约 5 秒，但消耗了两次调用。统计时分别看：

- 用户感知的端到端延迟；
- 关键路径耗时；
- 累计工具执行时间；
- 累计模型 token 与费用。

“步骤更少”和“整体更快”是两个不同结论。

## 5. 最小接入：先记录边界，再扩展细节

下面基于当前官方 Python SDK 的 context manager 形式编写。`search_documents` 是教学占位函数；示例用于理解埋点结构，未连接真实模型或 Langfuse 服务执行。[Tracing 入门](https://langfuse.com/docs/observability/get-started)

```python
from langfuse import get_client

langfuse = get_client()


def search_documents(query):
    return [{"id": "report-01", "title": "Example report"}]


def solve(question):
    with langfuse.start_as_current_observation(
        as_type="span", name="solve-question"
    ) as root:
        root.update(input={"question": question})
        with langfuse.start_as_current_observation(
            as_type="span", name="search-documents"
        ) as search:
            documents = search_documents(question)
            search.update(
                input={"query": question},
                output={"document_ids": [d["id"] for d in documents]},
            )
        root.update(output={"status": "evidence-collected"})


solve("Explain the cash-flow change")
langfuse.flush()
```

凭据通过环境配置提供，不写进源码。短生命周期脚本要注意 flush；异步和多线程执行要确认父子上下文是否正确传播。接入后第一件事应是检查实际轨迹，而不是仅看程序有没有报错。

## 6. 评测不只有一个 judge 分数

Langfuse 支持把人工、程序与模型评测等方法形成的结果记录为 score，并将在线轨迹转为离线实验样本。[评测概览](https://langfuse.com/docs/evaluation/overview)

我会把研究任务分为四组指标：

| 维度 | 指标示例 | 合适的评测方式 |
| --- | --- | --- |
| 硬约束 | JSON 合法、文件存在、公式正确 | 程序检查 |
| 内容正确 | 数值、时间范围、事实正确 | 参考答案与专家复核 |
| 证据质量 | 引用支持结论、来源可追溯 | 规则 + 盲评 |
| 运行效率 | token、费用、p95 延迟、重试 | 遥测统计 |

不要让同一个模型既生成答案、又凭主观印象选版本、最后再报告“自己评出的进步”，而不做任何外部校准。

### 6.1 Judge 至少要校准什么

1. 用一批人工标注检查模型评分与人的一致程度。
2. 交换 A/B 答案位置，检查位置偏差。
3. 构造语言漂亮但事实错误的负例。
4. 构造简短正确与冗长错误的对照。
5. 对分歧样本复核，不只看平均分。

评分器应该有自己的版本与测试集。评分提示一变，历史结果未必仍可直接比较。

## 7. 一个完整的 harness 对照实验

**假设：** 结构化证据表能减少遗漏，且总 token 增幅不超过 10%。这是教学实验目标，不是已有实测结果。

### 7.1 设计

- A：原始上下文装配方式。
- B：先将来源、时间、指标、证据片段整理成表，再生成答案。
- 固定：模型、工具、数据、预算上限、评测器、初始记忆。
- 每个任务运行 A/B 多次，执行次序随机化。
- 开发集调整方案，独立测试集只用于最终检验。

### 7.2 报告模板

| 指标 | A | B | 差异与区间 |
| --- | --- | --- | --- |
| 任务通过率 | 待测 | 待测 | 待测 |
| 引用支持率 | 待测 | 待测 | 待测 |
| 平均总 token | 待测 | 待测 | 待测 |
| p95 端到端延迟 | 待测 | 待测 | 待测 |
| 工具重试率 | 待测 | 待测 | 待测 |

配对差异比不相关的两次平均值更有解释力。对任务重采样计算区间时，应以任务为单位保留其多次运行结构，避免把同一任务的重复执行当作完全独立样本。

### 7.3 失败分类

把失败标成 retrieval、parse、context、reasoning、tool、evaluation 等类别。分类标签是工作假设，允许一条轨迹有多个原因，也允许“尚不能归因”。不要为了漂亮饼图强行指定单一根因。

## 8. 平台架构：为什么需要多种存储

当前 v4 自托管文档列出 Web、异步 Worker、Postgres、ClickHouse、Redis/Valkey 和对象存储。事务数据、分析数据、队列和原始事件分别由适合的组件承担。[自托管架构](https://langfuse.com/self-hosting)

从系统设计角度看，可以理解成两条路径：

```text
写入路径：接收事件 → 持久化原始事件 → 排队 → 异步处理
查询路径：元数据查询 / 轨迹分析 / 分数聚合 / 大对象读取
```

不要把这幅教学图当作完整生产协议。实际部署应固定版本，并核对文档中的存储职责与失败恢复方式。

对学习者来说，优先理解异步写入的取舍：主业务不必等待全部分析处理，但刚产生的事件可能不会立即出现在查询结果中。测试时要区分 SDK 发送、服务接收、后台入库和界面可见这几个时刻。

## 9. Prompt 管理与实验可复现性

官方 prompt management 提供集中存储、版本与部署标签，并可把使用的 prompt 关联到轨迹。[Prompt 管理](https://langfuse.com/docs/prompt-management/overview)

工程上需要进一步区别：

- 标签是可移动的入口，例如 production。
- 版本是这次执行真正使用的模板快照。
- 变量值决定最终输入，模板相同不等于输入相同。
- 模型别名可能漂移，尽可能保存可定位的模型标识。

只记“使用 production prompt”不足以重现三周前的一次执行。最好同时记模板版本、变量、工具配置与 harness commit。

## 10. 源码阅读路径

以[固定快照](https://github.com/langfuse/langfuse/tree/f6c3660ced73d380f1936d2adb0cca97f16e4d2a)为起点，带着问题读，而不是试图一次读完整个平台。

| 入口 | 阅读问题 |
| --- | --- |
| `web/` | API、页面、权限与领域对象怎样组织？ |
| `web/src/features/evals/` | 评测配置、模板与执行日志怎样关联？ |
| `worker/` | 哪些处理被放入异步工作流？ |
| `packages/` | Web 与 Worker 如何共享模型和逻辑？ |
| 官方 SDK 文档 | 上下文如何传播，事件何时发送？ |

这些是阅读入口，不表示本文审计了目录内全部实现。建议先追踪“一条 observation 从 SDK 到可查询结果”的数据流，再追踪“一条 score 如何关联实验”。

## 11. 常见误区与排查

| 误区 / 症状 | 更准确的解释 / 排查 |
| --- | --- |
| 有 trace 就能重放 | 重放还需要环境、输入和副作用处理 |
| 最后成功，所以工具无故障 | 查看每次重试和累计耗时 |
| 分数提升就是模型进步 | 同时固定工具、记忆、预算与评分器 |
| 接入后所有链路自动完整 | 检查异步上下文、包装层和缺失 span |
| 所有原文全部记录最安全 | 原文可能含敏感内容，也会增加存储成本 |
| 日志清理等于删除业务数据 | 遥测库与业务库生命周期不同 |
| 同一个任务算一个 span 就够 | 只能看结果，难定位中间责任 |

可观测数据本身也需要保留策略。记录足够的证据与版本，避免无边界采集凭据、个人数据和无关文件。

## 12. 一天 5 小时实操安排

| 时间 | 动作 | 验收产出 |
| --- | --- | --- |
| 45 分钟 | 阅读对象与 SDK 文档 | 一张任务对象关系表 |
| 75 分钟 | 为最小搜索 Agent 加埋点 | 可检查的轨迹树 |
| 60 分钟 | 构建 20 个开发案例 | 输入、约束和失败标签 |
| 75 分钟 | 对比两版上下文策略 | 配置表与原始运行记录 |
| 30 分钟 | 检查至少 5 个失败案例 | 归因证据与不确定性 |
| 15 分钟 | 闭卷复述 | 解释为何 score 不是能力本身 |

这 20 个案例用于打通流程，不能自动支持统计显著性或生产泛化结论。正式实验应依据任务方差和期望效应决定样本量。

## 13. 自测题与参考要点

先回答，再展开要点：

1. Trace、session 和任务 ID 分别解决什么问题？
2. 为什么最终重试成功后，仍要保留前几次错误？
3. 同时改变模型和 prompt，怎样影响结果解释？
4. Judge 喜欢更长答案时，怎样发现偏差？
5. 为什么遥测轨迹无法独自保证安全恢复？

<details>
<summary>参考要点</summary>
<p>1. 整体执行、跨交互关联和业务任务身份是不同维度。2. 失败决定真实成本、可靠性和尾延迟。3. 无法独立归因，至少需要交叉对照或逐项消融。4. 做长度与正确性解耦的负例，结合盲评校准。5. 恢复需要持久状态、幂等和环境副作用语义。</p>
</details>

## 14. 五分钟复习卡

- 核心作用：记录、关联、评分与比较执行行为。
- 最小闭环：trace → 失败样本 → dataset → 实验 → 改动 → 回归。
- 最重要的版本：模型、prompt、工具、harness、数据、记忆、judge。
- 最重要的边界：观测不等于恢复，评分不等于真值。
- 最重要的实验要求：成对任务、固定预算、独立测试、保留失败。

## 15. 资料与系列导航

官方资料：

1. [Langfuse 项目与固定源码快照](https://github.com/langfuse/langfuse/tree/f6c3660ced73d380f1936d2adb0cca97f16e4d2a)
2. [Tracing 入门](https://langfuse.com/docs/observability/get-started)
3. [Evaluation 核心概念](https://langfuse.com/docs/evaluation/core-concepts)
4. [Evaluation 概览](https://langfuse.com/docs/evaluation/overview)
5. [Prompt Management](https://langfuse.com/docs/prompt-management/overview)
6. [自托管与架构](https://langfuse.com/self-hosting)

系列：[Langfuse](/notes/agent-evolution-01-langfuse/) · [OpenViking](/notes/agent-evolution-02-openviking/) · [Mem0](/notes/agent-evolution-03-mem0/) · [Harness²](/notes/agent-evolution-04-harness2/) · [Dream-RSI](/notes/agent-evolution-05-dream-rsi/)
