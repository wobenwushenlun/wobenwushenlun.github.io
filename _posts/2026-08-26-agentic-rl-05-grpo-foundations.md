---
title: "Agentic RL 学习 05：从回报估计到 Dr.GRPO"
date: 2026-08-26 13:00:00 +0800
categories:
  - Agentic RL
tags:
  - GRPO
  - Dr.GRPO
  - GAE
  - Rejection Sampling
excerpt: "补齐 Agentic RL 优化层的基础：Monte Carlo return 与 GAE、组内相对优势、rejection sampling，以及 Dr.GRPO 想修正的长度偏置。"
pin: false
---

上一篇把轨迹一路追到了 trainer，这一篇就补优化层。我主要想理清四件容易混在一起的事：**奖励怎么加、样本怎么筛、优势怎么算、不同长度的回答怎么聚合 loss。**

把这四件事分开之后，GRPO 和 Dr.GRPO 就没那么绕了。

## 先看 reward_bonus_coeff：额外奖励占多大比重

环境通常给出基础任务奖励，训练代码还可能加入格式、探索、工具使用或过程质量奖励：

```text
总奖励 = 任务奖励 + bonus_coeff × 额外奖励
```

`reward_bonus_coeff` 就是额外奖励的权重。它不是越大越好：过小起不到引导作用，过大则可能让模型只优化 bonus，忽略真实任务目标。

因此每加一种 reward，都应该单独监控其数值分布和与成功率的相关性。

## Rejection sampling：先生成，再筛掉一部分

广义的 rejection sampling 是“生成候选，再按条件拒绝一部分”。在 Agent RL 数据管线中，它经常用于：

- 丢弃格式错误或环境执行失败的 rollout；
- 过滤过长、空响应或非法工具调用；
- 为 GRPO 去掉组内全对或全错、没有相对信号的样本组；
- 从多个候选中保留满足质量阈值的轨迹。

但过滤不是免费的。过滤越强，数据越干净，却也越容易改变原始策略的采样分布，并减少困难样本。

## Monte Carlo return 和 GAE 差在哪

Monte Carlo return 直接使用从当前时刻到 episode 结束的实际折扣回报：

```text
G_t = r_t + γr_(t+1) + γ²r_(t+2) + ...
```

它偏差较小，但方差大，而且必须等整条轨迹结束。

GAE 则结合 value function，用多步 TD 误差的加权和估计 advantage：

```text
δ_t = r_t + γV(s_(t+1)) - V(s_t)
A_t = δ_t + γλδ_(t+1) + (γλ)²δ_(t+2) + ...
```

`λ` 控制偏差—方差折中。GAE 更平滑，但需要训练 critic。很多 GRPO 方案选择组内相对奖励，是为了避免单独训练 value model。

## GRPO：在同一道题的答案里比好坏

对同一个问题采样一组回答，得到奖励 `r_1 ... r_G`，GRPO 用组内均值和标准差构造相对优势：

```text
A_i = (r_i - mean(r)) / std(r)
```

它回答的其实很朴素：同一道题采样出的这些候选里，谁比平均水平更好，谁更差？

随后再用 PPO 风格的 ratio clipping 限制策略更新幅度。这里要分清两个位置：

- advantage normalization 决定每条轨迹的相对训练信号；
- loss normalization 决定不同长度轨迹和不同 batch 怎样聚合。

## Dr.GRPO：别让长度归一化悄悄改了目标

标准实现中常见的样本级或 token 级归一化，可能产生长度偏置。例如先对每条回答按自身 token 数求平均，再对 batch 求平均，会让短回答和长回答以不直观的方式影响梯度。

Dr.GRPO 的核心方向，是移除或修改这些会引入偏置的归一化项，用固定尺度聚合 token loss，使目标更接近原始策略梯度形式。

我的理解是：

> GRPO 解决“没有 critic 时怎样获得相对 advantage”，Dr.GRPO 进一步追问“这个 advantage 进入 token loss 后，是否又被长度归一化扭曲了”。

## 为什么 Agent 场景更怕长度偏置

Agent 的长轨迹不一定代表更高质量，可能只是：

- 重复思考；
- 无效工具调用；
- 搜索失败后不断绕路；
- 环境观察文本很长；
- 到达最大轮数才被迫停止。

因此不能只看平均 reward，还要同时记录：

```text
成功率
模型生成 token 数
环境 observation token 数
工具调用轮数
单位 token 回报
不同长度区间的 advantage 与梯度贡献
```

## 把整条优化链再串一次

到这里，一条 Agent RL 训练链路终于能完整串起来了：

```text
环境产生 trajectory
→ evaluator 给 reward
→ 过滤无效或无信息样本
→ 计算 return / relative advantage
→ 构造 token mask
→ clipped policy loss
→ 按合理尺度聚合并更新参数
```

最后，我把这些概念带到更复杂的多模态搜索 Agent 中，看看数据构造和评测体系会增加哪些新问题。

## 资料

- 上一篇：[沿着一条轨迹读懂 rLLM](/notes/agentic-rl-04-rllm/)
- 下一篇：[Agentic RL 学习 06：多模态搜索 Agent 的数据与评测](/notes/agentic-rl-06-opensearch-vl/)
