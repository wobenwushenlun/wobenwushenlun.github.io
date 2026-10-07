---
title: Jev 学习笔记：把语义判断接进程序
date: 2026-10-07 00:00:00 +0800
categories:
- AI 前沿
tags:
- Jev
- TypeSafe AI
- System One
- RLCD
- 工作流自动化
excerpt: 从一张工单理解 Jev 的 state、Choice、Score 和 Noul，记下置信度、结构化输出与业务正确性之间的区别。
order: 1
pin: false
---

之前学习 Agent 时，我比较熟悉的流程是：模型接收消息，生成回答，或者发起工具调用。读 Jev 的资料时，我想弄明白的是另一件事：**如果程序只需要一个判断，模型接口应该长什么样？**

这篇先从工单分类入手，把 Jev 的输入输出、置信度和适用范围整理清楚。资料核对日期：**2026-10-07**；下面是阅读官方资料后的理解，还没有实际调用 API。

## 1. 从一个具体需求开始

假设收到这样一条消息：

> 接口已经连续三天报错，影响营业了，麻烦尽快处理。

工单系统需要知道的是：分给技术还是售后，优先级多高，是否需要人工复核。最终参与程序分支的，可能只是一个类别和几个数值。

Jev 是 TypeSafe AI 在 2026 年 9 月 15 日发布的 System One 模型，面向快速、结构化决策。我的理解是：可以把它放在程序里那些“需要理解语义，手写规则又太脆弱”的位置。[发布文章](https://typesafe.ai/blog/introducing-system-one-models-and-jev)

“System One”借用了快思考的概念。学习时先把它理解成这类模型的定位，具体能力还是要看任务表现。

## 2. state 放材料，questions 写清楚要判断什么

官方接口的基本结构是：

```text
state：所有问题共同参考的材料
questions：针对材料提出的一组有类型的问题
answers：程序可以读取的结构化结果
```

三个问题类型可以这样记：

| 类型 | 我会怎样问 | 返回内容 |
| --- | --- | --- |
| Choice | 技术、售后、销售，选哪一个？ | 选项、概率分布、置信度 |
| Score | 按给定标准，这条工单有多紧急？ | 分数、概率分布、置信度 |
| Noul | “用户表达了紧迫性”是否成立？ | 0 到 1 的值 |

这里有两个细节容易忽略。第一，Score 需要提供评分标准，不能默认大家对“严重”理解一致。第二，同一请求中的问题针对相同 state 独立评估；如果后一个问题依赖前一个结果，就需要在代码里组织下一步。[接口与问题类型](https://docs.typesafe.ai/introduction)

下面只是工单设计草图，不是可直接运行的 SDK 代码：

```text
state = 工单原文

questions:
  department: Choice(技术 / 售后 / 销售)
  urgency: Score(普通咨询 / 影响部分功能 / 无法营业)
  asks_refund: Noul(用户明确提出退款)
```

“影响营业”不能自动推出“要求退款”。把它们拆开，才能看到程序究竟依据了哪些判断。

## 3. 判断交给模型，组合关系写在代码里

如果提示词只有一句“处理这张工单”，部门、紧急度和业务动作很容易混在一起。拆成原子问题后，程序可以明确组合这些结果。

```text
工单 → Jev 给出各项判断
     → 代码检查结果和置信度
     → 按业务规则分配，或转交复核
```

下面是教学用的伪代码，`threshold` 需要用自己的数据验证：

```python
if department_confidence < threshold:
    send_to_review(ticket)
else:
    assign_ticket(ticket, department)
```

这让我想到 Agent 的控制循环：模型可以提供下一步判断，但最终执行什么、何时停止、何时升级处理，都需要清楚的控制逻辑。Jev 的官方文档也建议拆解复杂问题，再在代码中组合。[问题设计建议](https://docs.typesafe.ai/introduction)

## 4. 置信度和“零幻觉”要分开理解

官方称其训练方法为 RLCD，即 Reinforcement Learning for Calibrated Decisions，强调校准过的决策概率。[训练方向说明](https://typesafe.ai/blog/introducing-system-one-models-and-jev)

我先记住“校准”的直观含义：在一批可比较的预测里，如果系统经常报出约 90% 的把握，那么这些预测的实际正确率也应接近这个水平。它是统计意义上的性质，无法保证某一次判断正确。

另一个容易混淆的点是输出结构。即使返回值一定属于合法候选项，也可能选错：

```text
输出“技术” → 类型合法，但可能判断错部门
输出“一个未定义的新部门” → 输出结构本身出了问题
```

所以阅读官方的“零幻觉”表述时，我会把结构保证和判断正确率分开。真正接入前，还要看高置信度错误、信息不足和模糊样本。

## 5. 性能数字先连同条件一起记

发布时，官方给出的端到端延迟为 70–500 毫秒，输入价格为每百万 token 0.042 美元，决策输出不收费。约 194 倍提速、445 倍降本来自其特定工作流评测，官方也说明这些收益可能处于真实场景的较高端。[数字来源与限定条件](https://typesafe.ai/blog/introducing-system-one-models-and-jev)

这组数字让我注意到：大量短判断可能值得使用专门的模型。但如果要写长文、生成代码或做多步调查，还需要生成能力和外部流程。具体是否划算，要比较整个任务的正确率、延迟和费用。

## 6. 留给下一次实践的问题

我会先选一个已有人工标签的分类任务，用同一批材料比较规则、现有模型和 Jev。暂时要记住三个检查点：

- 错误集中在哪类样本？候选项描述是否清楚？
- 置信度降低时，实际错误率是否上升？
- 加入复核和后续步骤后，总耗时与费用是多少？

目前对 Jev 的理解是：它提供一个语义判断接口，程序负责把判断组织成可检查的业务流程。

## 参考资料

- [TypeSafe AI 发布文章](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
- [官方文档](https://docs.typesafe.ai/introduction)
- [快速入门](https://docs.typesafe.ai/introduction/quickstart)

## 相关笔记

- [Muse 学习笔记：个人 Agent 怎样持续完成任务](/notes/muse-personal-agent/)
- [Mostik 学习笔记：模型之间为什么要传隐藏状态](/notes/mostik-latent-communication/)
