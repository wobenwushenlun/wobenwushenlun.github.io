---
title: "音乐生成大模型：从文本生成到可编辑的歌曲工作流"
date: 2026-10-06 13:40:00 +0800
categories:
  - 音乐生成
tags:
  - MusicLM
  - MusicGen
  - YuE
  - SongGen
  - ACE-Step
  - Flow Matching
  - 数据与训练
excerpt: "从应用、数据和音频表示出发，梳理自回归、扩散、Flow Matching 与混合架构的路线，解释完整歌曲、歌词对齐、可编辑性和实时音乐为什么仍然难。"
pin: false
---

音乐生成大模型已经从“根据一句话生成几秒钟的旋律”，走到了“生成完整歌曲、分离 stem、局部重绘、续写和风格迁移”。但把一段声音做得像音乐，只是问题的一半；真正困难的是让它在几分钟内保持曲式、和声、节奏、人声身份和歌词对齐，同时还要允许创作者修改其中一个局部。

这篇笔记把目前的技术路线放到同一张图里。资料核对日期：**2026-10-06**。商业产品的训练数据和模型细节通常没有完全公开，下面会把论文、开源项目和产品已经明确披露的内容分开说。

## 1. 先把“音乐生成”拆成几类任务

“Text-to-Music”不是一个单一任务。输入和输出不同，模型需要学到的能力也不同。

| 任务 | 输入 | 输出 | 关键难点 |
| --- | --- | --- | --- |
| 文本到音乐 | 曲风、乐器、情绪、场景描述 | 纯音乐或短片段 | 文本遵循度、音质、风格覆盖 |
| 旋律到音乐 | 哼唱、MIDI、参考旋律 | 保留旋律、改变配器和风格 | 旋律保持与伴奏重编 |
| 歌词到歌曲 | 歌词、曲风、演唱情绪 | 人声、伴奏和混音 | 音素—音高—时长对齐 |
| 音频续写 | 一段已有音频 | 前后延长或补全 | 边界衔接、调性和节奏连续 |
| 局部编辑 | 原曲、时间区间、文字指令 | 只修改选中部分 | 保留上下文、避免其它轨道漂移 |
| 分轨与重混 | 完整歌曲或 stem | 人声、鼓、贝斯等独立轨道 | 分离质量与重新生成的一致性 |
| 视频到音乐 | 视频、镜头节奏、情绪 | 与时间轴同步的配乐 | 事件对齐、段落转折和时长约束 |
| 实时生成 | 演奏、和弦、动作或控制信号 | 连续输出音乐 | 延迟、可预测性和实时稳定性 |

因此，评价一个模型时，不能只问“听起来像不像音乐”。一首 30 秒的氛围音乐和一首 4 分钟、歌词清楚、段落完整的歌曲，实际上是两个难度不同的系统。

## 2. 应用已经从生成走向制作工作流

目前产品形态大致有三层。

第一层是**灵感生成**：输入“电影感的弦乐、雨夜、缓慢的钢琴”或一段哼唱，快速得到多个草稿。它适合广告、短视频、播客和游戏原型，也适合音乐人验证一个想法是否值得继续制作。

