---
title: "大模型基础 02：从标准注意力到 Gated DeltaNet"
date: 2026-10-06 09:10:00 +0800
categories:
  - 大模型基础
tags:
  - 线性注意力
  - Gated DeltaNet
  - Gated Attention
  - KV Cache
excerpt: "推导线性注意力的递推状态，区分 Delta 更新与输出门控，并说明混合注意力、GQA、FlashAttention 各自在节省什么。"
pin: false
---

线性注意力中的“线性”，主要指计算量对序列长度的增长关系，不是说整个模型没有非线性。它的核心思路是：把历史信息积累到一个固定形状的状态里，避免每次生成都显式遍历全部历史键值。

系列导航：[01 Transformer 与 ViT](/notes/llm-foundations-01-transformer-vit/) → **02 线性注意力** → [03 多模态架构与训练](/notes/llm-foundations-03-multimodal-training/) → [04 Qwen 三代对比](/notes/llm-foundations-04-qwen-comparison/)。

## 1. 标准注意力的成本来自哪里？

对长度为 N 的序列，标准注意力需要计算 Query 与 Key 之间的两两关系。忽略头数并固定特征维度 d，注意力部分的计算量约为 `O(N²d)`。

```text
Attention(Q, K, V) = softmax(Q K^T / sqrt(d) + mask) V
```

要区分训练 / Prefill 和单步 Decode：

| 场景 | 全注意力的主要成本 | 缓存或内存 |
| --- | --- | --- |
| 训练 / Prefill | 为多个位置计算相互关系，注意力算术量随 N 平方增长 | 朴素实现会存 N × N 中间矩阵；优化内核可避免完整物化 |
| 单步 Decode | 新 Query 与 N 个历史 Key 匹配，约 O(Nd) | KV Cache 随历史长度增长 |
| 连续生成很多 token | 每一步都读取逐渐变长的历史 | 生成越长，累计成本越高 |

