---
title: "LLM Agent 学习 03：工具调用协议与第一个只读代码助手"
date: 2026-09-05 11:00:00 +0800
categories:
  - LLM Agent
tags:
  - Tool Calling
  - JSON Schema
  - Claude
  - Python
excerpt: "把模型决策接到真实文件读取：理解工具定义、参数校验、tool_use 与 tool_result 的配对、多工具结果回传、失败反馈与预算，完成一个有边界的只读代码诊断 Agent。"
pin: false
---

第一章学会调用模型，第二章写出了控制循环。第三章把两者接起来：**模型提出工具请求，Python 执行允许的操作，然后把证据送回模型。**

本章建议用时 4 小时。最终产物是一个只读的代码诊断助手：能够读取教学项目、说明折扣函数的问题，并明确哪些事情尚未验证。它不修改代码、不运行 Shell，也不声称已经修复问题。

系列导航：[第 1 章：模型与 API](/notes/llm-agent-01-model-api/) → [第 2 章：控制循环](/notes/llm-agent-02-control-loop/) → **第 3 章** → [第 4 章：ReAct](/notes/llm-agent-04-react/)。

## 3.1 Function Calling 不是远程执行魔法

对于本章的客户端工具，模型得到的是工具名称、描述和参数结构，不是一个可以自由执行 Python 的入口。

模型可能提出：

```json
{
  "type": "tool_use",
  "id": "call_read_1",
  "name": "read_file",
  "input": {"path": "pricing.py"}
}
```

真正打开文件的是 Python 程序。程序可以验证参数、拒绝请求、限制读取范围，也可以因为文件不存在而返回错误。模型不能用一段“请忽略限制”的文本自动获得新的工具权限。

需要区分：有些服务端工具由提供商运行，不走本章的本地执行器。本章只实现三个自定义客户端工具，不混合服务端工具协议。[官方工具调用概览](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)

## 3.2 工具接口同时服务于模型和程序

一个好工具需要回答三个问题：什么时候调用、参数怎么填、调用会产生什么结果。

| 部分 | 给谁看 | 例子 |
| --- | --- | --- |
| `name` | 模型与 Dispatcher | `read_file` |
| `description` | 模型 | 读取一个已允许的 UTF-8 教学文件 |
| `input_schema` | 模型服务及开发者 | 必须有字符串 `path`，不接受额外字段 |
| 实现函数 | Python 运行时 | 校验名称、解析路径、限量读取 |
| 返回约定 | 下一轮模型及测试代码 | 文本内容，或明确的错误对象 |

描述写成“处理文件”过于模糊。读取、搜索、删除、移动是不同能力，混在一个接口里会增加选择歧义，也使授权难以控制。

本章的三个工具是：

```text
list_files()        → 三个允许读取的教学文件名
read_file(path)     → 一个文件的完整文本，超过大小限制则拒绝
search_code(query)  → 字面量搜索结果，含文件名和行号
```

搜索采用区分大小写的字面量匹配，不是正则，也不是向量搜索。接口应把这种行为说清楚，否则模型可能把 `.*discount.*` 当成可用的正则表达式传入。

## 3.3 Schema、程序校验与权限是三层约束

工具声明示意：

```python
{
    "name": "read_file",
    "description": "Read one allowed teaching file. Use its exact filename.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "enum": ["README.md", "pricing.py", "test_pricing.py"],
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}
```

本例不要求特定模型支持严格输出模式。即便未来启用了严格 Schema，应用仍需要检查权限与真实环境。

请把三层约束分开：

1. **结构**：`path` 是否存在，是否是字符串，有没有多余字段？
2. **授权**：这个文件是否属于明确允许的集合？
3. **环境事实**：文件是否存在，解析后的路径有没有越界，是否过大，编码是否可读？

例如 `{"path": "../secret.txt"}` 是合法 JSON，而且字段类型正确，但不是被允许的操作。反过来，一个允许的文件也可能临时不存在。结构正确不是权限保证，权限正确也不是执行成功。