第二层是**歌曲生产**：输入歌词、曲风和演唱情绪，直接生成主歌、副歌、伴奏和人声。Suno 的 Extend、Cover、Persona 和分轨工具，已经把生成结果放进了一个连续的创作流程；Udio 支持上传音频后 remix、stylize 和 extend。[Suno 产品页](https://suno.com/products)、[Udio 音频创作说明](https://help.udio.com/en/articles/10754328-create-music-with-your-own-audio)

第三层是**可控制作**：用户指定某一段的歌词、和弦、乐器和人声，要求模型只重做这一部分；或者把一首歌拆成 stem，再单独替换鼓组、贝斯或主唱。这类能力对专业制作比“一次生成一首完整歌曲”更有价值，因为真实创作很少是生成一次就交付。

Google 的 Lyria 系列则把方向推进到视频配乐、Gemini 内的音乐生成和实时交互。[Google DeepMind Lyria](https://deepmind.google/models/lyria/)

## 3. 数据：规模很重要，但配对质量更重要

音乐模型的训练数据可以分成四层：

1. **音频层**：完整歌曲、片段、loop、纯音乐、人声、伴奏、单乐器和多轨 stem。
2. **语义层**：标题、曲风、情绪、乐器、BPM、调性、时代和场景描述。
3. **结构层**：拍点、和弦、旋律、段落边界、歌词、音素和词级时间戳。
4. **反馈层**：用户选择、A/B 偏好、音质评分、歌词可懂度、提示词遵循度和编辑成功率。

公开数据能帮助研究者验证方法，但很难直接支撑商业级完整歌曲生成：

| 数据集或数据来源 | 主要用途 | 需要注意的边界 |
| --- | --- | --- |
| MusicCaps | 约 5,500 条人工音乐描述，适合文本—音乐对齐和评测 | 规模小，片段短，不能代表完整歌曲训练 |
| FMA | 约 10.6 万首 Creative Commons 音乐，含流派元数据 | 授权条件不完全相同，需要逐条遵守许可证 |
| AudioSet | 大规模带标签的音频片段 | 音乐片段短，下载和再分发受限制 |
| Music4All / MTG-Jamendo | 音频、标签、检索和音乐理解 | 更适合 MIR、标签和表示学习 |
| AudioSparx | 商业授权音乐、音效和单乐器数据 | 授权范围由具体合作和产品条款决定 |
| 歌曲专用数据 | 歌词、人声、伴奏、段落和时间戳 | 数据稀缺、标注昂贵、版权风险最高 |

MusicLM 发布了 MusicCaps；MusicGen 论文披露其使用约 2 万小时授权音乐，并配有文本描述、曲风、BPM 和标签。[MusicLM](https://research.google/pubs/musiclm-generating-music-from-text/)、[MusicGen](https://proceedings.nips.cc/paper_files/paper/2023/file/94b472a1842cd7c56dcb125fb2765fbd-Paper-Conference.pdf)

高质量数据管线通常包括：

```text
音频采集
→ 版权与许可证记录
→ 去重、音质和响度筛选
→ 人声/伴奏/多轨分离
→ ASR 歌词转录
→ 音素、拍点、BPM、调性和段落对齐
→ 自动 caption 与人工抽检
→ 按歌曲、艺人和专辑切分训练/验证/测试
```

这里最容易被低估的是**数据切分**。如果同一首歌的不同片段同时出现在训练和测试中，模型可能只是记住了录音的音色或旋律，评测结果会明显偏高。完整歌曲模型还要检查歌词重复、艺人泄漏、旋律近似和生成结果与训练集的相似度。

训练数据的版权路线也会直接影响产品能否商业化。Stable Audio 2.0 宣称使用 AudioSparx 的授权数据，并支持艺人退出训练；Stable Audio 3 继续强调授权和 Creative Commons 数据。[Stable Audio 2.0](https://stability.ai/news/stable-audio-2-0)、[Stable Audio 3 模型说明](https://huggingface.co/stabilityai/stable-audio-3-small-music-base)

## 4. 音频怎么变成模型能处理的 token

原始波形采样率通常是 16 kHz、24 kHz、32 kHz 或 44.1/48 kHz。直接对波形做语言模型式的 next-token prediction，序列太长，所以模型通常先经过音频压缩器。

目前有三种主要表示：

### 4.1 MIDI 和符号表示

音符、和弦、力度、节奏和段落结构清楚，适合编曲控制和音乐理论分析；但它不包含真实歌声、音色、混音、呼吸和演奏细节。

### 4.2 离散 codec token

EnCodec、SoundStream 或专门的音乐 codec 把波形量化成多个 codebook。模型像语言模型一样预测这些离散 token。MusicGen 就使用 32 kHz EnCodec，并通过多码本模式生成音乐。[MusicGen 技术说明](https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md)

优点是可以复用 Transformer 的语言建模方法；缺点是高保真音频需要较高 token 率，完整歌曲会变成长序列，推理速度和误差累积都成为问题。

### 4.3 连续 latent

VAE、DCAE 等编码器把波形压到连续空间，扩散模型或 Flow Matching 模型直接在 latent 中生成，再由 decoder 还原音频。这种表示更适合并行生成和局部编辑，但需要额外处理长期结构和歌词的精确对齐。

一个明显趋势是**降低帧率，同时提高每个 token 的信息量**。HeartCodec 采用约 12.5 Hz 的低帧率音乐 codec，目标是同时保留长期音乐结构和高频声学细节。[HeartMuLa](https://arxiv.org/abs/2601.10547)

可以把未来的表示理解为三层：

```text
低频结构 token：曲式、和弦、旋律走向
中频表达 token：歌词节奏、人声表达、乐器进入/退出
高频声学 latent：音色、瞬态、混响和混音细节
```

## 5. 模型路线：自回归、扩散和混合架构

### 5.1 自回归音乐语言模型

自回归模型把音频 token 排成序列，逐步预测下一个 token。MusicGen 是代表性的单阶段 Transformer；YuE 基于 LLaMA2，专门面向长时歌词到歌曲；SongGen 则尝试在单个自回归模型中统一歌词、曲风、人声参考和混合/双轨输出。[MusicGen](https://arxiv.org/abs/2306.05284)、[YuE](https://arxiv.org/abs/2503.08638)、[SongGen](https://arxiv.org/abs/2502.13128)

它的优势是：

- 顺序结构自然，适合歌词和段落规划；
- 可以利用语言模型的上下文、指令和 in-context learning 能力；
- 通过条件 token 可以统一文本、歌词、参考音频和音乐属性。

主要问题是序列太长、推理慢、错误会累积，而且低码率 token 可能牺牲音质。长歌曲还需要解决“模型知道前面发生了什么，但不代表它能持续保持主题”的问题。

### 5.2 扩散和 Flow Matching

扩散模型从噪声逐步还原目标 latent；Flow Matching 则学习从简单分布到数据分布的连续速度场。它们可以并行处理一段音频，因此更适合高保真、快速生成和 inpainting。

MusicFlow 研究了级联 Flow Matching；Stable Audio 使用 latent diffusion；DiffRhythm 和类似方法则尝试把完整歌曲直接放进低维空间生成。[MusicFlow](https://proceedings.mlr.press/v235/prajwal24a.html)

它们的优势是局部音质好、采样可加速、编辑自然；问题是全局曲式、逐字歌词对齐和段落记忆不如自回归方法直接。

### 5.3 混合模型是目前最现实的折中

现在越来越多系统让不同模块分工：

```text
文本/歌词/参考音频
        ↓
LLM 或 Transformer：曲式、歌词、和弦、乐器和情绪规划
        ↓
低帧率 codec 或语义 latent：生成音乐草图
        ↓
DiT / Flow Matching：补全细节和高频声学质量
        ↓
VAE / codec decoder：输出 44.1/48 kHz 音频
```

InspireMusic 将自回归 Transformer 与超分辨率 Flow Matching 结合，目标是生成较长、高保真的音乐；SongBloom 交替进行自回归草图生成和扩散细化；ACE-Step 1.5 让语言模型规划歌曲蓝图，再由 DiT 渲染音频。[InspireMusic](https://arxiv.org/abs/2503.00084)、[SongBloom](https://arxiv.org/abs/2506.07634)、[ACE-Step 1.5](https://arxiv.org/abs/2602.00744)

这个范式的核心不是“把两个模型串起来”这么简单，而是要定义一个稳定的中间表示：规划器输出的曲式、歌词时长、和弦和乐器信息，必须真的能够约束渲染器。

## 6. 一套完整的训练配方

一个面向歌曲生成的训练系统，通常分成以下阶段。

### 阶段一：训练或选择 audio codec

先让 codec 在目标采样率和音乐数据上实现高质量重建。需要同时观察波形误差、频谱保真、瞬态、立体声空间和人声清晰度。codec 如果丢失齿音、呼吸和鼓的瞬态，后面的生成模型很难补回来。

### 阶段二：无条件或弱条件预训练

用大量音频学习节奏、和声、音色和音乐统计规律。这个阶段不一定需要精细 caption，但必须进行音质筛选、重复检测、版权记录和分布控制。

### 阶段三：文本—音频和属性对齐

加入曲风、乐器、情绪、BPM、调性、段落等条件。caption 可以由人工、元数据和多模态模型共同产生，但需要抽样人工核验，否则模型会学到过于笼统或错误的描述。

### 阶段四：歌词、人声和轨道专项训练

重点学习：

- 音素与音频帧的时间关系；
- 音节、音高和持续时间的关系；
- 歌词内容与旋律走向的关系；
- 人声、伴奏和混音之间的关系；
- 主歌、副歌和桥段的结构变化。

这一阶段最好有词级或音素级时间戳，不能只把整首歌词拼在音频前面作为文本条件。

### 阶段五：多任务和指令微调

把 text-to-music、lyrics-to-song、continuation、inpainting、cover、vocal-to-accompaniment 和 stem editing 放进统一任务格式。这样模型学到的不是“只会从零生成”，而是“根据一个创作请求修改已有音乐”。

### 阶段六：偏好优化和推理加速

最后可以用人工偏好、音乐质量模型、文本遵循度、歌词清晰度和编辑成功率进行 DPO、奖励优化或其它后训练；再通过少步 Flow Matching、蒸馏、量化和 adversarial post-training 降低推理成本。

JAM 已经探索把 Direct Preference Optimization 用于歌曲的音乐属性和音质对齐。[JAM](https://arxiv.org/abs/2507.20880)

## 7. 评测：一首歌“好”在哪里

音乐生成不适合只用一个分数排名。至少要分成五类指标：

| 维度 | 关注的问题 | 例子 |
| --- | --- | --- |
| 声学质量 | 是否有噪声、失真、伪影和不自然的混音 | FAD、频谱和人工音质评分 |
| 条件遵循 | 是否真的生成了指定的曲风、乐器、情绪和歌词 | CLAP 相似度、人工 prompt adherence |
| 音乐性 | 旋律、和声、节奏、调性和段落是否合理 | 音高、和弦、节拍和结构分析 |
| 歌曲一致性 | 几分钟内人声、主题、调性和配器是否保持 | 长时一致性、段落衔接评分 |
| 可用性 | 是否易于编辑、导出、重混和进入制作流程 | 编辑成功率、延迟、显存、用户偏好 |

歌词到歌曲还应单独评测：歌词识别准确率、音素—歌声对齐误差、发音可懂度、旋律与词义的适配，以及不同语言的表现。评测综述指出，音乐生成需要结合客观指标、人工听评、音乐学分析和真实创作体验，单一的 CLAP 或 FAD 都不能代表最终质量。[音乐生成评测综述](https://arxiv.org/abs/2506.05104)

## 8. 当前最值得关注的前沿路线

### 8.1 从“生成片段”到“生成曲式”

模型需要知道 intro、verse、pre-chorus、chorus、bridge 和 outro 的关系，而不只是延长局部纹理。层次化规划、段落记忆、显式和弦/旋律表示和结构条件会继续变重要。

### 8.2 从一次性生成到可逆编辑

未来产品的核心交互可能是：选中 0:42–0:58，输入“保留歌词和鼓，把吉他换成木管”，然后得到几种候选。为此需要稳定的 latent inversion、时间区间条件、stem 约束和跨版本一致性。

### 8.3 从文本 prompt 到音乐控制协议

自然语言适合表达风格，但不适合精确表达和弦、音高、节拍和时间轴。MIDI、humming、和弦进行、鼓点网格、音高曲线、演唱情绪和视频事件会成为更可靠的控制接口。

### 8.4 实时和交互式生成

实时音乐模型的关键指标不是离线样本的最高音质，而是延迟、稳定性和用户能否预测下一小节。模型需要处理实时演奏、和弦、动作和反馈，可能还要支持“生成—试听—修改—继续”的循环。

### 8.5 多语言歌声与文化覆盖

中文、日文、韩文和阿拉伯语等语言在音节、声调、重音和歌唱发音上不同。真正的多语言歌曲模型要联合学习文字、音素、声调、旋律和演唱方式，而不是只把 prompt 翻译成英语。

### 8.6 版权、声音身份和可归因生成

数据授权、艺人同意、声音克隆、训练集泄漏、输出相似度和内容溯源，会越来越直接地影响模型能否上线。对企业来说，“质量略高但来源不清”的模型，可能不如质量稍低、授权和输出权清晰的模型。

## 9. 如果自己做一个研究原型

不建议一开始就训练“完整歌曲大模型”。更可行的路线是逐层验证：

1. 用 FMA、MusicCaps 或授权数据训练一个 10–30 秒 text-to-music baseline。
2. 先固定成熟 codec，比较自回归 token 模型和 latent diffusion/flow 模型。
3. 加入 BPM、调性、和弦或 humming 条件，验证控制是否真的生效。
4. 建立歌词 ASR、音素对齐和人声/伴奏分离管线。
5. 先做局部 inpainting 或 continuation，再做完整歌曲。
6. 用人工听评、歌词对齐、结构一致性和推理成本建立自己的评测集。
7. 最后再考虑 LLM 规划器、偏好优化和 LoRA 个性化。

一个值得复现的最小系统可以是：

```text
文本/歌词
  → LLM 生成结构化歌曲计划
  → 低帧率 codec token 或 latent 生成器
  → 局部扩散细化
  → 人声/伴奏分轨与简单混音
  → 结构、对齐和音质评测
```

我对这个方向的判断是：短期的突破点不只是把模型从 3B 扩到更大，而是改善**授权数据、音乐结构表示、歌词对齐、可编辑接口和人机协作流程**。真正有用的音乐模型，最终应该更像一个可以反复修改的制作伙伴，而不是只能点击一次的歌曲生成器。

## 资料入口

- [MusicLM: Generating Music From Text](https://research.google/pubs/musiclm-generating-music-from-text/)
- [MusicGen: Simple and Controllable Music Generation](https://arxiv.org/abs/2306.05284)
- [Stable Audio Open](https://arxiv.org/abs/2407.14358)
- [YuE: Scaling Open Foundation Models for Long-Form Music Generation](https://arxiv.org/abs/2503.08638)
- [SongGen: A Single Stage Auto-regressive Transformer for Text-to-Song Generation](https://arxiv.org/abs/2502.13128)
- [InspireMusic](https://arxiv.org/abs/2503.00084)
- [SongBloom](https://arxiv.org/abs/2506.07634)
- [ACE-Step](https://arxiv.org/abs/2506.00045)
- [ACE-Step 1.5](https://arxiv.org/abs/2602.00744)
- [HeartMuLa](https://arxiv.org/abs/2601.10547)
- [Auto-Regressive vs Flow-Matching](https://arxiv.org/abs/2506.08570)
- [Survey on the Evaluation of Generative Models in Music](https://arxiv.org/abs/2506.05104)