FlashAttention 改善的是内存访问和中间结果存储，在不改变标准注意力结果的前提下提高效率。它并没有把全注意力的算术复杂度从平方改成线性。[FlashAttention 论文](https://arxiv.org/abs/2205.14135)

## 2. 先看最简单的矩阵变换

如果暂时去掉 softmax，则矩阵乘法满足结合律：

```text
(Q K^T) V = Q (K^T V)
```

左边先生成 `N × N` 的矩阵；右边先生成与序列长度无关的特征维度矩阵。但标准 softmax 耦合了每一行的所有分数，不能直接把它搬到结合律外面。因此，“线性注意力就是标准注意力换个乘法顺序”并不准确。

一种经典路线用特征映射 phi 定义新的相似度核。设 q、k 映射后的维度为 r，v 的维度为 d_v，则因果注意力可以写成：

```text
S_t = S_(t-1) + phi(k_t) v_t^T     # r × d_v
z_t = z_(t-1) + phi(k_t)           # r 维

o_t = [phi(q_t)^T S_t]
      / [phi(q_t)^T z_t + epsilon]
```

S 保存历史键值关联的累积，z 用于归一化。更新和读取的成本由特征维度决定，不需要随历史长度增大。固定 r、d_v 时，处理整个序列对 N 呈线性增长。这是理解线性注意力的一条基础路线，并非所有现代线性模型都使用同样的归一化公式。[Linear Transformer 论文](https://arxiv.org/abs/2006.16236)

## 3. 固定状态意味着什么代价？

全注意力保留每个历史位置的 K、V，新 Query 可以直接访问这些位置。线性注意力则把历史关联压缩进固定状态，不再为每个位置保存一份独立键值。

比如依次读到“订单 A 的地址”“订单 B 的地址”“订单 A 的新地址”，模型不仅要记住关联，还要能覆盖旧值、保留无关信息，并在查询时区分相似 Key。简单累加会发生信息干扰；固定状态也不能无损保存任意多条独立信息。

因此，效率优势常伴随精确检索与状态容量的权衡。但“线性注意力不能推理”同样过度概括：表现取决于状态更新机制、模型规模、训练数据和任务，不能从复杂度公式直接推出能力结论。

## 4. DeltaNet：根据预测误差更新关联

换一种矩阵方向，令 S 的形状为 `d_v × d_k`，k、q 是列向量。一个简化的 Delta 更新为：

```text
v_pred = S_(t-1) k_t
error  = v_t - v_pred
S_t    = S_(t-1) + beta_t error k_t^T
o_t    = S_t q_t
```

直觉上，模型先用旧状态读取当前 Key 对应的 Value，再把“希望写入的值”和“已有读出值”的差额写回。beta 控制更新强度。它比单纯累加更有针对性，但由于 Key 之间不一定正交，也不能把它等同于无冲突的精确数据库。

这里的状态更新发生在前向计算中，是模型处理上下文的一部分；**它不是每读一个 token 就运行优化器修改模型权重**。

## 5. Gated DeltaNet：再加入遗忘门

Gated DeltaNet 将遗忘和定向更新结合。以下为单头、简化记号下的核心递推，省略投影、卷积、归一化等实现细节：

```text
S_bar = alpha_t S_(t-1)
S_t   = S_bar + beta_t (v_t - S_bar k_t) k_t^T
o_t   = S_t q_t
```

alpha 控制保留多少旧状态，beta 控制沿当前 Key 方向修正多少。注意，误差读取的是衰减后的 `S_bar`，不能随意把它改成未衰减的状态。

概念上可以分三步理解：先遗忘一部分旧信息，再检查当前关联还差多少，最后有针对性地修正。论文也提供适合 GPU 的分块并行训练算法；递推形式不代表训练必须逐 token 串行执行。[Gated DeltaNet 论文](https://arxiv.org/abs/2412.06464)及[官方实现](https://github.com/NVlabs/GatedDeltaNet)

## 6. Gated Attention 是另一个东西

Gated Attention 在标准 softmax 注意力输出后加入依赖输入的门控。简化形式是：

```text
U = softmax(Q K^T / sqrt(d) + mask) V
G = sigmoid(X W_g)
O = (U * G) W_o
```

其中 `*` 表示逐元素乘法，实际门的形状随实现而变。它可以对注意力读出的不同分量进行抑制，引入额外非线性，并改善部分实验中的训练稳定性和 Attention Sink。

Attention Sink 指某些位置，尤其早期 token，吸收了过多注意力权重的现象。门控能调节读出的信息，但不能把某一论文设置的比例下降当成所有模型的固定收益。[Gated Attention 论文](https://arxiv.org/abs/2505.06708)

| 对比项 | Gated DeltaNet | Gated Attention |
| --- | --- | --- |
| 核心机制 | 递推状态、衰减和 Delta 更新 | 标准注意力后增加门控 |
| 历史存储 | 固定形状状态 | 全注意力层仍保存历史 KV |
| 对序列长度的注意力成本 | 固定状态维度下线性 | 全序列注意力仍是平方量级 |
| 门的主要作用 | 调节记忆保留和关联写入 | 调节注意力输出 |

## 7. 为什么混合两种层？

Qwen3.5-397B-A17B 的语言主干采用 15 个重复块，每块包含 3 个 Gated DeltaNet 层和 1 个 Gated Attention 层，共 60 层。它希望用较多递推层控制成本，同时保留一部分直接访问历史位置的层。[官方模型卡](https://huggingface.co/Qwen/Qwen3.5-397B-A17B)

```text
[DeltaNet → FFN/MoE] × 3
         ↓
[Gated Full Attention → FFN/MoE]
         ↓
重复若干块
```

这个设计有两个容易漏掉的限制：

1. 仍有全注意力层，所以模型整体并没有消除长序列的平方注意力项。
2. 全注意力层仍需 KV Cache，所以“所有推理缓存都不随上下文增长”不成立。

## 8. 不要把几种“高效”混为一谈

| 技术 | 主要减少什么 | 没有自动解决什么 |
| --- | --- | --- |
| GQA | KV 头数、KV Cache 和相关带宽 | 不改变全注意力对序列长度的平方算术复杂度 |
| FlashAttention | 中间矩阵物化与显存读写 | 不取消全注意力两两交互 |
| 线性注意力 | 对历史长度的注意力计算增长及递推状态存储 | 不保证无损召回任意历史 |
| MoE | 每个 token 激活的 FFN 参数与计算 | 不等于只需存储激活的那些权重 |
| 视觉 token 压缩 | 进入 LLM 的序列长度 | 不保证保留全部细节 |

真实速度还取决于 batch、序列长度、内核、硬件和通信开销。复杂度更低不代表在每一种短输入、小 batch 场景下都更快。

下一篇：[多模态模型怎么连接、训练，以及损失如何传播](/notes/llm-foundations-03-multimodal-training/)。