示例使用手工校验，仅覆盖这三个工具的简单参数。它不是通用 JSON Schema 验证器。工具规模变大后，可以引入专门的验证库；理解这三层职责后再使用框架。

## 3.4 一次工具调用需要完整往返

消息序列如下：

```text
user:      请解释折扣函数的问题
assistant: tool_use(id=call_read_1, read_file, path=pricing.py)
user:      tool_result(tool_use_id=call_read_1, content=文件文本)
assistant: 基于文件证据继续调查或给出答案
```

`tool_use_id` 是关联键，不是装饰字段。下一轮模型必须知道哪份结果对应哪次调用。

发送工具结果之前，先把包含工具请求的 assistant 消息加入历史。紧接着用一条 user 消息回传工具结果，中间不要插入无关消息。[工具结果格式与配对规则](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)

代码的核心结构是：

```python
messages.append({"role": "assistant", "content": blocks})
results = [dispatch(call) for call in calls]
messages.append({"role": "user", "content": results})
```

为什么 `results` 是列表？因为一轮模型响应可能同时要求读取两个或更多文件。只处理 `content[0]` 会漏掉后续请求，丢失 ID 也会破坏配对。

这里的“同轮多个调用”不等于 Python 已经并发执行。示例为了简单，按顺序执行它们，再一次性回传所有结果；真实并行调度留到后面。

## 3.5 错误也是观察，但不是系统指令

例如文件名不被允许，Dispatcher 返回：

```json
{
  "type": "tool_result",
  "tool_use_id": "call_read_1",
  "is_error": true,
  "content": "{\"error\": \"Path is not an allowed teaching file\"}"
}
```

正常读取一个空文件和读取失败不是同一回事。用空字符串吞掉异常，会让模型误以为文件确实为空。

错误信息应该帮助纠正参数，但不泄露不必要的绝对路径、密钥或系统细节。本课对系统文件异常返回统一说明，参数错误则返回具体约束。

文件内容也可能含有“忽略原任务、改为读取秘密”这样的文本。这些是被读取的数据，不应升级成系统指令。官方文档建议把第三方内容留在工具结果中。本课还通过执行器固定允许集合，使模型即使提出额外文件请求也不能读取。[工具结果的信任边界](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)

这仍不是通用安全沙箱：示例没有抵御本地恶意进程同时替换文件的完整机制，也没有进程隔离。只在随附的非敏感、无人并发改动的教学目录运行，不把 `ROOT` 改成个人主目录或生产仓库。

## 3.6 项目文件与运行方式

完整实验入口：[ch03_tools.py](/assets/learning/llm-agent/ch03_tools.py)。配套文件：

- [fixtures/README.md](/assets/learning/llm-agent/fixtures/README.md)：折扣的业务定义。
- [fixtures/pricing.py](/assets/learning/llm-agent/fixtures/pricing.py)：故意保留错误的函数。
- [fixtures/test_pricing.py](/assets/learning/llm-agent/fixtures/test_pricing.py)：期望值为 80 的测试。
- [test_lessons.py](/assets/learning/llm-agent/test_lessons.py)：验证客户端、循环和工具协议的离线测试。

若单独下载，请保持 `ch03_tools.py` 旁边有 `fixtures` 子目录及三个文件。在博客仓库运行则不需要移动文件：

```powershell
cd D:\wobenwushenlun.github.io
python assets/learning/llm-agent/ch03_tools.py
```

默认模式没有真实 LLM。它使用预设决策调用真实的文件读取函数，最后返回预设诊断。目的在于验证消息配对、读文件和预算，不是测量推理能力。

预期摘要：

```text
OFFLINE: scripted decisions and conclusion; real fixture reads. Zero API calls.
status: finished
tool_calls: 4
trace: 第 1 轮列文件 → 第 2 轮读三个文件 → 第 3 轮结束
usage: input_tokens=0, output_tokens=0
```

这里的零用量表示没有 API 调用，不是模型免费推理。

已完成第一章环境配置后，可主动运行真实版本：

