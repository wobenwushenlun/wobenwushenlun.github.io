---
title: "Agentic RL 学习 04：沿着一条轨迹读懂 rLLM"
date: 2026-08-26 12:00:00 +0800
categories:
  - Agentic RL
tags:
  - rLLM
  - AgentFlow
  - Workflow
  - 源码阅读
excerpt: "不再从 README 顺着看，而是从本地 trajectory JSON 反向追踪：它在哪里生成、怎样计算奖励、如何构造 mask，最后怎样进入优化器。"
pin: false
---

这一篇解决一个很具体的问题：**面对 rLLM 这样的大型训练框架，源码应该从哪里开始看？**

我最初按目录从头读 [rLLM](https://github.com/rllm-org/rllm)，很快就迷路了。后来换了个办法：先找一条本地 trajectory JSON，再顺着里面的字段反向追代码。这样每走一步都有数据可以对照。

## 第一步：先对上代码版本

rLLM 的文档和主分支在演进中出现过不同抽象。早期材料更多使用 `Workflow → RolloutEngine`，较新的主路径则偏向 `AgentFlow → Model Gateway → Trainer`。

这类项目最容易踩的坑，是拿旧文档里的类名去解释新代码。因此源码阅读的第一步不是搜索函数，而是确认：

- 当前 checkout 的 commit；
- 示例使用 Workflow 还是 AgentFlow；
- rollout 由哪个服务生成；
- trainer 接收的样本结构是什么。

## 第二步：先找 JSON 里的四组“指纹”

我把轨迹中的关键字段分成四组。

### 会话：这条轨迹从哪里来

`episode.id`、`session_id` 或类似字段用于定位这一局由谁启动、经过哪些步骤。它们适合追生成入口和日志。

### 分组与奖励：它为什么拿到这个分数

`trajectory.name`、`group_id`、`reward` 可以帮助定位同一问题的多次采样，以及 reward 在哪里被写回。

### Token：哪些内容真的进入训练

`prompt_ids`、`response_ids`、`attention_mask`、`loss_mask` 是从轨迹进入训练张量的桥梁。看到这些字段后，重点追踪 tokenizer、padding、环境 token 屏蔽和 response 截断。

### 优化：这条数据有没有真正更新模型

`advantage`、`old_log_prob`、`weight_version` 可以回答：优势在哪里计算、rollout 是否来自过旧权重、哪批数据真正参与了优化。

## 第三步：按数据流反向追代码

我现在会按下面的顺序读这类框架：

```text
本地 Episode / Trajectory JSON
        ↓
序列化与保存函数
        ↓
rollout / gateway 的生成入口
        ↓
环境执行与 step 状态推进
        ↓
evaluator / reward 写回
        ↓
tokenization 与 loss mask
        ↓
advantage 计算
        ↓
trainer 的 PPO / GRPO loss
```

对我来说，这比从 trainer 正向硬读有效得多。每到一层，我都能拿 JSON 里的字段核对，而不是盯着抽象接口猜数据长什么样。

## 追代码时，我只问四个问题

### 1. 这条轨迹怎么生成的

确认一次 rollout 怎样选择模型版本、采样参数、最大轮数和工具预算。这里还要关注超时、异常和未完成轨迹怎样标记。

### 2. 奖励在哪里写进去的

确认 reward 是 episode 级、trajectory 级还是 step 级；多个 evaluator 怎样组合；格式错误和环境失败是否有单独惩罚。

### 3. 哪些 token 被 mask 了

确认哪些 token 是模型真正生成的。系统提示、用户输入、工具观察和 padding 通常不应进入策略损失。Agent 训练中一个 mask 错误，足以让表面正常的 loss 学向完全错误的目标。

### 4. 最后怎么进入优化器

确认样本怎样分组、优势怎样归一化、KL 和 clipping 在哪里计算，以及 loss 最终按 token、序列还是固定常数归一化。

## “固定 Gym 环境”固定的是什么

rLLM 的示例经常把任务封装成类似 Gym 的环境：`reset()` 给出初始状态，`step(action)` 推进环境并返回观察、奖励和结束标记。

“固定环境”不代表每次轨迹相同，而是指状态转移规则和评测规则在训练期间保持稳定。这样 reward 变化更有可能来自策略变化，而不是环境实现悄悄改变。

## 这一篇，我记住了什么

框架的价值不只在于提供一个训练命令，而在于把以下契约固定下来：

```text
Agent 如何表达动作
环境如何返回观察
轨迹如何保存
奖励如何挂到轨迹
哪些 token 可以训练
样本怎样进入优化器
```

读到优化器这一层时，我又遇到了几个必须补齐的概念：rejection sampling、Monte Carlo return、GAE，以及 GRPO 与 Dr.GRPO 的差别。

## 资料

- [rLLM 官方仓库](https://github.com/rllm-org/rllm)
- [rLLM Workflow 文档](https://rllm-org-rllm.mintlify.app/api/workflows)
- 上一篇：[把 Agent 执行与训练拆开](/notes/agentic-rl-03-agent-lightning/)
- 下一篇：[Agentic RL 学习 05：从回报估计到 Dr.GRPO](/notes/agentic-rl-05-grpo-foundations/)
