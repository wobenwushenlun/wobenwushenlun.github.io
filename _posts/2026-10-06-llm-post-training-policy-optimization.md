---
title: "大模型后训练方法地图：从 PPO、DPO 到 GRPO、GSPO 与 SAPO"
date: 2026-10-06 12:00:00 +0800
categories:
  - Agentic RL
tags:
  - PPO
  - DPO
  - GRPO
  - Dr.GRPO
  - DAPO
  - GSPO
  - SAPO
excerpt: "从 reward、value、advantage 和 importance ratio 出发，梳理 PPO、DPO 与组策略优化家族分别解决什么问题，以及算法为何这样演进。"
pin: false
---

PPO、DPO、GRPO、Dr.GRPO、DAPO、GSPO 和 SAPO 经常被放在同一张表里，但它们并不是一条严格的版本升级链。更准确的关系是：**DPO 是离线偏好学习路线；PPO 是经典在线 RLHF 路线；GRPO 去掉了 PPO 的价值模型，而 Dr.GRPO、DAPO、GSPO 和 SAPO 又分别修正 GRPO 家族中的不同问题。**

```text
偏好对齐
├─ 离线偏好优化
│  └─ DPO：直接学习 chosen > rejected
└─ 在线强化学习
   ├─ PPO：奖励模型 + 价值模型 + GAE
   └─ 组策略优化：用同题多回答的相对奖励代替价值模型
      ├─ GRPO：token 级 ratio + 硬裁剪
      ├─ Dr.GRPO：修正标准差和回答长度归一化偏置
      ├─ DAPO：改善裁剪、采样、loss 聚合和超长回答处理
      ├─ GSPO：sequence 级 ratio + 硬裁剪
      └─ SAPO：token 级 ratio + 平滑软门控
```

## 先统一四个容易混淆的量

理解这些算法之前，要先把奖励、回报、优势和重要性比率分开。

| 概念 | 回答的问题 | 典型形式 |
| --- | --- | --- |
| Reward | 这一步或整条回答得了多少分？ | `r_t` 或回答总分 `R_i` |
| Return | 从当前位置开始，后续累计能得到多少奖励？ | `G_t = r_t + gamma*r_(t+1) + ...` |
| Value | 从当前状态出发，预计能得到多少回报？ | `V(s_t)` |
| Advantage | 这次动作相对基线到底好多少？ | `A_t = G_t - V(s_t)` 或组内相对奖励 |
| Importance ratio | 当前策略相对采样时的旧策略改变了多少？ | `rho = pi_theta / pi_old` |

奖励模型和价值模型也不是同一个角色：奖励模型定义“什么回答好”，价值模型预测“从当前前缀继续生成，预计最终能拿多少分”。策略更新直接使用的是 advantage，但 advantage 的计算依赖奖励信号；没有奖励，价值模型也不知道应该预测什么。

在经典 LLM RLHF 中，奖励模型通常读取完整的 `prompt + response`，在结尾给一个回答级总分，并不是逐 token 判断哪一个词写得好。每个 token 位置可能还有算法构造的 KL 惩罚，但这不等于奖励模型逐 token 打分。

## PPO：完整但昂贵的在线 RLHF

PPO 的典型训练流程是：

```text
策略模型生成完整回答
→ 奖励模型给回答打分
→ 价值模型预测每个生成状态的未来回报
→ 用奖励序列和 value 通过 GAE 计算逐 token advantage
→ 用新旧策略概率比和 clipping 更新策略模型
→ 用回报目标更新价值模型
```

对第 `t` 个 token，PPO 计算：

```text
rho_t = pi_theta(y_t | s_t) / pi_old(y_t | s_t)
```

并用裁剪目标限制一次更新不要离旧策略太远：

```text
min(rho_t * A_t, clip(rho_t, 1-epsilon, 1+epsilon) * A_t)
```

如果 `A_t > 0`，模型会提高这次所选 token 的概率；如果 `A_t < 0`，则降低其概率。价值模型作为 baseline 可以显著降低策略梯度方差，并让同一回答中不同位置得到不同的 advantage。

代价是训练系统通常要维护策略模型、参考模型、奖励模型和价值模型。价值模型规模往往接近策略模型，显存、计算和工程复杂度都比较高。

## DPO：把偏好优化变成成对排序

DPO 走的是另一条路线。它使用离线偏好数据：

```text
prompt
├─ chosen：人类更偏好的回答
└─ rejected：人类较不偏好的回答
```

DPO 可以理解为回答对上的二分类或排序学习。它比较当前模型相对于参考模型，对 chosen 和 rejected 的偏好差：

```text
score = [log pi_theta(chosen) - log pi_ref(chosen)]
      - [log pi_theta(rejected) - log pi_ref(rejected)]

loss = -log sigmoid(beta * score)
```

它在工程上很像 SFT：都是离线 teacher forcing，前向计算已有文本的 token log probability，再反向传播；不需要在线 rollout、奖励模型、价值模型、GAE 或 PPO clipping。

但两者的目标不同：

- SFT 只提高标准回答的似然，学习“应该怎样回答”；
- DPO 同时比较 chosen 和 rejected，学习“两个回答中应该更偏好哪一个”。

