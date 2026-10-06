---
title: "大模型基础 01：Transformer、Encoder / Decoder 与 ViT"
date: 2026-10-06 09:00:00 +0800
categories:
  - 大模型基础
tags:
  - Transformer
  - Attention
  - ViT
  - 视觉编码器
excerpt: "从 Q、K、V 和因果掩码理解 Transformer，再沿着图像切块、视觉编码和训练目标，弄清 ViT 如何成为多模态大模型的视觉入口。"
pin: false
---

文本和图像看起来很不一样，但进入 Transformer 后，都可以表示为一串向量。理解这个共同接口，才能继续理解 LLaVA、Qwen-VL，以及为什么“原生多模态”仍然可以包含视觉编码器。

这组笔记整理了关于大模型架构、注意力、视觉训练和 Qwen 系列的讨论。阅读顺序：**01 Transformer 与 ViT** → [02 线性注意力](/notes/llm-foundations-02-linear-attention/) → [03 多模态架构与训练](/notes/llm-foundations-03-multimodal-training/) → [04 Qwen 三代对比](/notes/llm-foundations-04-qwen-comparison/)。

## 1. 先把模型的数据流串起来

典型的自回归语言模型可以写成：

```text
文本 → Tokenizer → token ID → Embedding
     → 多层 Transformer → 最后归一化 → LM Head
     → 词表上的 logits → 选择下一个 token
```

Tokenizer 决定文本如何拆成离散单元；Embedding 把 ID 查表转换成向量；Transformer 建模上下文；LM Head 把隐藏向量映射成词表上的分数。

设词表大小为 V，隐藏维度为 d，则输入 Embedding 矩阵通常具有 `V × d` 的形状。**词表大小和隐藏维度是两个独立概念。** 输出层可以与输入 Embedding 共享权重，也可以单独训练，具体取决于模型配置。

模型并不是在每一步重新“训练”。常规推理时权重固定，改变的是输入上下文、各层激活，以及用于复用历史计算的缓存。

## 2. Q、K、V 在做什么？

单头自注意力的简化公式如下。X 是当前层输入，W 是可训练投影矩阵，d_k 是单个 Key 的维度。

```text
Q = X W_Q
K = X W_K
V = X W_V

A = softmax(Q K^T / sqrt(d_k) + mask)
O = A V
```

Query 表示当前位置要查找什么；Key 表示每个位置提供什么匹配线索；Value 是匹配后实际汇聚的信息。它们是学习得到的向量，不是显式的自然语言标签。

例如在“杯子放在桌上，它是蓝色的”中，处理“它”时，注意力可以从前面的相关位置汇聚信息。不同的头使用不同投影，有机会学习不同关系，但不能保证每个头都有单一、清晰的人类语义。