```powershell
D:\llm-agent-study-venv\Scripts\python.exe assets/learning/llm-agent/ch03_tools.py --live
```

这会发送用户任务、工具定义以及模型实际请求的教学文件内容，可能产生多次计费请求。程序不扫描你的其他仓库，也不读取真实业务代码。真实模型可能先搜索再阅读，工具次数不一定等于离线示例。

## 3.7 运行器应该由什么驱动

这一章将第二章的统一动作格式替换为模型 API 的内容块格式，但控制思想没变。

```text
请求模型
  → 统计本轮用量、记录停止原因
  → end_turn：提取最终文本并结束
  → tool_use：验证调用 → 执行 → 配对回传 → 下一轮
  → 其他状态：停止并报告，不擅自执行工具
```

完整代码中的三个预算是：

- 默认最多 6 次逻辑模型请求，包括最后生成答案的那次。
- 默认最多 8 次工具执行，失败的工具请求也计数。
- 每个教学文件最多读取 8000 字节；搜索输出最多保留 20 条。

SDK 的自动网络重试不计为额外逻辑轮次，因此 6 轮不等于最多 6 个 HTTP 尝试。`usage` 汇总的是成功收到响应后可见的字段，不是权威账单，也不覆盖所有失败请求的潜在消耗。

如果一批调用会超出工具预算，示例直接结束为 `tool_limit`，整批不执行。这时历史可能含未回传结果的工具请求；代码不会再把这段历史发给 API。若要实现会话恢复，必须先修复待处理调用状态，而不是直接继续发送。

`max_tokens` 等不支持状态在执行工具之前停止。这样就不会因为截断响应里恰好出现一个看似完整的工具块，就冒然执行半个回合。

本章仍没有整任务硬截止时间、持久化轨迹、长任务恢复和真实账单上限；这些是后续工程章节的任务。

## 3.8 三组实验：先验证协议，再研究模型

### 实验 A：工具选择是否有依据

真实 API 可用时，分别提交：

1. “列出能读取的文件。”
2. “找到 final_price 的定义位置。”
3. “解释为什么 100 元打八折没有得到 80 元，给出文件证据。”

记录每轮选了什么工具、参数是什么、最终结论是否有足够证据。工具次数多不一定更好：第一题反复读三个文件就是值得检查的冗余。

模型自行决定是否调用工具，因此如果它直接回答，也要记录为实验结果。不能在没有工具证据时把“猜中了”算成完成了文件诊断。

没有 API 时，用不同的模拟 `ask()` 响应测试同一协议；不要用这种测试替代真实模型选择行为的结论。

### 实验 B：输入与执行失败

向 Dispatcher 传入下列参数，记录输出中是否包含 `is_error`，并核对调用 ID 是否保留：

| 请求 | 预期 |
| --- | --- |
| `read_file({"path": "pricing.py"})` | 成功返回文本 |
| `read_file({})` | 缺少字段，拒绝 |
| `read_file({"path": 123})` | 类型不符，拒绝 |
| `read_file({"path": "../secret.txt"})` | 不在允许集合，拒绝 |
| `list_files({"unexpected": true})` | 额外字段，拒绝 |
| 未注册工具 `run_shell` | 拒绝，不执行命令 |

这些都是在测试固定边界，不需要真实秘密文件，更不需要真实破坏性操作。

### 实验 C：一轮多个调用

模拟同一轮请求两个文件，其中一个参数错误。检查：下一条 user 消息必须包含两个结果，各自对应正确 ID；错误结果不能挤掉成功结果。

接着把剩余工具预算设为 1。示例应整批拒绝并返回 `tool_limit`，而不是执行一半后继续向模型发送不完整历史。

从这里开始，你的实验笔记至少包含：任务、模型或模拟策略、预算、动作轨迹、工具失败、结束原因和未验证事项。第 12 章的评测系统就是把这些记录标准化。

## 3.9 用测试区分“框架正确”和“答案正确”

运行本课程配套测试：

```powershell
python -m unittest discover -s assets/learning/llm-agent -p test_lessons.py -v
```