DPO 优点是简单、稳定、成本低；局限是能力上限受已有偏好数据覆盖范围约束，不能像在线 RL 一样持续生成新轨迹、获得新反馈并探索新的解法。

## GRPO：用组内比较代替价值模型

GRPO 保留在线生成与奖励，但去掉价值模型。它对同一个 prompt 采样 `G` 条完整回答，分别获得回答级奖励 `R_i`，然后计算组内相对 advantage：

```text
A_i = (R_i - mean(R_1 ... R_G)) / (std(R_1 ... R_G) + epsilon)
```

同一条回答中的所有 completion token 通常共享同一个 `A_i`。Prompt token 只是上下文，会在策略损失中被 mask 掉。

随后，每个 token 仍使用自己的重要性比率：

```text
rho_(i,t) = pi_theta(y_(i,t) | x, y_(i,<t))
            / pi_old(y_(i,t) | x, y_(i,<t))
```

再分别执行 PPO 风格的硬裁剪。因此，GRPO 不是“给每个 token 单独计算语义奖励”：回答级 reward 和 advantage 是共享的，不同 token 的是概率比、裁剪状态和最终梯度。

GRPO 的主要优势是省掉了 Critic，尤其适合数学、代码等可以用答案校验器或测试用例给分的 RLVR 任务。主要问题包括：

- 同一回答所有 token 共享一个粗粒度 advantage，信用分配有限；
- token 级概率比可能产生高方差，长序列会累积噪声；
- MoE 模型的专家路由变化会进一步放大新旧策略概率差异；
- 组内全对或全错时，所有 advantage 都为零，没有训练信号。

更细的 return、GAE 和 GRPO 基础记录见：[从回报估计到 Dr.GRPO](/notes/agentic-rl-05-grpo-foundations/)。

## Dr.GRPO：修正两个隐性归一化偏置

Dr.GRPO 即 GRPO Done Right。它认为原始 GRPO 的两个归一化项悄悄改变了不同样本的训练权重。

第一是题目级难度偏置。GRPO 用每道题的组内奖励标准差做除数：

```text
(R_i - mean(R)) / std(R)
```

不同题目的 `std(R)` 不同，相当于又给题目乘上了不同尺度。Dr.GRPO 删除标准差归一化，只保留中心化：

```text
A_i = R_i - mean(R)
```

第二是回答长度偏置。常见 GRPO 实现先对每条回答按自身长度取平均：

```text
(1 / length_i) * sum_t loss_(i,t)
```

这会使长错误回答中的每个 token 受到更弱惩罚，可能推动错误回答越写越长。Dr.GRPO 删除按每条回答自身长度归一化，改用固定尺度聚合 token loss，从而减少无效长推理和 overthinking。

需要注意，删除长度归一化后，长回答因为 token 更多，也可能贡献更多总梯度。这里存在“策略梯度无偏”和“每条长短回答贡献相同”之间的取舍，所以 Done Right 并不意味着它在所有任务上都绝对最优。

## DAPO：面向长 CoT 的一组训练配方

DAPO 是 Decoupled Clip and Dynamic sAmpling Policy Optimization。它不是把 GRPO 的核心目标整体换掉，而是在 GRPO 风格训练上增加四项关键改进。

### 非对称裁剪 Clip-Higher

GRPO 常用对称区间 `[1-epsilon, 1+epsilon]`。DAPO 把上下界解耦，并通常令上界更宽：

```text
[1-epsilon_low, 1+epsilon_high]
epsilon_high > epsilon_low
```

这给低概率但有潜力的 token 更大的概率上升空间，避免正向探索刚开始就被截断，缓解策略熵过快下降。

### Dynamic Sampling

如果同一题采样出的回答全部正确或全部错误，组内 advantage 为零。DAPO 过滤这种退化组，并继续采样，直到 batch 中有足够多同时包含正确和错误答案的有效组。

这样提高了有效梯度密度，但也会改变训练题目的难度分布：过易题和过难题可能被系统性减少。

### Token-Level Policy Gradient Loss

GRPO 常先按每条回答长度求平均，再对回答求平均；DAPO 改为对 batch 中所有有效 completion token 统一平均：

```text
sum(all token losses) / number_of_all_valid_tokens
```

因此长回答包含更多 token，也会贡献更多总梯度。这更接近 token 级优化视角，但必须与长度控制配合使用。

### Overlong Reward Shaping

回答超过最大生成长度而被截断时，直接给一个突兀的负奖励可能误伤原本合理、只是尚未写完的推理。DAPO 在接近长度上限时逐步增加惩罚，让奖励变化更平滑，减少截断噪声。

简而言之，DAPO 主要解决的是：**探索空间太窄、无效组浪费算力、长短回答 loss 聚合不合理，以及截断奖励过于粗暴。**

## GSPO：让优化粒度与奖励粒度一致

GRPO 使用整条回答的奖励，却对每个 token 的概率比分别裁剪。GSPO 认为这是粒度不匹配，于是把一条回答内所有 token 的概率比聚合为长度归一化的序列级比率：

