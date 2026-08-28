---
title: "Agentic RL 学习 03：把 Agent 执行与训练拆开"
date: 2026-08-26 11:00:00 +0800
categories:
  - Agentic RL
tags:
  - Agent Lightning
  - Credit Assignment
  - 轨迹
  - 学习笔记
excerpt: "Agent Lightning 带来的工程视角：保留原有 Agent 运行方式，把每次模型调用记录成 transition，再独立完成奖励分配与训练。"
pin: false
---

前两篇主要在看算法。这一篇转向工程问题：**一个已经能跑的 Agent，怎么接上强化学习，又不用把整个项目推倒重写？**

[Agent Lightning](https://github.com/microsoft/agent-lightning) 给我的答案是：先让 Agent 照常运行，把每次模型调用记录下来；执行结束后，再单独做奖励分配和训练。

## 先别急着把整局拼成长文本

一种直接做法，是把整局 Agent 交互拼成一条长序列：

```text
系统提示 + 用户问题 + 第一次回答 + 工具结果
+ 第二次回答 + 工具结果 + ... + 最终答案
```

但真实 Agent 可能由多个模块组成，还包含数据库、搜索服务、业务代码甚至其他模型。把所有东西塞进一条训练序列，会让数据边界、mask 和信用分配越来越难维护。

Agent Lightning 的关键抽象，是把每一次 LLM 调用记录成相对独立的 transition：

```text
输入上下文
→ 模型输出
→ 工具或环境反馈
→ 关联的奖励与元数据
```

整个 Agent 仍然按照原来的工作流运行，训练系统在旁边收集轨迹，再把最终回报分配给相关调用。

## 把运行和训练拆成两条线

我把它理解为两条管线：

```text
执行管线：Agent → 工具 → 环境 → 任务结果
训练管线：轨迹存储 → 信用分配 → 训练样本 → 参数更新
```

这样拆开不只是代码更好看，实际好处也很直接：

- Agent 可以继续使用现有框架和工具；
- rollout 服务与训练服务可以独立扩缩容；
- 同一条轨迹可以尝试不同的奖励和信用分配方法；
- 多个模型调用可以分别构造训练样本；
- 线上执行数据与离线训练之间有了明确接口。

## Credit assignment 到底在分什么

假设一个 Agent 有规划、搜索、阅读和回答四次模型调用，最终任务得到奖励 1。最粗糙的方法是把 1 同样分给每次调用，但这隐含了“所有步骤贡献相同”的假设。

更精细的分配可以考虑：

- 哪个 span 产生了关键工具查询；
- 哪个步骤首次找到有效证据；
- 哪个输出导致环境进入失败状态；
- 最终答案对应哪些上游调用。

因此，信用分配不是一个抽象术语，而是从“任务级 reward”生成“调用级或 token 级训练信号”的数据变换过程。

## 没有完整日志，后面很难查错

学到这里，我发现训练问题经常首先是可观测性问题。如果轨迹里没有稳定记录下面这些信息，后续很难排查：

```text
episode_id：属于哪一局任务
span_id：属于哪一次模型或工具调用
parent_id：调用之间的因果关系
model_version：rollout 使用了哪版权重
prompt / response：实际输入输出
reward：任务级和局部奖励
timing：调用延迟与顺序
```

Agent RL 的基础设施，本质上需要一套能把“运行现场”还原出来的 tracing 系统。

## 它和 RAGEN 分别在解决什么

RAGEN 更关心多轮 RL 的训练动力学：策略为何坍缩、怎样保持有效探索。Agent Lightning 更关心训练系统如何接住现实世界中异构的 Agent 执行。

二者并不冲突：一个回答“怎样稳定优化”，另一个回答“怎样把可优化的数据送进来”。

## 这一篇，我记住了什么

我开始用三个层次理解 Agentic RL：

```text
Agent 层：规划、工具调用和环境状态
数据层：episode、span、transition 和 reward
优化层：advantage、mask、loss 和参数更新
```

接下来，我想在一个更完整的开源训练框架里把这三层对应起来，于是进入了 rLLM。

## 资料

- [Agent Lightning 官方仓库](https://github.com/microsoft/agent-lightning)
- 上一篇：[多轮训练为什么会崩](/notes/agentic-rl-02-ragen/)
- 下一篇：[Agentic RL 学习 04：沿着一条轨迹读懂 rLLM](/notes/agentic-rl-04-rllm/)
