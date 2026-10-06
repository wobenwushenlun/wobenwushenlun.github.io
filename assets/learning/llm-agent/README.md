# LLM Agent：第 1～6 章实验

这是博客前六篇讲义的配套教学代码。默认只运行离线示例，不联网、不需要密钥；第 1、3、4 章只有显式添加 `--live` 才会调用可能计费的 Claude API。第 2、5、6 章仅包含离线机制实验。

## 运行

在博客仓库根目录运行，Python 3.10+：

```powershell
python assets/learning/llm-agent/ch01_client.py
python assets/learning/llm-agent/ch02_loop.py
python assets/learning/llm-agent/ch03_tools.py
python -B assets/learning/llm-agent/ch04_react.py
python -B assets/learning/llm-agent/ch05_planning.py --fault
python -B assets/learning/llm-agent/ch06_context.py --stale-demo
python -B -m unittest discover -s assets/learning/llm-agent -p "test_*.py" -v
```

单独下载时保持六个脚本、测试文件与 `fixtures` 子目录的布局；在该目录运行时省略路径前缀即可。第 4～6 章都依赖 `ch03_tools.py` 和原有三个教学文件。

真实 API 分支需要安装 `anthropic`，并在自己的终端安全设置 `ANTHROPIC_API_KEY` 与 `ANTHROPIC_MODEL`。模型 ID 由你根据账户权限选择，不在课程中写死。不要把密钥放在这个公开下载目录，不要提交密钥。

```powershell
python ch01_client.py --live
python ch01_client.py --live --stream
python ch03_tools.py --live
python ch04_react.py --live --mode provided
python ch04_react.py --live --mode react
```

离线策略和结论是预设内容，只用来测试程序。第 2 章的环境观察也是模拟的；第 3 章会真实读取随附三个教学文件。真实模式会发送被请求的教学文件内容，但不会读取其他仓库。

`fixtures/pricing.py` 故意保留 Bug；`fixtures/test_pricing.py` 故意会失败。它们是后续代码修复课程的题目，不是本次框架测试。不要把所有名为 `test_*.py` 的文件一起运行后将预期失败误判成框架回归。

## 学习记录模板

| 日期 | 章/任务 | 离线或模型 ID | 修改的变量 | 观察与停止原因 | 未验证事项 |
| --- | --- | --- | --- | --- | --- |
| 自填 | 自填 | 自填 | 自填 | 自填 | 自填 |

阶段账本：

- 目标：独立设计、实现和评测 LLM Agent。
- 当前阶段：前六章教材与实验准备；不是学习者掌握评定。
- 已核对事实：消息请求/响应、工具结果配对和客户端执行职责。
- 未解决问题：所选模型在真实任务中的表现、成本与错误分布。
- 掌握分数：未测。
- 薄弱点：待自测与迁移练习识别。
- 下一步：完成第 4～6 章的反馈对照、计划修订与上下文选择练习，再进入记忆与 RAG。

## 阅读路径（五项，按需摘读）

1. [Messages API](https://platform.claude.com/docs/en/build-with-claude/working-with-messages)：20 分钟，识别请求、响应、历史；第 1 章。
2. [Python SDK](https://github.com/anthropics/anthropic-sdk-python)：20 分钟，查调用、流式与错误处理；第 1 章。
3. [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)：30 分钟，区分控制路径；第 2 章。
4. [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)：20 分钟，画一次往返；第 3 章。
5. [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)：20 分钟，核对结果 ID、错误与多结果格式；第 3 章。

文档阅读免费；真实 API 实验需要自行准备服务权限与预算。先读对应段落，不要求通读整个文档站。课程使用主动回忆、故障注入和迁移作业检验理解，未执行真实模型能力评测。

## 本次验证（2026-09-05）

- 三个默认离线入口均正常运行。
- `test_lessons.py` 的 27 项单元测试通过，包括预算、非法动作、路径限制、批量结果配对和截断响应不执行工具。
- 博客构建成功，内部引用检查通过；三篇文章及代码下载路径已纳入生成结果。
- 未安装或调用真实模型服务，`--live` 与真实流式网络行为尚未联调；离线测试不证明 SDK 集成或模型效果。
- 教学文件中的折扣 Bug 保留未修改；用户的学习掌握程度尚未测试。

## 第 4～6 章的项目增量

| 章 | 文件 | 实验边界 |
| --- | --- | --- |
| 4 | `ch04_react.py` | 三种证据访问条件；默认离线固定答案，仅真实调用才能观察模型表现 |
| 5 | `ch05_planning.py` | DAG 调度与有限修订；Planner 是脚本替身，不是 LLM |
| 6 | `ch06_context.py` | 词法检索与字符预算；不是 Token 计数，不发送 API 请求 |

三个模块分别运行，共用受限文件工具。尚未整合成完整 Coding Agent，也不修改或运行教学代码。

第 4 章评分器只针对公开的折扣例题；不能把脚本得分当成模型基准成绩。第 5 章 `completed` 只意味着证据读取成功。第 6 章记录路径、行号与文件文本哈希；预算包括标签但不包括系统提示、工具定义和输出空间。

## 第 4～6 章阅读路径（五项）

1. [ReAct](https://arxiv.org/abs/2210.03629)：40 分钟，重点读方法与消融，画出动作反馈关系；第 4 章。论文免费，先理解第 3 章循环。
2. [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)：30 分钟，将编排模式映射到具体任务；第 5 章。以架构原理为主，不依赖旧工具清单。
3. [Tree of Thoughts](https://arxiv.org/abs/2305.10601)：30 分钟，区分候选生成、评估和搜索；第 5 章拓展。先掌握简单任务图，不要求复现完整论文。
4. [Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：25 分钟，识别检索、选择和压缩的不同职责；第 6 章。用文中思路审查自己的 ContextBuilder。
5. [Token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)：15 分钟，确定真实请求计数边界；第 6 章。阅读免费，接口使用需账户权限；本课离线实验不调用它。

各章包含故障实验、自测参考与迁移任务。先提交自己的解释，再查看参考答案；没有真实 API 条件时，只将离线控制机制标记为已验证。

## 本次验证（2026-10-06）

- 前三章 27 项测试与新增 24 项测试共 51 项通过。
- 第 4 章三组离线管线正常；第 5 章故障修订保留已完成任务且不重置预算；第 6 章默认示例检测到内存模拟的文件版本变化。
- 新增覆盖：评分器的证据与类型校验、模型客户端适配替身、无环图与非法修订、字符预算、查询无匹配、来源行号和过期证据。
- 没有调用真实模型 API；客户端适配替身测试不等同于 SDK 网络联调或模型质量评测。