多头注意力把各头输出拼接后通过输出投影。FFN 则对各位置的向量进行非线性变换。在一个标准块里，可以把二者粗略理解为：注意力负责位置之间的信息交换，FFN 负责每个位置内部的特征变换。[Transformer 原论文](https://arxiv.org/abs/1706.03762)

## 3. Encoder、Decoder 到底有什么区别？

| 结构 | 自注意力可见范围 | 是否有 Cross-Attention | 典型用途 |
| --- | --- | --- | --- |
| Transformer Encoder | 通常可以看完整输入，忽略 padding 等被屏蔽位置 | 标准结构没有 | 文本表示、图像编码 |
| 原始 Encoder–Decoder 的 Decoder | 输出侧使用因果掩码，只看当前及之前位置 | 有，读取 Encoder 输出 | 翻译、条件序列生成 |
| GPT / Qwen 类 Decoder-only 主干 | 通常使用因果自注意力 | 通常没有独立的编码器交叉注意力子层 | 自回归文本生成 |

原始 Transformer 的结构可以概括为：

```text
Encoder 层：Self-Attention → Add & Norm → FFN → Add & Norm

Decoder 层：Masked Self-Attention → Add & Norm
           → Cross-Attention → Add & Norm
           → FFN → Add & Norm
```

其中 Add 是残差连接。在 Cross-Attention 中，Q 来自 Decoder，K 和 V 来自 Encoder 输出。现代语言模型常采用 Pre-Norm，即先归一化再进入子层，并使用 RMSNorm、SwiGLU 等变体；不能把原论文的具体层顺序原封不动套到所有模型上。

“Decoder-only”也不意味着模型只能读取文字。只要模型经过相应训练，视觉向量也可以作为主干输入。**ViT + Decoder-only LLM 并不自动等于原始 Transformer 的 Encoder–Decoder 结构**：视觉 token 可以直接拼入 LLM 序列，不必通过独立的 Cross-Attention 子层传递。

## 4. 因果模型为什么能并行训练，却要逐步生成？

训练时完整的正确序列已经存在，可以把它右移，构成输入和监督目标：

```text
输入：<BOS>  今天  天气
目标：今天   天气  很好
```

因果掩码阻止每个位置看到未来 token，因此多个位置可以在同一次前向计算中同时预测各自的下一个 token。这就是常见的 teacher forcing。

推理时未来 token 尚未知，模型通常需要生成一个 token 后再继续。KV Cache 保存历史位置的 K、V，减少重复计算，但标准全注意力仍需读取越来越长的历史。投机解码可以批量提出候选并验证，并不取消自回归概率建模。

## 5. ViT：把图像变成向量序列

Vision Transformer 的基础路线是把图像切成 patch，再用 Transformer Encoder 建模 patch 之间的关系。

以 `224 × 224 × 3` 的 RGB 图像和 `16 × 16` 的 patch 为例：

```text
patch 数量：N = (224 / 16) × (224 / 16) = 196
每个 patch 展平：16 × 16 × 3 = 768 个像素通道值
线性投影：768 → d，得到 196 个 d 维向量
加入位置信息 → Transformer Encoder → 视觉表示
```

这里输入块的 768 维来自像素排列，隐藏维度 d 是模型选择；在某些配置中二者碰巧一样，不代表必须相同。Patch Embedding 也可以用卷积核大小和步长都等于 patch 大小的卷积实现。

原始分类 ViT 通常加入一个可学习的 `[CLS]` token，用其最终表示接分类头。多模态模型往往保留一组 patch 特征，以保存局部细节和空间关系，并不一定使用 `[CLS]` 作为全部图像的唯一表示。[ViT 原论文](https://arxiv.org/abs/2010.11929)

## 6. ViT 是怎样训练出来的？

ViT 是架构，训练目标并不唯一。下面三条路线可以训练出不同用途的视觉表示。

| 路线 | 输入与监督 | 典型损失 | 学习重点 |
| --- | --- | --- | --- |
| 有监督分类 | 图像和类别标签 | 类别交叉熵 | 区分预定义类别 |
| CLIP 式图文对比学习 | 成对的图片与描述 | 图像到文本、文本到图像的对比交叉熵 | 匹配图像语义与文本语义 |
| MAE 式掩码重建 | 遮住大量 patch，只输入可见部分 | 被遮住区域的重建误差 | 从可见结构推断缺失内容 |

分类训练流程是：图像预处理与增强 → 切块和编码 → 分类头 → 计算交叉熵 → 反向传播 → 更新参数。之后可以更换分类头，迁移到下游数据集。

CLIP 同时包含图像编码器和文本编码器。对一个包含 B 对图文的 batch，计算 `B × B` 相似度矩阵，提高配对图文的相似度，并相对降低不配对项的相似度。**CLIP 的文本编码器不是 LLaVA 中负责生成答案的 LLM。** LLaVA 可以取用 CLIP 的视觉部分，再连接另一个生成式语言模型。[CLIP 论文](https://arxiv.org/abs/2103.00020)

MAE 的 Encoder 只处理可见 patch，较轻的 Decoder 再尝试重建被遮住的像素块。这个重建 Decoder 和聊天 LLM 不是同一个概念；预训练后也可以丢弃重建头，只保留视觉 Encoder。[MAE 论文](https://arxiv.org/abs/2111.06377)

## 7. 从 ViT 到多模态 LLM，还差什么？

视觉编码器产生的向量，与 LLM 的输入表示即使维度相同，语义分布也未必兼容。因此需要连接模块及相应训练。

```text
图像 → ViT → patch 特征 → Projector / Merger ─┐
                                            ├→ LLM → 文本答案
文本 → Tokenizer → Embedding ────────────────┘
```

Projector 主要完成特征映射。Merger 还可以将相邻视觉 token 合并，以缩短序列。比如将一个 `2 × 2` 的局部区域合成一个 token，会让该区域对应的 token 数量减少到四分之一；压缩也可能损失细节，需要结合分辨率和训练任务设计。

“图像变成 token”不一定是把图像离散成词表 ID。许多理解型 VL 模型直接使用连续视觉向量；输入中的特殊图像标记用于组织序列，不等于每个 patch 都是一个普通文字词表项。

下一篇：[线性注意力为什么更省，以及它牺牲了什么](/notes/llm-foundations-02-linear-attention/)。