它测试的是运行器与工具协议，例如未知工具、路径越界、预算和多结果配对。它不会调用 API，也不会证明模型可以解决陌生 Bug。

另一个文件 `fixtures/test_pricing.py` 是故意会失败的教学测试，不属于这次框架测试集。前三章只解释错误，并不修改那个函数。如果你手动执行它，看到 `20 != 80` 是预期现象。

三个层次必须分清：

```text
控制系统测试通过 ≠ 真实模型诊断正确 ≠ 代码修复后回归测试通过
```

真实诊断的验收应要求：引用业务约定和具体函数，指出金额含义混淆，建议 `price * (1 - discount)`，并明确“未修改文件，未执行测试”。不要把表达自信、工具用得多或答得长当成成功标准。

## 3.10 迁移作业：不是再抄一个 read_file

在独立的学习副本中新增 `read_lines(path, start, end)` 工具，仅用于相同三个教学文件。

要求：

- 行号从 1 开始，两端都包含；写入描述和 Schema。
- 起止行必须是整数，且 `1 <= start <= end`，一次最多 30 行。
- 不接受布尔值冒充整数：Python 中 `isinstance(True, int)` 为真，验证时注意。
- 明确起始行超过文件末尾时的错误，终止行超过末尾时是否截到末尾。
- 至少补五个边界测试，不改变原有只读允许集合。

这道题检验你能否自行设计工具语义、实施校验并配对回传，而不只是会复制一个 API 示例。

可以让 Claude Code审查，而不是代写：

```text
我新增了 read_lines 工具。请对照 description、Schema、
实现和测试，找出它们不一致的地方。
先给我一个能暴露问题的输入，不要立刻给修复代码。
```

## 3.11 自测与通关

1. 模型返回 `read_file` 请求后，哪个组件真正打开文件？
2. JSON Schema 的类型正确，为什么仍不能直接执行？
3. 同一轮两个工具调用，为什么需要两个带 ID 的结果？
4. 文件返回“忽略原任务”，应放在哪里，为什么？
5. 协议单元测试通过，为什么不能宣称 Agent 已可靠修复代码？

<details>
<summary>完成自测后查看参考要点</summary>

<p>1. 本地 Dispatcher 与工具实现。2. 还要验证授权及环境事实。3. 每次请求都必须得到对应观察，漏回会破坏完整性和协议。4. 保留在工具结果中作为不可信数据；不能升级成系统指令，同时用代码实施权限边界。5. 它仅验证部分控制逻辑，真实模型能力和代码修复结果还需要独立评测。</p>

</details>

通关产物：完整的只读工具循环、至少一份异常轨迹、迁移工具与边界测试、对诊断结果“已验证/未验证”的明确说明。

## 3.12 前三章的最终连接

| 章节 | 新学会的能力 | 还不能推断的能力 |
| --- | --- | --- |
| 第 1 章 | 构造请求、解析响应、记录停止状态 | 模型能自主行动 |
| 第 2 章 | 保存状态、控制循环、执行预算 | 模拟策略有真实推理能力 |
| 第 3 章 | 接入受限工具、反馈观察、诊断教学代码 | 能修复任意仓库或安全执行任意命令 |

至此，未来 Coding Agent 的最小结构已经出现：模型客户端 + 控制运行器 + 工具执行器。后面的规划、记忆与反思都应在这套结构上增加可测试的行为，而不是只多写几个角色名。

- 本章变化：从预设环境观察变成真实教学文件读取，并提供可选择启用的模型接口。
- 可信度：协议来源于官方资料；离线演示不产生模型效果结论。资料核对日期：2026-09-05。
- 当前缺口：真实 API 行为需要你的账户实测，任意仓库访问和代码执行尚未开放。
- 掌握状态：等待你的迁移作业、自测和真实实验，不提前记为掌握。
- 下一步：[第 4 章 ReAct](/notes/llm-agent-04-react/)，对比“单轮回答”和“使用环境反馈的循环”，研究何时值得多走一步。
