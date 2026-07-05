# TradingAgents-Bundle Reflection 记忆机制说明

## 1. 改进动机

原始 TradingAgents 是一次性多智能体投研流程：分析师、辩论团队、交易员和风险团队根据当前输入生成交易结论。但如果系统每次运行后不记录决策结果，就无法知道过去的判断是否正确，也无法把经验反馈给后续决策。

本版 `tradingagents_bundle` 增加了不依赖 embedding 的 markdown decision log 机制，用于把“最终交易决策 -> 后续收益验证 -> 复盘经验”串成闭环。这样系统不只是生成报告，而是可以在后续同标的或跨标的分析中读取已验证的历史经验。

## 2. 当前实现方式

本版保留了旧版 ChromaDB 向量记忆代码，同时新增一套更适合 DeepSeek-only 环境的 markdown 记忆机制。

核心文件：

- `tradingagents/agents/utils/memory_log.py`：新增 `TradingMemoryLog`，负责记录、读取和回填决策日志。
- `tradingagents/graph/trading_graph.py`：运行前解析 pending 记录，运行后写入新的 pending 决策。
- `tradingagents/graph/reflection.py`：新增 `reflect_on_final_decision`，生成 2-4 句中文短复盘。
- `tradingagents/graph/propagation.py`：初始 state 增加 `past_context`。
- `tradingagents/agents/managers/portfolio_manager.py`：Portfolio Manager 读取 `past_context`，把历史经验纳入最终决策。

默认记忆文件：

```text
outputs/memory/decision_memory.md
```

## 3. 运行时序

以 `300269` 为例，流程如下：

```text
第1天运行
生成 6-29 交易信号
写入 decision_memory.md，状态为 pending

第2天运行
运行开始前读取 6-29 pending
获取 6-29 之后的行情
计算 300269 后续收益、SH000905 后续收益和 alpha
调用 quick model 生成 6-29 的 reflection
把 6-29 记录从 pending 回填为已完成复盘
再把已完成 reflection 注入本次 Portfolio Manager
生成 6-30 交易信号
写入 6-30 pending

第3天运行
同理，先回填 6-30，再生成 7-01 信号
```

因此第一天信号本身不会使用 reflection，因为还没有后续结果；第二天开始，只要能获取到后续行情，就可以使用前一天的复盘经验。

## 4. 记忆内容示例

初次运行后记录为：

```text
[2026-06-29 | 300269 | Buy | pending]

DECISION:
当时的最终交易决策...
```

下一次同股票运行并成功回填后变为：

```text
[2026-06-29 | 300269 | Buy | +3.4% | +2.1% | 1d]

DECISION:
当时的最终交易决策...

REFLECTION:
方向判断基本正确，alpha 为 +2.1%。原判断中成交量改善的逻辑得到验证，但新闻催化持续性仍需谨慎。下次遇到类似小盘题材股，应同时确认量价结构和资金持续性。
```

## 5. 为什么不会让 prompt 无限膨胀

本机制不是把所有历史报告全文塞回 prompt，而是只注入少量、已验证的短复盘：

- 同一股票最多读取最近 5 条完整记录。
- 跨股票最多读取最近 3 条短经验。
- 每条 reflection 被限制为 2-4 句。
- 注入位置只在 Portfolio Manager，不进入所有 Agent。

因此它更像“经验摘要表”，不是无限增长的历史上下文。

## 6. 和旧版向量记忆的区别

旧版 memory 基于 `FinancialSituationMemory + ChromaDB + embedding`，会为 bull、bear、trader、invest judge、risk manager 等角色分别维护向量记忆。这种方式理论上更细粒度，但依赖 embedding 能力。

当前环境主要使用 DeepSeek API，而 DeepSeek 不直接提供 embedding。旧版向量记忆在 DeepSeek-only 环境下需要额外 embedding 服务，例如 DashScope，否则稳定性较弱。

新增 markdown decision log 不依赖 embedding，只依赖普通 LLM 调用和行情数据，因此更适合当前实验环境。

## 7. 对多智能体交易框架的意义

这次改动把多智能体流程从“静态投研报告生成”推进到“带结果反馈的决策系统”：

- 分析阶段仍由市场、新闻、社交、基本面 Agent 分工完成。
- 辩论和风险团队仍负责不同立场的审查。
- Reflection 机制负责把最终决策和后续收益关联起来。
- Portfolio Manager 在下一次决策时读取过去已验证的经验，减少重复犯错。

从研究角度看，这相当于在多智能体投研框架中加入了一个轻量的闭环学习模块。

## 8. 当前局限

当前机制还不是严格意义上的模型训练或参数更新，而是基于日志的经验注入。它能影响后续 prompt，但不会改变模型参数。

另外，reflection 的质量依赖三个条件：

- 后续行情数据能正常获取。
- 收益和 alpha 的计算窗口合理。
- LLM 生成的复盘足够具体，而不是泛泛总结。

因此目前不能直接声称“已经显著提升收益”，只能说系统具备了可复盘、可积累经验的闭环能力。

## 9. 后续验证计划

后续可以做一个小规模对比实验：

- 固定股票池和日期区间。
- 跑一组不使用 memory 的 baseline。
- 跑一组启用 reflection memory 的版本。
- 对比 Buy/Hold/Sell 分布、信号分数、后续收益、alpha、最大回撤和报告质量。
- 抽取 1-2 个 case 检查 reflection 是否真正影响了 Portfolio Manager 的结论。

这样可以回答导师可能关心的问题：reflection 机制是否只是“看起来更智能”，还是确实改变了决策质量。

## 10. 汇报表述

可以这样向导师说明：

```text
我们在 TradingAgents-Bundle 中加入了不依赖 embedding 的 reflection memory 机制。系统每次运行后会把最终交易决策写入 markdown decision log；下一次同股票运行时，会根据后续行情计算绝对收益和相对中证500的 alpha，并调用模型生成短复盘。复盘结果会写回日志，并作为 past_context 注入 Portfolio Manager，帮助后续决策参考已经验证过的历史经验。

这个机制相比旧版 ChromaDB 向量记忆更适合当前 DeepSeek-only 环境，因为它不需要额外 embedding 服务。同时我们限制只读取最近少量短复盘，避免 prompt 无限膨胀。当前它主要提供一个可复盘、可积累经验的闭环，后续还需要通过固定股票池和日期区间做 ablation，验证它对信号质量和收益表现的实际影响。
```