```text
s_i = exp(mean_t(log rho_(i,t)))
```

也就是 token 概率比的几何平均，然后对整条回答统一执行：

```text
min(s_i * A_i, clip(s_i, 1-epsilon, 1+epsilon) * A_i)
```

这样，回答级 reward、回答级 advantage、序列级重要性比率和序列级 clipping 处在同一粒度上。长度归一化使不同长度回答的比率保持在相近数值尺度，特别有利于长序列和 MoE 模型的稳定训练。

它的代价是粒度更粗：如果少数异常 token 把序列比率推过裁剪边界，整条回答的策略梯度都可能被压制，有效的正常 token 也会一起失去训练信号。

## SAPO：用软门控代替硬裁剪

SAPO 即 Soft Adaptive Policy Optimization。它回到 token 级概率比，但不再做“范围内保留、范围外归零”的硬裁剪，而是用以 `rho=1` 为中心的平滑门控：

```text
p_(i,t) = sigmoid(tau * (rho_(i,t) - 1))
w_(i,t) = 4 * p_(i,t) * (1 - p_(i,t))
```

当 `rho` 接近 1 时，门控权重接近 1；偏离越大，梯度权重越平滑地衰减。假设一条回答的 token 比率为：

```text
[1.01, 1.03, 1.00, 1.80]
```

SAPO 会基本保留前三个接近旧策略的 token，只对最后一个严重离策略的 token 大幅降权。相比之下，GRPO 对 token 做硬裁剪，GSPO 则可能统一裁掉整条序列。

SAPO 还可对正、负 advantage 使用不同温度，通常让负向更新衰减更快，以减少不稳定。它试图同时获得序列层面的整体稳定性和 token 层面的选择性，但代价是引入了额外温度超参数，而且作为较新的方法，其适用范围仍需要更多任务和规模验证。

## 把七种方法放到同一张表里

| 算法 | 数据与反馈 | Advantage / 训练信号 | Ratio 与约束粒度 | Value 模型 | 主要解决的问题 |
| --- | --- | --- | --- | --- | --- |
| PPO | 在线 rollout + 奖励模型/环境奖励 | Value + GAE，逐 token 可不同 | token 级硬裁剪 | 需要 | 通用在线 RL 与细粒度信用分配 |
| DPO | 离线 chosen/rejected | 回答对排序损失 | 参考模型约束，无 PPO clipping | 不需要 | 简化偏好对齐，避免在线 RL |
| GRPO | 同题多回答 + 回答级奖励 | 组内标准化相对奖励 | token 级硬裁剪 | 不需要 | 用组内 baseline 取代 Critic |
| Dr.GRPO | 同 GRPO | 去 std，仅中心化 | token 级硬裁剪，固定尺度聚合 loss | 不需要 | 难度偏置与回答长度偏置 |
| DAPO | 同题动态采样 + 可验证奖励 | 组内相对奖励 | token 级非对称硬裁剪 | 不需要 | 探索、有效采样、长 CoT 与截断处理 |
| GSPO | 同题多回答 + 回答级奖励 | 组内相对奖励 | sequence 级硬裁剪 | 不需要 | 长序列和 MoE 训练稳定性 |
| SAPO | 同题多回答 + 回答级奖励 | 组内相对奖励 | token 级平滑软门控 | 不需要 | 保留有效 token 梯度并抑制离策略异常值 |

## 为什么会这样演进

这几种方法的演进可以压缩成四个问题：

1. **PPO 太重怎么办？** DPO 绕开在线 RL；GRPO 用组内比较去掉价值模型。
2. **GRPO 的归一化会不会改变样本权重？** Dr.GRPO 删除标准差和逐回答长度归一化。
3. **长 CoT 训练中采样、探索和截断怎么处理？** DAPO 给出一组面向大规模 RLVR 的训练配方。
4. **token 级重要性比率与回答级奖励不匹配，而且硬裁剪太生硬怎么办？** GSPO 改为序列级优化，SAPO 改为 token 级平滑门控。

因此，没有一种算法在所有场景中无条件胜出：

- 有高质量静态偏好对、追求简单稳定：优先考虑 DPO；
- 需要在线探索和细粒度 value estimation：PPO 仍有价值；
- 数学或代码 RLVR、资源有限：GRPO 家族更实用；
- 关注归一化偏置和 token 效率：Dr.GRPO；
- 长 CoT、大规模可验证奖励训练：DAPO；
- 长序列或 MoE，稳定性优先：GSPO；
- 希望平滑抑制异常 token 并保留更多有效信号：SAPO。

## 资料

- [Proximal Policy Optimization Algorithms](https://arxiv.org/abs/1707.06347)
- [Direct Preference Optimization](https://arxiv.org/abs/2305.18290)
- [DeepSeekMath：GRPO 的代表性来源](https://arxiv.org/abs/2402.03300)
- [Understanding R1-Zero-Like Training：Dr.GRPO](https://arxiv.org/abs/2503.20783)
- [DAPO](https://arxiv.org/abs/2503.14476)
- [GSPO](https://arxiv.org/abs/2507.18071)
- [SAPO](https://arxiv.org/abs/2511.20347)
